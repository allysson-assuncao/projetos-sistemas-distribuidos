"""
sensor.py — Processo Sensor da Estufa.

Simula dois sensores físicos em malha fechada:
  - Sensor de Temperatura (ºC)
  - Sensor de Umidade do Solo (%)

Publica leituras no broker MQTT nos tópicos definidos em config.py e assina
os tópicos de status dos atuadores (`estufa/status/bomba` e `estufa/status/exaustor`)
para refletir em tempo real o efeito da bomba de irrigação e do exaustor nas
próximas leituras geradas.

Uso:
    python -m estufa.sensor [--intervalo SEGUNDOS] [--modo {normal,seco,quente,frio}]
"""

import argparse
import json
import random
import threading
import time
import paho.mqtt.client as mqtt
from estufa import config


# Perfis de simulação: faixas iniciais e deriva ambiental natural (sem atuadores)
PERFIS = {
    "normal": {
        "temp": (23.0, 28.0),
        "umidade": (42.0, 58.0),
        "deriva_temp": (-0.3, 0.7),
        "deriva_umidade": (-1.8, -0.4),
    },
    "seco": {
        "temp": (26.0, 32.0),
        "umidade": (18.0, 27.0),       # inicia abaixo de 30% -> dispara bomba
        "deriva_temp": (-0.2, 0.6),
        "deriva_umidade": (-3.5, -1.5),
    },
    "quente": {
        "temp": (36.0, 40.0),          # inicia acima de 35°C -> dispara exaustor
        "umidade": (38.0, 52.0),
        "deriva_temp": (1.0, 2.5),
        "deriva_umidade": (-2.0, -0.8),
    },
    "frio": {
        "temp": (10.0, 14.0),
        "umidade": (55.0, 68.0),
        "deriva_temp": (-0.8, 0.2),
        "deriva_umidade": (-0.6, 0.4),
    },
}

EFEITO_BOMBA_UMIDADE = (5.0, 8.0)
EFEITO_EXAUSTOR_TEMP = (-3.5, -2.0)
TEMP_LIMITE_MIN = 0.0
TEMP_LIMITE_MAX = 55.0
UMIDADE_LIMITE_MIN = 0.0
UMIDADE_LIMITE_MAX = 100.0


class SimuladorAmbiente:
    """Mantém o estado físico simulado da estufa considerando feedback dos atuadores."""

    def __init__(self, perfil: str = "normal"):
        self.perfil = perfil if perfil in PERFIS else "normal"
        self._cfg = PERFIS[self.perfil]
        self.temperatura = round(random.uniform(*self._cfg["temp"]), 2)
        self.umidade = round(random.uniform(*self._cfg["umidade"]), 2)
        self.bomba_ligada = False
        self.exaustor_ligado = False
        self._primeira_leitura = True
        self._lock = threading.Lock()

    def atualizar_atuador(self, atuador: str, ligado: bool) -> None:
        """Atualiza o estado conhecido de um atuador a partir de feedback MQTT."""
        with self._lock:
            if atuador == "bomba":
                self.bomba_ligada = bool(ligado)
            elif atuador == "exaustor":
                self.exaustor_ligado = bool(ligado)

    def proxima_leitura(self) -> tuple[float, float]:
        """
        Retorna a próxima dupla (temperatura, umidade) aplicando o efeito dos
        atuadores ativos ou a deriva natural do perfil selecionado.
        """
        with self._lock:
            if self._primeira_leitura:
                self._primeira_leitura = False
                return self.temperatura, self.umidade

            if self.exaustor_ligado:
                delta_temp = random.uniform(*EFEITO_EXAUSTOR_TEMP)
            else:
                delta_temp = random.uniform(*self._cfg["deriva_temp"])

            if self.bomba_ligada:
                delta_umidade = random.uniform(*EFEITO_BOMBA_UMIDADE)
            else:
                delta_umidade = random.uniform(*self._cfg["deriva_umidade"])

            self.temperatura = round(
                max(TEMP_LIMITE_MIN, min(TEMP_LIMITE_MAX, self.temperatura + delta_temp)),
                2,
            )
            self.umidade = round(
                max(UMIDADE_LIMITE_MIN, min(UMIDADE_LIMITE_MAX, self.umidade + delta_umidade)),
                2,
            )
            return self.temperatura, self.umidade


