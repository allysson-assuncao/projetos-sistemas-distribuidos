"""
middleware.py — Camada lógica distribuída de comunicação RPC, failover e consenso.

Módulo utilizado pelo Cliente (para descoberta de líder, failover automático
e leitura por consenso) e pelos Controladores (para comunicação P2P, eleição
e apuração de quórum entre as réplicas do cluster).
"""

import collections
import concurrent.futures
import json
import socket
import xmlrpc.client
from typing import Any
from estufa import config


class ErroQuorum(Exception):
    """Exceção lançada quando não há consenso ou controladores ativos suficientes."""


# Transporte XML-RPC com timeout explícito para evitar travamento TCP longo no Windows
class _TimeoutTransport(xmlrpc.client.Transport):
    """Transporte XML-RPC com timeout explícito de socket para evitar travamentos no Windows."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


def criar_proxy_rpc(
    host: str,
    port: int,
    timeout: float = config.TIMEOUT_RPC_SEGUNDOS,
) -> xmlrpc.client.ServerProxy:
    """Cria um proxy XML-RPC com timeout de socket explícito para (host, port)."""
    url = f"http://{host}:{port}"
    return xmlrpc.client.ServerProxy(
        url,
        transport=_TimeoutTransport(timeout),
        allow_none=True,
    )


def _normalizar_lista_controladores(controladores: list | None) -> list[dict]:
    """Converte entradas (tuplas ou dicts) para lista padronizada de metadados do cluster."""
    itens = controladores if controladores is not None else config.CONTROLADORES
    mapa_por_porta = {cfg["port"]: cfg for cfg in config.MAPA_CONTROLADORES.values()}

    normalizados = []
    for idx, item in enumerate(itens, start=1):
        if isinstance(item, dict):
            port = int(item["port"])
            base = mapa_por_porta.get(port, {})
            normalizados.append({
                "id": item.get("id", base.get("id", f"ctrl_{idx}")),
                "rank": int(item.get("rank", base.get("rank", idx))),
                "host": item.get("host", "127.0.0.1"),
                "port": port,
            })
        else:
            host, port = item
            port = int(port)
            base = mapa_por_porta.get(port, {})
            normalizados.append({
                "id": base.get("id", f"ctrl_{idx}"),
                "rank": int(base.get("rank", idx)),
                "host": host,
                "port": port,
            })
    return normalizados


class ClusterMiddleware:
    """
    Camada lógica do Middleware para comunicação direta Cliente <-> Controladores
    e cálculo de consenso dinâmico sobre réplicas ativas.
    """

    def __init__(
        self,
        controladores: list | None = None,
        timeout: float | None = None,
    ):
        self._controladores = _normalizar_lista_controladores(controladores)
        # Cliente usa janela maior que o timeout entre pares (coleta + commit no líder)
        self._timeout = float(
            timeout if timeout is not None else config.TIMEOUT_RPC_SEGUNDOS * 2.5
        )
        self._lider_atual: dict | None = None

    @property
    def controladores(self) -> list[dict]:
        """Lista dos nós configurados no cluster."""
        return list(self._controladores)

    def _criar_proxy(self, controlador: dict | tuple[str, int]) -> xmlrpc.client.ServerProxy:
        """Instancia um proxy XML-RPC para o controlador informado."""
        if isinstance(controlador, dict):
            host, port = controlador["host"], int(controlador["port"])
        else:
            host, port = controlador[0], int(controlador[1])
        return criar_proxy_rpc(host, port, timeout=self._timeout)

    @staticmethod
    def _normalizar_estado(estado: Any) -> str:
        """
        Normaliza o estado removendo metadados voláteis (timestamp/lider_id) para
        comparar apenas os dados oficiais de domínio durante a votação.
        """
        if not isinstance(estado, dict):
            return str(estado)

        chaves_dominio = ("temperatura", "umidade", "bomba_ligada", "exaustor_ligado")
        if any(k in estado for k in chaves_dominio):
            canonico = {
                "temperatura": estado.get("temperatura"),
                "umidade": estado.get("umidade"),
                "bomba_ligada": bool(estado.get("bomba_ligada", False)),
                "exaustor_ligado": bool(estado.get("exaustor_ligado", False)),
            }
            return json.dumps(canonico, sort_keys=True)

        copia = {
            k: v
            for k, v in estado.items()
            if k not in ("ultima_atualizacao", "controlador_id", "lider_id", "byzantino")
        }
        return json.dumps(copia, sort_keys=True)

    # Consenso dinâmico: 3 nós (maioria 2/3 mascara 1 bizantino), 2 nós (2/2), 1 nó (1/1 degradado)
    @classmethod
    def calcular_consenso(
        cls,
        respostas: list[dict],
        total_ativos: int | None = None,
    ) -> dict:
        """
        Aplica quórum dinâmico sobre as respostas recebidas dos nós ativos:
        - 3 ativos: maioria (>= 2 votos) mascara 1 nó bizantino.
        - 2 ativos: exige concordância (2/2); divergência levanta ErroQuorum.
        - 1 ativo: modo degradado (1/1) preserva disponibilidade do sistema.
        - 0 ativos: levanta ErroQuorum.
        """
        if not respostas:
            raise ErroQuorum("ERRO_QUORUM: Nenhum controlador ativo respondeu.")

        contagem = collections.Counter(cls._normalizar_estado(r) for r in respostas)
        chave_vencedora, votos = contagem.most_common(1)[0]
        n_respostas = len(respostas) if total_ativos is None else max(len(respostas), total_ativos)

        if n_respostas >= 3 and votos < 2:
            raise ErroQuorum(
                f"ERRO_QUORUM: Divergência total entre os {len(respostas)} controladores ativos."
            )
        if n_respostas == 2 and votos < 2:
            raise ErroQuorum(
                "ERRO_QUORUM: Conflito entre os 2 controladores ativos (sem desempate)."
            )

        for resposta in respostas:
            if cls._normalizar_estado(resposta) == chave_vencedora:
                return dict(resposta)

        raise ErroQuorum("ERRO_QUORUM: Falha inesperada ao apurar consenso.")

    def _ordenar_candidatos(self) -> list[dict]:
        """Prioriza o último líder conhecido e, em seguida, os nós de maior rank."""
        por_rank = sorted(self._controladores, key=lambda c: c["rank"], reverse=True)
        if not self._lider_atual:
            return por_rank
        lider_id = self._lider_atual.get("id")
        restantes = [c for c in por_rank if c["id"] != lider_id]
        return [self._lider_atual] + restantes

    def _atualizar_lider_cache(self, resposta: Any) -> None:
        """Atualiza o cache de líder local a partir de respostas retornadas pelo cluster."""
        if not isinstance(resposta, dict):
            return
        lider_id = resposta.get("lider_id")
        if not lider_id:
            return
        for ctrl in self._controladores:
            if ctrl["id"] == lider_id:
                self._lider_atual = ctrl
                return

    # Comunicação direta Cliente -> Controladores com failover automático em queda ou timeout
    def _chamar_com_failover(self, metodo: str, *args) -> Any:
        """
        Executa uma chamada XML-RPC diretamente contra o líder ou réplica ativa,
        migrando automaticamente para o próximo controlador em caso de falha ou timeout.
        """
        erros = []
        for ctrl in self._ordenar_candidatos():
            try:
                proxy = self._criar_proxy(ctrl)
                func = getattr(proxy, metodo)
                resposta = func(*args)
                self._atualizar_lider_cache(resposta)
                return resposta
            except xmlrpc.client.Fault as e:
                if "ERRO_QUORUM" in str(e.faultString):
                    raise ErroQuorum(e.faultString) from e
                erros.append((ctrl["id"], e.faultString))
                print(f"[MIDDLEWARE] Falha lógica em {ctrl['id']}: {e.faultString}")
            except (
                ConnectionRefusedError,
                TimeoutError,
                socket.timeout,
                OSError,
                xmlrpc.client.ProtocolError,
            ) as e:
                erros.append((ctrl["id"], str(e)))
                if self._lider_atual and self._lider_atual["id"] == ctrl["id"]:
                    self._lider_atual = None
                print(
                    f"[MIDDLEWARE] Failover: {ctrl['id']} ({ctrl['host']}:{ctrl['port']}) "
                    f"indisponível ({e}). Tentando próximo controlador..."
                )

        raise ErroQuorum(f"ERRO_QUORUM: Nenhum controlador acessível. Detalhes: {erros}")

    # Consulta paralela a todas as réplicas ativas para validar estado oficial por consenso
    def obter_estado(self) -> dict:
        """
        Consulta diretamente todos os controladores alcançáveis em paralelo e valida
        o estado oficial por consenso dinâmico (mascarando eventuais nós bizantinos).
        """
        if not self._controladores:
            raise ErroQuorum("ERRO_QUORUM: Nenhum controlador configurado.")

        respostas: list[dict] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(self._controladores))
        futures = {
            executor.submit(lambda c: self._criar_proxy(c).obter_estado(), ctrl): ctrl
            for ctrl in self._controladores
        }
        try:
            for future in concurrent.futures.as_completed(futures, timeout=self._timeout + 0.3):
                ctrl = futures[future]
                try:
                    resp = future.result(timeout=0.1)
                    if isinstance(resp, dict):
                        respostas.append(resp)
                except Exception as e:
                    print(f"[MIDDLEWARE] {ctrl['id']} indisponível na leitura: {e}")
        except (concurrent.futures.TimeoutError, TimeoutError):
            print("[MIDDLEWARE] Timeout aguardando réplicas lentas na consulta de estado.")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        oficial = self.calcular_consenso(respostas)
        self._atualizar_lider_cache(oficial)
        return oficial

    def comandar_bomba(self, ligar: bool) -> dict:
        """Envia comando booleano da bomba diretamente ao cluster com failover automático."""
        if not isinstance(ligar, bool):
            raise ValueError("O parâmetro 'ligar' deve ser booleano (True ou False).")
        return self._chamar_com_failover("comandar_bomba", ligar)

    def comandar_exaustor(self, ligar: bool) -> dict:
        """Envia comando booleano do exaustor diretamente ao cluster com failover automático."""
        if not isinstance(ligar, bool):
            raise ValueError("O parâmetro 'ligar' deve ser booleano (True ou False).")
        return self._chamar_com_failover("comandar_exaustor", ligar)

    def verificar_saude(self) -> dict:
        """Verifica conectividade e papel (líder/seguidor) de cada controlador do cluster."""
        detalhes = {}
        ativos = 0
        votos_lider = []

        for ctrl in self._controladores:
            try:
                proxy = self._criar_proxy(ctrl)
                resp = proxy.ping()
                ativos += 1
                if isinstance(resp, dict) and resp.get("status") == "ok":
                    lider_id = resp.get("lider_id")
                    if lider_id:
                        votos_lider.append(lider_id)
                    papel = "LÍDER" if lider_id == ctrl["id"] else "seguidor"
                    detalhes[ctrl["id"]] = f"ok ({papel})"
                elif "pong" in str(resp):
                    detalhes[ctrl["id"]] = "ok"
                else:
                    detalhes[ctrl["id"]] = f"resposta inesperada: {resp}"
            except Exception as e:
                detalhes[ctrl["id"]] = f"OFFLINE: {e}"

        lider_cluster = (
            collections.Counter(votos_lider).most_common(1)[0][0]
            if votos_lider
            else None
        )
        if lider_cluster:
            for ctrl in self._controladores:
                if ctrl["id"] == lider_cluster:
                    self._lider_atual = ctrl
                    break

        return {
            "ativos": ativos,
            "total": len(self._controladores),
            "lider_id": lider_cluster,
            "detalhes": detalhes,
        }


# Alias de compatibilidade
Middleware = ClusterMiddleware
