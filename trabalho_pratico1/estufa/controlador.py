"""
controlador.py — Processo Controlador distribuído com liderança e consenso.

Responsabilidades:
  1. Eleição dinâmica de líder entre os controladores (algoritmo Bully via XML-RPC).
  2. Validação por consenso dinâmico antes de persistir o estado oficial nos bancos
     replicados (data_ctrl_1.json, data_ctrl_2.json, data_ctrl_3.json).
  3. Publicação exclusiva pelo Líder dos comandos MQTT de atuação (bomba e exaustor).
  4. Sincronização automática de réplica no boot/reconexão diretamente com os pares.

Uso simplificado:
    python -m estufa.controlador 1
    python -m estufa.controlador 2 --byzantino
"""

import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
import os
import socket
import socketserver
import threading
import time
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer
import paho.mqtt.client as mqtt
from estufa import config
from estufa.middleware import ClusterMiddleware, ErroQuorum, criar_proxy_rpc


class _ThreadedXMLRPCServer(socketserver.ThreadingMixIn, SimpleXMLRPCServer):
    """Servidor XML-RPC multi-thread com reuso de porta para evitar bloqueios e WinError 10048."""

    allow_reuse_address = True
    daemon_threads = True


ESTADO_INICIAL = {
    "temperatura": None,
    "umidade": None,
    "bomba_ligada": False,
    "exaustor_ligado": False,
    "ultima_atualizacao": None,
    "lider_id": None,
}

CAMPOS_PERSISTIDOS = (
    "temperatura",
    "umidade",
    "bomba_ligada",
    "exaustor_ligado",
    "ultima_atualizacao",
    "lider_id",
)


def _avaliar_regras_atuacao(
    temperatura: float | None,
    umidade: float | None,
    bomba_atual: bool,
    exaustor_atual: bool,
) -> tuple[bool, bool]:
    """Avalia regras de histerese para bomba e exaustor sem efeitos colaterais."""
    novo_exaustor = exaustor_atual
    if temperatura is not None:
        if temperatura > config.TEMP_MAX_CELSIUS:
            novo_exaustor = True
        elif temperatura < config.TEMP_MIN_CELSIUS:
            novo_exaustor = False

    nova_bomba = bomba_atual
    if umidade is not None:
        if umidade < config.UMIDADE_MIN_PERCENT:
            nova_bomba = True
        elif umidade > config.UMIDADE_MAX_PERCENT:
            nova_bomba = False

    return nova_bomba, novo_exaustor


def _validar_limites_sensor(temperatura: float | None, umidade: float | None) -> bool:
    """Valida se leituras de temperatura e umidade estão dentro de faixa física aceitável."""
    if temperatura is not None:
        if isinstance(temperatura, bool) or not isinstance(temperatura, (int, float)):
            return False
        if not (-50.0 <= float(temperatura) <= 100.0):
            return False
    if umidade is not None:
        if isinstance(umidade, bool) or not isinstance(umidade, (int, float)):
            return False
        if not (0.0 <= float(umidade) <= 100.0):
            return False
    return True