def _criar_cliente_mqtt(client_id: str) -> mqtt.Client:
    """Cria e conecta um cliente MQTT ao broker configurado."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    return client


def _configurar_callbacks_feedback(
    client: mqtt.Client,
    simulador: SimuladorAmbiente,
    evento_inscrito: threading.Event,
) -> None:
    """Registra callbacks MQTT para receber o estado real da bomba e do exaustor."""
    subs_confirmadas = {"count": 0}

    def on_connect(cli, userdata, flags, reason_code, properties):
        if reason_code == 0:
            cli.subscribe(config.TOPIC_STATUS_BOMBA, qos=1)
            cli.subscribe(config.TOPIC_STATUS_EXAUSTOR, qos=1)

    def on_subscribe(cli, userdata, mid, reason_code_list, properties):
        subs_confirmadas["count"] += 1
        if subs_confirmadas["count"] >= 2:
            evento_inscrito.set()

    def on_message(cli, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        atuador = payload.get("atuador")
        if atuador not in ("bomba", "exaustor") or "ligado" not in payload:
            return

        ligado = bool(payload["ligado"])
        simulador.atualizar_atuador(atuador, ligado)
        estado_txt = (
            ("LIGADA" if ligado else "DESLIGADA")
            if atuador == "bomba"
            else ("LIGADO" if ligado else "DESLIGADO")
        )
        print(
            f"[SENSOR] Feedback atuador: {atuador} -> {estado_txt} "
            f"(ajustando próximas leituras)"
        )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message


def publicar_leitura(client: mqtt.Client, topico: str, valor: float, unidade: str) -> None:
    """Publica uma leitura de sensor em formato JSON no tópico MQTT."""
    payload = json.dumps({
        "valor": round(valor, 2),
        "unidade": unidade,
        "timestamp": time.time(),
    })
    result = client.publish(topico, payload, qos=1)
    result.wait_for_publish()
    print(f"[SENSOR] {topico}: {payload}")


def executar_sensor(
    intervalo: float = 2.0,
    perfil: str = "normal",
    max_iteracoes: int = None,
    espera_subscricao: float = 1.0,
):
    """
    Loop principal do sensor com retroalimentação dos atuadores.

    Args:
        intervalo: Intervalo entre publicações em segundos.
        perfil: Um dos perfis em PERFIS (normal, seco, quente, frio).
        max_iteracoes: Se definido, encerra após N publicações (útil para testes).
        espera_subscricao: Tempo máximo (s) aguardando confirmação das assinaturas de status.
    """
    simulador = SimuladorAmbiente(perfil=perfil)
    evento_inscrito = threading.Event()
    client = _criar_cliente_mqtt("sensor_estufa")
    _configurar_callbacks_feedback(client, simulador, evento_inscrito)
    client.loop_start()
    evento_inscrito.wait(timeout=espera_subscricao)

    iteracao = 0

    try:
        while True:
            temperatura, umidade = simulador.proxima_leitura()

            publicar_leitura(client, config.TOPIC_TEMPERATURA, temperatura, "°C")
            publicar_leitura(client, config.TOPIC_UMIDADE_SOLO, umidade, "%")

            iteracao += 1
            if max_iteracoes is not None and iteracao >= max_iteracoes:
                break

            time.sleep(intervalo)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensor da Estufa Agrícola")
    parser.add_argument("--intervalo", type=float, default=2.0,
                        help="Intervalo entre publicações (segundos)")
    parser.add_argument("--modo", choices=list(PERFIS.keys()), default="normal",
                        help="Perfil de simulação")
    args = parser.parse_args()
    executar_sensor(intervalo=args.intervalo, perfil=args.modo)
