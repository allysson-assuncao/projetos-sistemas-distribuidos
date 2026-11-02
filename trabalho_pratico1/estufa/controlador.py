"""
controlador.py — Processo Controlador replicado do sistema da estufa agrícola.

Responsabilidades:
  1. Transferência de estado no boot via consulta ao servidor de Middleware.
  2. Subscrição MQTT aos tópicos de temperatura e umidade do solo.
  3. Avaliação autônoma de regras de controle com geração determinística de
     'comando_id' (hash MD5 da ação + timestamp da leitura do sensor).
  4. Persistência local do estado em arquivo JSON.
  5. Servidor XML-RPC interno para responder às chamadas do Middleware.

Uso:
    python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json [--byzantino]
"""

import argparse
import hashlib
import json
import os
import threading
import time
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import paho.mqtt.client as mqtt
from estufa import config


ESTADO_INICIAL = {
    "temperatura": None,
    "umidade_solo": None,
    "bomba_ligada": False,
    "exaustor_ligado": False,
    "ultima_atualizacao": None,
    "sensor_timestamp": None,
    "controlador_id": None,
}


class Controlador:
    """
    Nó controlador replicado. Utiliza lock interno para sincronizar o acesso ao
    estado entre a thread de consumo MQTT e a thread do servidor XML-RPC.
    """

    def __init__(self, ctrl_id: str, data_file: str, byzantino: bool = False):
        self.ctrl_id = ctrl_id
        self.data_file = data_file
        self.byzantino = byzantino
        self._lock = threading.Lock()
        self._mqtt_client = None

        self._estado = self._carregar_estado()
        self._estado["controlador_id"] = ctrl_id

    def _carregar_estado(self) -> dict:
        """Lê o estado persistido em disco ou retorna o estado inicial."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return dict(ESTADO_INICIAL)

    def _salvar_estado(self) -> None:
        """Persiste o estado atual no arquivo JSON local (requer lock adquirido)."""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._estado, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[{self.ctrl_id}] Erro ao salvar estado: {e}")

    def _sincronizar_estado_via_middleware(self, max_tentativas: int = 10, intervalo: float = 2.0) -> bool:
        """
        Consulta o estado aprovado por quórum no Middleware antes de iniciar o
        consumo MQTT, garantindo convergência imediata após recuperação de falha.
        """
        mw_url = f"http://{config.MIDDLEWARE_HOST}:{config.MIDDLEWARE_PORT}"
        print(f"[{self.ctrl_id}] Sincronizando estado inicial via Middleware ({mw_url})...")

        for tentativa in range(1, max_tentativas + 1):
            try:
                proxy = xmlrpc.client.ServerProxy(mw_url, allow_none=True)
                estado_majoritario = proxy.obter_estado()

                with self._lock:
                    estado_majoritario["controlador_id"] = self.ctrl_id
                    self._estado = estado_majoritario
                    self._salvar_estado()

                print(f"[{self.ctrl_id}] Estado sincronizado na tentativa {tentativa}/{max_tentativas} "
                      f"(Bomba={self._estado.get('bomba_ligada')}, "
                      f"Exaustor={self._estado.get('exaustor_ligado')}, "
                      f"Temp={self._estado.get('temperatura')}).")
                return True

            except Exception as e:
                print(f"[{self.ctrl_id}] Tentativa {tentativa}/{max_tentativas} sem quórum disponível: {e}")
                if tentativa < max_tentativas:
                    time.sleep(intervalo)

        print(f"[{self.ctrl_id}] Sincronização não concluída após {max_tentativas} tentativas. "
              f"Mantendo estado local.")
        return False

    def _decidir_atuacao(self) -> None:
        """
        Avalia os limiares de temperatura e umidade e publica comandos MQTT
        quando necessário. Gera 'comando_id' determinístico a partir da ação e
        do timestamp original do sensor para permitir deduplicação no atuador.
        """
        temp = self._estado.get("temperatura")
        umidade = self._estado.get("umidade_solo")
        sensor_ts = self._estado.get("sensor_timestamp", 0)

        def gerar_comando_id(acao_alvo: str) -> str:
            raw = f"{acao_alvo}_{sensor_ts}"
            return hashlib.md5(raw.encode("utf-8")).hexdigest()

        if temp is not None:
            if temp > config.TEMP_MAX_CELSIUS and not self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = True
                cmd_id = gerar_comando_id("exaustor_ligar")
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "ligar", cmd_id)
                print(f"[{self.ctrl_id}] Temp={temp:.1f}°C > {config.TEMP_MAX_CELSIUS}°C -> LIGAR exaustor")
            elif temp < config.TEMP_MIN_CELSIUS and self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = False
                cmd_id = gerar_comando_id("exaustor_desligar")
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "desligar", cmd_id)
                print(f"[{self.ctrl_id}] Temp={temp:.1f}°C < {config.TEMP_MIN_CELSIUS}°C -> DESLIGAR exaustor")

        if umidade is not None:
            if umidade < config.UMIDADE_MIN_PERCENT and not self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = True
                cmd_id = gerar_comando_id("bomba_ligar")
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "ligar", cmd_id)
                print(f"[{self.ctrl_id}] Umidade={umidade:.1f}% < {config.UMIDADE_MIN_PERCENT}% -> LIGAR bomba")
            elif umidade > config.UMIDADE_MAX_PERCENT and self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = False
                cmd_id = gerar_comando_id("bomba_desligar")
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "desligar", cmd_id)
                print(f"[{self.ctrl_id}] Umidade={umidade:.1f}% > {config.UMIDADE_MAX_PERCENT}% -> DESLIGAR bomba")

    def _publicar_comando(self, topico: str, acao: str, comando_id: str) -> None:
        """Publica comando para o atuador via MQTT contendo o identificador de deduplicação."""
        payload = json.dumps({
            "acao": acao,
            "origem": self.ctrl_id,
            "comando_id": comando_id,
            "timestamp": time.time(),
        })
        if self._mqtt_client:
            self._mqtt_client.publish(topico, payload, qos=1)

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
            sensor_ts = payload.get("timestamp", time.time())
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[{self.ctrl_id}] Mensagem MQTT inválida: {e}")
            return

        with self._lock:
            if msg.topic == config.TOPIC_TEMPERATURA:
                self._estado["temperatura"] = valor
                print(f"[{self.ctrl_id}] Temperatura recebida: {valor:.2f}°C")
            elif msg.topic == config.TOPIC_UMIDADE_SOLO:
                self._estado["umidade_solo"] = valor
                print(f"[{self.ctrl_id}] Umidade do solo recebida: {valor:.2f}%")

            self._estado["ultima_atualizacao"] = time.time()
            self._estado["sensor_timestamp"] = sensor_ts
            self._decidir_atuacao()
            self._salvar_estado()

    def obter_estado(self) -> dict:
        """Retorna o estado atual da réplica (ou valores adulterados se em modo bizantino)."""
        with self._lock:
            if self.byzantino:
                return {
                    "temperatura": 999.0,
                    "umidade_solo": -1.0,
                    "bomba_ligada": not self._estado.get("bomba_ligada", False),
                    "exaustor_ligado": not self._estado.get("exaustor_ligado", False),
                    "ultima_atualizacao": time.time(),
                    "sensor_timestamp": self._estado.get("sensor_timestamp"),
                    "controlador_id": self.ctrl_id,
                }
            return dict(self._estado)

    def comandar_bomba(self, acao: str, comando_id: str = "") -> dict:
        """Aciona ou desliga manualmente a bomba de irrigação."""
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {
                "sucesso": False,
                "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'.",
                "controlador_id": self.ctrl_id,
            }

        if self.byzantino:
            estado_falso = "desligada" if acao == "ligar" else "ligada"
            return {
                "sucesso": True,
                "mensagem": f"Bomba {estado_falso} com sucesso",
                "controlador_id": self.ctrl_id,
            }

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["bomba_ligada"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, acao, comando_id)
            self._salvar_estado()
            estado_texto = "ligada" if novo_estado else "desligada"
            return {
                "sucesso": True,
                "mensagem": f"Bomba {estado_texto} com sucesso",
                "controlador_id": self.ctrl_id,
            }

    def comandar_exaustor(self, acao: str, comando_id: str = "") -> dict:
        """Aciona ou desliga manualmente o exaustor."""
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {
                "sucesso": False,
                "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'.",
                "controlador_id": self.ctrl_id,
            }

        if self.byzantino:
            estado_falso = "desligado" if acao == "ligar" else "ligado"
            return {
                "sucesso": True,
                "mensagem": f"Exaustor {estado_falso} com sucesso",
                "controlador_id": self.ctrl_id,
            }

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["exaustor_ligado"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, acao, comando_id)
            self._salvar_estado()
            estado_texto = "ligado" if novo_estado else "desligado"
            return {
                "sucesso": True,
                "mensagem": f"Exaustor {estado_texto} com sucesso",
                "controlador_id": self.ctrl_id,
            }

    def ping(self) -> str:
        """Verificação de disponibilidade da réplica."""
        return f"pong:{self.ctrl_id}"

    def iniciar(self, host: str, port: int, skip_sync: bool = False) -> None:
        """
        Inicializa o controlador em três etapas:
        1. Sobe o servidor XML-RPC em thread daemon.
        2. Sincroniza o estado com o cluster via Middleware (salvo se skip_sync=True).
        3. Inicia o loop de consumo MQTT.
        """
        class SilentHandler(SimpleXMLRPCRequestHandler):
            def log_message(self, fmt, *args):
                pass

        server = SimpleXMLRPCServer(
            (host, port),
            requestHandler=SilentHandler,
            allow_none=True,
            logRequests=False,
        )
        server.register_instance(self)
        server.register_introspection_functions()

        modo = " [MODO BIZANTINO]" if self.byzantino else ""
        print(f"[{self.ctrl_id}] Servidor XML-RPC iniciado em {host}:{port}{modo}")

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        if not skip_sync:
            self._sincronizar_estado_via_middleware()
        else:
            print(f"[{self.ctrl_id}] Sincronização inicial ignorada (--skip-sync ativo).")

        self._mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"controlador_{self.ctrl_id}"
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)

        print(f"[{self.ctrl_id}] Controlador inicializado. Consumindo sensores MQTT.")
        self._mqtt_client.loop_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Controlador da Estufa")
    parser.add_argument("--id", required=True, help="Identificador da réplica (ex: ctrl_1)")
    parser.add_argument("--port", required=True, type=int, help="Porta XML-RPC")
    parser.add_argument("--data", required=True, help="Arquivo JSON de persistência")
    parser.add_argument("--host", default="localhost", help="Host do servidor XML-RPC")
    parser.add_argument("--byzantino", action="store_true", help="Ativa simulação de falha bizantina")
    parser.add_argument("--skip-sync", action="store_true", help="Ignora transferência de estado no boot")
    args = parser.parse_args()

    ctrl = Controlador(ctrl_id=args.id, data_file=args.data, byzantino=args.byzantino)
    ctrl.iniciar(host=args.host, port=args.port, skip_sync=args.skip_sync)