class Controlador:
    """
    Nó controlador replicado do cluster distribuído (Middleware lógico embarcado).

    Regra de concorrência: self._lock nunca é mantido durante chamadas XML-RPC externas,
    prevenindo deadlocks entre eleições, votações e commits simultâneos.
    """

    def __init__(
        self,
        ctrl_id: str | int,
        port: int | None = None,
        data_file: str | None = None,
        host: str = "127.0.0.1",
        byzantino: bool = False,
        pares: list[dict] | None = None,
        timeout_rpc: float = config.TIMEOUT_RPC_SEGUNDOS,
        heartbeat_interval: float = config.INTERVALO_HEARTBEAT_SEGUNDOS,
    ):
        try:
            cfg = config.obter_config_controlador(ctrl_id)
            self.ctrl_id = cfg["id"]
            self.rank = int(cfg["rank"])
            self.host = host or cfg["host"]
            self.port = int(port if port is not None else cfg["port"])
            self.data_file = data_file if data_file is not None else cfg["data_file"]
        except ValueError:
            self.ctrl_id = str(ctrl_id)
            digitos = "".join(ch for ch in self.ctrl_id if ch.isdigit())
            self.rank = int(digitos) if digitos else 1
            self.host = host
            self.port = int(port if port is not None else 8000 + self.rank)
            self.data_file = data_file if data_file is not None else f"data_{self.ctrl_id}.json"

        self.byzantino = bool(byzantino)
        self._timeout_rpc = float(timeout_rpc)
        self._heartbeat_interval = float(heartbeat_interval)

        if pares is not None:
            self._pares = [dict(p) for p in pares if p.get("id") != self.ctrl_id]
        else:
            self._pares = [
                dict(c) for c in config.MAPA_CONTROLADORES.values()
                if c["id"] != self.ctrl_id
            ]

        self._lock = threading.RLock()
        self._eleicao_lock = threading.Lock()
        self._parar_evento = threading.Event()
        self._mqtt_client = None
        self._server: SimpleXMLRPCServer | None = None

        self._estado = self._carregar_estado()
        # No boot/reconexão, o líder ativo deve ser descoberto no cluster (não assumido do disco antigo)
        self.lider_id: str | None = None

    def eh_lider(self) -> bool:
        """Indica se este controlador é o líder atual do cluster."""
        with self._lock:
            return self.lider_id == self.ctrl_id

    def _criar_proxy_par(self, par: dict) -> xmlrpc.client.ServerProxy:
        """Cria um proxy XML-RPC com timeout explícito para um controlador par."""
        return criar_proxy_rpc(par["host"], int(par["port"]), timeout=self._timeout_rpc)

    def _carregar_estado(self) -> dict:
        """Lê o estado persistido em disco ou retorna o estado inicial canônico."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                if isinstance(dados, dict):
                    estado = dict(ESTADO_INICIAL)
                    for chave in CAMPOS_PERSISTIDOS:
                        if chave in dados:
                            estado[chave] = dados[chave]
                    if "umidade" not in dados and "umidade_solo" in dados:
                        estado["umidade"] = dados["umidade_solo"]
                    return estado
            except (json.JSONDecodeError, OSError):
                pass
        return dict(ESTADO_INICIAL)

    def _salvar_estado(self) -> None:
        """Persiste de forma atômica o estado oficial no arquivo JSON local."""
        with self._lock:
            dados = {chave: self._estado.get(chave) for chave in CAMPOS_PERSISTIDOS}
        tmp_file = f"{self.data_file}.{threading.get_ident()}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
            for tentativa in range(5):
                try:
                    os.replace(tmp_file, self.data_file)
                    return
                except PermissionError:
                    if tentativa == 4:
                        raise
                    time.sleep(0.02)
        except OSError as e:
            print(f"[{self.ctrl_id}] Erro ao salvar estado: {e}")
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Métodos RPC de Eleição (Algoritmo Valentão / Bully) e Heartbeat
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """Verificação de disponibilidade e identificação do papel do nó."""
        with self._lock:
            return {
                "status": "ok",
                "id": self.ctrl_id,
                "rank": self.rank,
                "lider_id": self.lider_id,
            }

    def iniciar_eleicao(self, rank_origem: int) -> dict:
        """Recebe mensagem de eleição de um nó de menor rank e assume se tiver prioridade maior."""
        if not isinstance(rank_origem, int) or isinstance(rank_origem, bool):
            raise ValueError("rank_origem deve ser inteiro.")

        if self.rank > rank_origem:
            threading.Thread(target=self.realizar_eleicao, daemon=True).start()
            return {"aceito": True, "id": self.ctrl_id, "rank": self.rank}

        return {"aceito": False, "id": self.ctrl_id, "rank": self.rank}

    def _obter_rank_id(self, ctrl_id: str) -> int:
        try:
            return int(config.obter_config_controlador(ctrl_id)["rank"])
        except ValueError:
            digs = "".join(ch for ch in str(ctrl_id) if ch.isdigit())
            return int(digs) if digs else 0

    def anunciar_lider(self, novo_lider_id: str) -> dict:
        """Registra o novo líder eleito pelo algoritmo Bully."""
        if not isinstance(novo_lider_id, str) or not novo_lider_id.strip():
            raise ValueError("novo_lider_id inválido.")

        lider_limpo = novo_lider_id.strip()
        if self._obter_rank_id(lider_limpo) < self.rank:
            # Nó de rank superior nunca aceita líder de rank inferior; dispara nova eleição Bully
            threading.Thread(target=self.realizar_eleicao, daemon=True).start()
            return {"ok": False, "id": self.ctrl_id, "lider_id": self.ctrl_id}

        with self._lock:
            self.lider_id = lider_limpo
            self._estado["lider_id"] = self.lider_id
            self._salvar_estado()

        print(f"[ELEICAO] [{self.ctrl_id}] Novo líder reconhecido: {self.lider_id}")
        return {"ok": True, "id": self.ctrl_id, "lider_id": self.lider_id}

    # Algoritmo Valentão (Bully): consulta nós com rank maior; se nenhum responder, assume liderança
    def realizar_eleicao(self) -> str:
        """Executa o algoritmo Bully entre os pares configurados e elege o maior rank ativo."""
        with self._eleicao_lock:
            with self._lock:
                pares = list(self._pares)

            superiores = sorted(
                [p for p in pares if int(p["rank"]) > self.rank],
                key=lambda p: int(p["rank"]),
                reverse=True,
            )

            superior_ativo = None
            if superiores:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(superiores))
                futuros = {
                    executor.submit(
                        lambda par: self._criar_proxy_par(par).iniciar_eleicao(self.rank),
                        p,
                    ): p
                    for p in superiores
                }
                respondentes = []
                try:
                    for fut in concurrent.futures.as_completed(futuros, timeout=self._timeout_rpc + 0.2):
                        par = futuros[fut]
                        try:
                            resp = fut.result(timeout=0.1)
                            if isinstance(resp, dict) and resp.get("aceito"):
                                respondentes.append(par)
                        except Exception:
                            continue
                except (concurrent.futures.TimeoutError, TimeoutError):
                    pass
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

                if respondentes:
                    superior_ativo = max(respondentes, key=lambda p: int(p["rank"]))

            if superior_ativo is None:
                with self._lock:
                    self.lider_id = self.ctrl_id
                    self._estado["lider_id"] = self.ctrl_id
                    self._salvar_estado()
                    estado_para_replicar = dict(self._estado)

                print(f"[ELEICAO] [{self.ctrl_id}] Assumiu a LIDERANÇA (rank={self.rank}).")

                if pares:
                    def _notificar_par(par: dict) -> None:
                        proxy = self._criar_proxy_par(par)
                        proxy.anunciar_lider(self.ctrl_id)
                        if (
                            not self.byzantino
                            and estado_para_replicar.get("ultima_atualizacao") is not None
                        ):
                            proxy.commit_estado(estado_para_replicar)

                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(pares))
                    futuros_anuncio = [executor.submit(_notificar_par, par) for par in pares]
                    try:
                        concurrent.futures.wait(futuros_anuncio, timeout=self._timeout_rpc + 0.3)
                    finally:
                        executor.shutdown(wait=False, cancel_futures=True)
                return self.ctrl_id

            # Aguarda brevemente o anúncio do nó superior; se ainda não chegou, consulta o superior
            time.sleep(min(0.25, self._timeout_rpc))
            try:
                resp_ping = self._criar_proxy_par(superior_ativo).ping()
                novo_lider = (
                    resp_ping.get("lider_id") or superior_ativo["id"]
                    if isinstance(resp_ping, dict)
                    else superior_ativo["id"]
                )
            except Exception:
                novo_lider = superior_ativo["id"]

            with self._lock:
                self.lider_id = novo_lider
                self._estado["lider_id"] = novo_lider
                self._salvar_estado()

            return novo_lider

    def _encontrar_par(self, ctrl_id: str | None) -> dict | None:
        if not ctrl_id:
            return None
        for par in self._pares:
            if par["id"] == ctrl_id:
                return par
        return None

    # Detecção de falha por heartbeat: monitora o líder via ping() e dispara eleição se cair
    def _loop_heartbeat(self) -> None:
        """Monitora periodicamente o líder ativo e dispara eleição em caso de falha."""
        while not self._parar_evento.is_set():
            self._parar_evento.wait(self._heartbeat_interval)
            if self._parar_evento.is_set():
                break

            with self._lock:
                lider_atual = self.lider_id

            if lider_atual is None:
                self.realizar_eleicao()
                continue

            if lider_atual == self.ctrl_id:
                continue

            par_lider = self._encontrar_par(lider_atual)
            if par_lider is None:
                self.realizar_eleicao()
                continue

            try:
                resp = self._criar_proxy_par(par_lider).ping()
                if not isinstance(resp, dict) or resp.get("status") != "ok":
                    raise OSError("Resposta inválida no heartbeat")
            except (
                ConnectionRefusedError,
                TimeoutError,
                socket.timeout,
                OSError,
                xmlrpc.client.Fault,
                xmlrpc.client.ProtocolError,
            ) as e:
                print(f"[HEARTBEAT] [{self.ctrl_id}] Líder '{lider_atual}' falhou ({e}). Iniciando eleição...")
                self.realizar_eleicao()

    # ------------------------------------------------------------------
    # Sincronização de Réplica na Inicialização / Reconexão
    # ------------------------------------------------------------------

    # Recuperação de réplica: ao religar, puxa o estado oficial dos pares antes de operar
    def _sincronizar_com_cluster(self) -> bool:
        """
        Consulta os pares ativos na inicialização para obter o estado oficial atual
        e atualizar imediatamente o banco JSON local antes de assumir operações.
        """
        with self._lock:
            pares = list(self._pares)

        respostas = []
        lider_descoberto = None

        if pares:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(pares))
            futuros = {
                executor.submit(lambda p: self._criar_proxy_par(p).obter_estado(), par): par
                for par in pares
            }
            try:
                for fut in concurrent.futures.as_completed(futuros, timeout=self._timeout_rpc + 0.2):
                    par = futuros[fut]
                    try:
                        estado = fut.result(timeout=0.1)
                        if isinstance(estado, dict):
                            respostas.append((par["id"], estado))
                            if estado.get("lider_id"):
                                lider_descoberto = estado["lider_id"]
                    except Exception:
                        continue
            except (concurrent.futures.TimeoutError, TimeoutError):
                pass
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        if not respostas:
            print(f"[SYNC] [{self.ctrl_id}] Nenhum par ativo no momento; mantendo estado local.")
            return False

        inicializados = [
            (pid, est)
            for pid, est in respostas
            if not (
                est.get("ultima_atualizacao") is None
                and est.get("temperatura") is None
                and est.get("umidade") is None
            )
        ]
        candidatos = inicializados if inicializados else respostas

        try:
            oficial = ClusterMiddleware.calcular_consenso([est for _, est in candidatos])
        except ErroQuorum:
            # Em empate (ex: reconexão com estado desatualizado ou 1 bizantino), prioriza líder ativo e timestamp mais recente
            validos = [
                (pid, est)
                for pid, est in candidatos
                if _validar_limites_sensor(est.get("temperatura"), est.get("umidade"))
            ]
            if not validos:
                print(f"[SYNC] [{self.ctrl_id}] Divergência entre pares na sincronização; aguardando consenso.")
                return False
            _, oficial = max(
                validos,
                key=lambda item: (
                    1 if item[0] == item[1].get("lider_id") else 0,
                    str(item[1].get("ultima_atualizacao") or ""),
                ),
            )

        if not _validar_limites_sensor(oficial.get("temperatura"), oficial.get("umidade")):
            print(f"[SYNC] [{self.ctrl_id}] Estado descartado por limites inválidos.")
            return False

        with self._lock:
            self._estado["temperatura"] = oficial.get("temperatura")
            self._estado["umidade"] = oficial.get("umidade")
            self._estado["bomba_ligada"] = bool(oficial.get("bomba_ligada", False))
            self._estado["exaustor_ligado"] = bool(oficial.get("exaustor_ligado", False))
            self._estado["ultima_atualizacao"] = oficial.get("ultima_atualizacao")
            if oficial.get("lider_id"):
                self.lider_id = oficial["lider_id"]
                self._estado["lider_id"] = self.lider_id
            self._salvar_estado()

        print(
            f"[SYNC] [{self.ctrl_id}] Banco local sincronizado com o cluster "
            f"(Temp={self._estado['temperatura']}, Umidade={self._estado['umidade']}, "
            f"Bomba={self._estado['bomba_ligada']}, Exaustor={self._estado['exaustor_ligado']})."
        )
        return True

    # ------------------------------------------------------------------
    # Consenso Dinâmico e Persistência Replicada (commit_estado)
    # ------------------------------------------------------------------

    # Votação P2P: cada nó avalia as regras de histerese (ou adultera em modo --byzantino)
    def coletar_voto_estado(self, proposta: dict | None = None) -> dict:
        """
        Retorna o voto deste controlador para validação por consenso antes do commit.
        Em modo --byzantino, retorna valores propositalmente corrompidos.
        """
        with self._lock:
            if self.byzantino:
                return {
                    "temperatura": 999.9,
                    "umidade": -50.0,
                    "bomba_ligada": not bool(self._estado.get("bomba_ligada", False)),
                    "exaustor_ligado": not bool(self._estado.get("exaustor_ligado", False)),
                    "lider_id": self.lider_id,
                }

            temp = self._estado.get("temperatura")
            umidade = self._estado.get("umidade")
            bomba_atual = bool(self._estado.get("bomba_ligada", False))
            exaustor_atual = bool(self._estado.get("exaustor_ligado", False))
            lider_atual = self.lider_id

        if isinstance(proposta, dict):
            if proposta.get("manual"):
                nova_bomba = bool(proposta.get("bomba_ligada", bomba_atual))
                novo_exaustor = bool(proposta.get("exaustor_ligado", exaustor_atual))
                return {
                    "temperatura": temp,
                    "umidade": umidade,
                    "bomba_ligada": nova_bomba,
                    "exaustor_ligado": novo_exaustor,
                    "lider_id": lider_atual,
                }

            prop_temp = proposta.get("temperatura", temp)
            prop_umid = proposta.get("umidade", umidade)
            if _validar_limites_sensor(prop_temp, prop_umid):
                temp = float(prop_temp) if prop_temp is not None else None
                umidade = float(prop_umid) if prop_umid is not None else None

        nova_bomba, novo_exaustor = _avaliar_regras_atuacao(
            temp, umidade, bomba_atual, exaustor_atual
        )
        return {
            "temperatura": temp,
            "umidade": umidade,
            "bomba_ligada": nova_bomba,
            "exaustor_ligado": novo_exaustor,
            "lider_id": lider_atual,
        }

    # Persistência replicada: todas as réplicas ativas gravam o mesmo JSON validado pelo Líder
    def commit_estado(self, estado_oficial: dict) -> dict:
        """
        Recebe o estado oficial validado por consenso pelo Líder e persiste no banco local.
        """
        if not isinstance(estado_oficial, dict):
            raise ValueError("estado_oficial deve ser um dicionário.")
        if not isinstance(estado_oficial.get("bomba_ligada"), bool):
            raise ValueError("Campo 'bomba_ligada' inválido.")
        if not isinstance(estado_oficial.get("exaustor_ligado"), bool):
            raise ValueError("Campo 'exaustor_ligado' inválido.")
        if not _validar_limites_sensor(estado_oficial.get("temperatura"), estado_oficial.get("umidade")):
            raise ValueError("Valores de sensor fora dos limites físicos permitidos.")

        with self._lock:
            self._estado["temperatura"] = estado_oficial.get("temperatura")
            self._estado["umidade"] = estado_oficial.get("umidade")
            self._estado["bomba_ligada"] = estado_oficial["bomba_ligada"]
            self._estado["exaustor_ligado"] = estado_oficial["exaustor_ligado"]
            self._estado["ultima_atualizacao"] = estado_oficial.get("ultima_atualizacao")
            if estado_oficial.get("lider_id"):
                self.lider_id = str(estado_oficial["lider_id"])
            self._estado["lider_id"] = self.lider_id
            self._salvar_estado()

        return {"ok": True, "id": self.ctrl_id}

    # Apenas o Líder publica comandos MQTT após o consenso, evitando duplicidade no atuador
    def _publicar_comando(self, topico: str, acao: str) -> None:
        """Publica comando oficial para o atuador via MQTT (chamado apenas pelo Líder)."""
        payload = json.dumps({
            "acao": acao,
            "origem": self.ctrl_id,
            "timestamp": time.time(),
        })
        if self._mqtt_client:
            self._mqtt_client.publish(topico, payload, qos=1)

    # Coordenação do consenso: coleta votos em paralelo, resolve quórum e replica commit_estado
    def _coordenar_consenso_e_persistir(
        self,
        proposta: dict,
        publicar_atuacao: bool = True,
        forcar_publicacao: tuple[str, bool] | None = None,
    ) -> dict:
        """
        Executado pelo Líder: coleta votos dos pares ativos em paralelo, resolve o quórum
        dinâmico, faz commit síncrono do estado oficial em todas as réplicas e publica no MQTT.
        """
        with self._lock:
            estado_anterior = dict(self._estado)
            pares = list(self._pares)

        # Coleta votos em paralelo fora de self._lock para evitar contenção e atraso em cascata
        votos = [self.coletar_voto_estado(proposta)]
        pares_alcancaveis = []

        if pares:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(pares))
            futuros = {
                executor.submit(
                    lambda p: self._criar_proxy_par(p).coletar_voto_estado(proposta),
                    par,
                ): par
                for par in pares
            }
            try:
                for fut in concurrent.futures.as_completed(futuros, timeout=self._timeout_rpc + 0.2):
                    par = futuros[fut]
                    try:
                        voto = fut.result(timeout=0.1)
                        if isinstance(voto, dict):
                            votos.append(voto)
                            pares_alcancaveis.append(par)
                    except Exception:
                        continue
            except (concurrent.futures.TimeoutError, TimeoutError):
                pass
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        if len(votos) == 1:
            print(f"[QUORUM DEGRADADO: 1/3 ativos] [{self.ctrl_id}] Operando em modo isolado.")

        estado_oficial = ClusterMiddleware.calcular_consenso(votos)
        estado_oficial["ultima_atualizacao"] = datetime.now(timezone.utc).isoformat()
        estado_oficial["lider_id"] = self.ctrl_id

        self.commit_estado(estado_oficial)

        if pares_alcancaveis:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(pares_alcancaveis))
            futuros_commit = {
                executor.submit(
                    lambda p: self._criar_proxy_par(p).commit_estado(estado_oficial),
                    par,
                ): par
                for par in pares_alcancaveis
            }
            try:
                for fut in concurrent.futures.as_completed(futuros_commit, timeout=self._timeout_rpc + 0.2):
                    par = futuros_commit[fut]
                    try:
                        fut.result(timeout=0.1)
                    except Exception as e:
                        print(f"[REPLICA] [{self.ctrl_id}] Falha ao enviar commit para {par['id']}: {e}")
            except (concurrent.futures.TimeoutError, TimeoutError):
                pass
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        if publicar_atuacao and self.eh_lider():
            if forcar_publicacao is not None:
                alvo, ligar = forcar_publicacao
                topico = (
                    config.TOPIC_ATUADOR_BOMBA
                    if alvo == "bomba"
                    else config.TOPIC_ATUADOR_EXAUSTOR
                )
                self._publicar_comando(topico, "ligar" if ligar else "desligar")
            else:
                if estado_oficial["exaustor_ligado"] != estado_anterior.get("exaustor_ligado", False):
                    acao = "ligar" if estado_oficial["exaustor_ligado"] else "desligar"
                    self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, acao)
                    print(f"[LIDER] [{self.ctrl_id}] Exaustor -> {acao.upper()} (consenso)")

                if estado_oficial["bomba_ligada"] != estado_anterior.get("bomba_ligada", False):
                    acao = "ligar" if estado_oficial["bomba_ligada"] else "desligar"
                    self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, acao)
                    print(f"[LIDER] [{self.ctrl_id}] Bomba -> {acao.upper()} (consenso)")

        return dict(estado_oficial)

    # ------------------------------------------------------------------
    # MQTT: Consumo de Sensores
    # ------------------------------------------------------------------

    # Inscrição MQTT QoS 1 nos tópicos dos sensores ao conectar ao broker
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(config.TOPIC_TEMPERATURA, qos=1)
            client.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)
            print(f"[{self.ctrl_id}] Conectado ao broker MQTT. Assinando tópicos de sensores.")
        else:
            print(f"[{self.ctrl_id}] Falha na conexão MQTT: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            valor = float(payload["valor"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"[{self.ctrl_id}] Mensagem MQTT inválida: {e}")
            return

        if msg.topic == config.TOPIC_TEMPERATURA and not _validar_limites_sensor(valor, None):
            print(f"[{self.ctrl_id}] Temperatura fora da faixa física: {valor}")
            return
        if msg.topic == config.TOPIC_UMIDADE_SOLO and not _validar_limites_sensor(None, valor):
            print(f"[{self.ctrl_id}] Umidade fora da faixa física: {valor}")
            return

        with self._lock:
            proposta = {
                "temperatura": self._estado.get("temperatura"),
                "umidade": self._estado.get("umidade"),
            }
            if msg.topic == config.TOPIC_TEMPERATURA:
                proposta["temperatura"] = valor
                self._estado["temperatura"] = valor
                print(f"[{self.ctrl_id}] Temperatura recebida: {valor:.2f}°C")
            elif msg.topic == config.TOPIC_UMIDADE_SOLO:
                proposta["umidade"] = valor
                self._estado["umidade"] = valor
                print(f"[{self.ctrl_id}] Umidade recebida: {valor:.2f}%")
            else:
                return

            sou_lider = (self.lider_id == self.ctrl_id)
            sem_lider = (self.lider_id is None)

        if sem_lider:
            self.realizar_eleicao()
            sou_lider = self.eh_lider()

        if sou_lider:
            try:
                self._coordenar_consenso_e_persistir(proposta, publicar_atuacao=True)
            except ErroQuorum as e:
                print(f"[{self.ctrl_id}] Consenso bloqueado: {e}")

    # ------------------------------------------------------------------
    # Interface XML-RPC para Cliente Direto e Pares
    # ------------------------------------------------------------------

    def obter_estado(self) -> dict:
        """Retorna o estado local da réplica (ou dados corrompidos em modo bizantino)."""
        with self._lock:
            if self.byzantino:
                return {
                    "temperatura": 999.9,
                    "umidade": -50.0,
                    "bomba_ligada": not bool(self._estado.get("bomba_ligada", False)),
                    "exaustor_ligado": not bool(self._estado.get("exaustor_ligado", False)),
                    "ultima_atualizacao": datetime.now(timezone.utc).isoformat(),
                    "lider_id": self.lider_id,
                }
            return dict(self._estado)

    def _executar_comando_atuador(self, alvo: str, ligar: bool) -> dict:
        """
        Valida e encaminha comando manual ao Líder (ou executa consenso se for o Líder).
        """
        if alvo not in ("bomba", "exaustor"):
            raise ValueError(f"Atuador inválido: {alvo}")
        if not isinstance(ligar, bool):
            raise ValueError("O parâmetro 'ligar' deve ser booleano (True ou False).")

        with self._lock:
            lider_atual = self.lider_id

        if lider_atual != self.ctrl_id:
            par_lider = self._encontrar_par(lider_atual)
            if par_lider is not None:
                try:
                    proxy = criar_proxy_rpc(
                        par_lider["host"],
                        int(par_lider["port"]),
                        timeout=self._timeout_rpc * 2.5,
                    )
                    metodo = "comandar_bomba" if alvo == "bomba" else "comandar_exaustor"
                    return getattr(proxy, metodo)(ligar)
                except (
                    ConnectionRefusedError,
                    TimeoutError,
                    socket.timeout,
                    OSError,
                    xmlrpc.client.ProtocolError,
                ):
                    pass

            # Líder anterior indisponível ou indefinido: realiza eleição imediata
            novo_lider = self.realizar_eleicao()
            if novo_lider != self.ctrl_id:
                par_novo = self._encontrar_par(novo_lider)
                if par_novo is not None:
                    proxy = criar_proxy_rpc(
                        par_novo["host"],
                        int(par_novo["port"]),
                        timeout=self._timeout_rpc * 2.5,
                    )
                    metodo = "comandar_bomba" if alvo == "bomba" else "comandar_exaustor"
                    return getattr(proxy, metodo)(ligar)

        with self._lock:
            proposta = {
                "manual": True,
                "temperatura": self._estado.get("temperatura"),
                "umidade": self._estado.get("umidade"),
                "bomba_ligada": ligar if alvo == "bomba" else bool(self._estado.get("bomba_ligada", False)),
                "exaustor_ligado": ligar if alvo == "exaustor" else bool(self._estado.get("exaustor_ligado", False)),
            }

        try:
            oficial = self._coordenar_consenso_e_persistir(
                proposta,
                publicar_atuacao=True,
                forcar_publicacao=(alvo, ligar),
            )
        except ErroQuorum as e:
            raise xmlrpc.client.Fault(1, str(e)) from e

        nome = "Bomba" if alvo == "bomba" else "Exaustor"
        estado_txt = (
            ("ligada" if ligar else "desligada")
            if alvo == "bomba"
            else ("ligado" if ligar else "desligado")
        )
        oficial["sucesso"] = True
        oficial["mensagem"] = f"{nome} {estado_txt} com sucesso"
        return oficial

    def comandar_bomba(self, ligar: bool) -> dict:
        """Aciona ou desliga manualmente a bomba de irrigação com consenso do cluster."""
        return self._executar_comando_atuador("bomba", ligar)

    def comandar_exaustor(self, ligar: bool) -> dict:
        """Aciona ou desliga manualmente o exaustor com consenso do cluster."""
        return self._executar_comando_atuador("exaustor", ligar)

    # ------------------------------------------------------------------
    # Ciclo de Vida do Serviço
    # ------------------------------------------------------------------

    def iniciar_servidor_rpc(self) -> None:
        """Sobe servidor XML-RPC, sincroniza estado com pares ativos e inicia eleição/heartbeat."""
        self._parar_evento.clear()
        self._server = _ThreadedXMLRPCServer(
            (self.host, self.port),
            allow_none=True,
            logRequests=False,
        )
        self._server.register_instance(self)

        modo = " [MODO BIZANTINO]" if self.byzantino else ""
        print(f"[{self.ctrl_id}] Servidor XML-RPC ativo em {self.host}:{self.port}{modo}")

        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._sincronizar_com_cluster()
        self.realizar_eleicao()
        threading.Thread(target=self._loop_heartbeat, daemon=True).start()

    def parar(self) -> None:
        """Encerra ordenadamente heartbeat, servidor XML-RPC e cliente MQTT."""
        self._parar_evento.set()
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.disconnect()
            except Exception:
                pass
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass

    def iniciar(self) -> None:
        """Inicializa servidor XML-RPC, sincronização/eleição Bully e consumo MQTT."""
        self.iniciar_servidor_rpc()

        self._mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"controlador_{self.ctrl_id}",
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)

        print(f"[{self.ctrl_id}] Controlador pronto. Consumindo sensores MQTT.")
        try:
            self._mqtt_client.loop_forever()
        except KeyboardInterrupt:
            print(f"\n[{self.ctrl_id}] Encerrando controlador...")
        finally:
            self.parar()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Controlador Distribuído da Estufa")
    parser.add_argument(
        "numero",
        nargs="?",
        help="Número do controlador (1, 2 ou 3)",
    )
    parser.add_argument("--id", help="Identificador opcional (ex: ctrl_1)")
    parser.add_argument("--port", type=int, help="Porta XML-RPC opcional")
    parser.add_argument("--data", help="Arquivo JSON opcional")
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor XML-RPC")
    parser.add_argument("--byzantino", action="store_true", help="Ativa simulação de falha bizantina")
    args = parser.parse_args()

    identificador = args.numero or args.id
    if not identificador:
        parser.error("Informe o número do controlador (1, 2 ou 3) ou --id.")

    ctrl = Controlador(
        ctrl_id=identificador,
        port=args.port,
        data_file=args.data,
        host=args.host,
        byzantino=args.byzantino,
    )
    ctrl.iniciar()
