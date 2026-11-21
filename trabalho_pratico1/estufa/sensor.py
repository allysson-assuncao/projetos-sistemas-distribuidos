"""
sensor.py — Processo Sensor da Estufa em malha fechada contínua.

Publica leituras periódicas de temperatura (°C) e umidade do solo (%) via MQTT
e assina os tópicos de status da bomba e do exaustor para ajustar as próximas
leituras de forma contínua e determinística.

Uso:
    python -m estufa.sensor
    python -m estufa.sensor --temp 37.0 --umidade 25.0 --intervalo 2.0
"""

import argparse
import json
import time
import paho.mqtt.client as mqtt
from estufa import config

TEMP_LIMITE_MIN = 0.0
TEMP_LIMITE_MAX = 55.0
UMIDADE_LIMITE_MIN = 0.0
UMIDADE_LIMITE_MAX = 100.0


class SimuladorAmbiente:
    """Simula a evolução física da estufa em malha fechada conforme os atuadores."""

    def __init__(self, temp_inicial: float = 28.0, umidade_inicial: float = 42.0):
        if isinstance(temp_inicial, bool) or not (-50.0 <= float(temp_inicial) <= 100.0):
            raise ValueError(f"Temperatura inicial inválida: {temp_inicial} (esperado: -50..100).")
        if isinstance(umidade_inicial, bool) or not (0.0 <= float(umidade_inicial) <= 100.0):
            raise ValueError(f"Umidade inicial inválida: {umidade_inicial} (esperado: 0..100).")

        self.temperatura = round(float(temp_inicial), 2)
        self.umidade = round(float(umidade_inicial), 2)
        self.bomba_ligada = False
        self.exaustor_ligado = False

    def atualizar_atuador(self, atuador: str, ligado: bool) -> None:
        """Atualiza o estado conhecido do atuador a partir do feedback MQTT."""
        if atuador == "bomba":
            self.bomba_ligada = bool(ligado)
        elif atuador == "exaustor":
            self.exaustor_ligado = bool(ligado)

    def proxima_leitura(self) -> tuple[float, float]:
        """Calcula a próxima leitura com passos fixos (+2.0/-2.5°C e -3.0/+6.0%)."""
        delta_temp = -2.5 if self.exaustor_ligado else 2.0
        delta_umidade = 6.0 if self.bomba_ligada else -3.0

        self.temperatura = round(
            max(TEMP_LIMITE_MIN, min(TEMP_LIMITE_MAX, self.temperatura + delta_temp)),
            2,
        )
        self.umidade = round(
            max(UMIDADE_LIMITE_MIN, min(UMIDADE_LIMITE_MAX, self.umidade + delta_umidade)),
            2,
        )
        return self.temperatura, self.umidade


# Inscrição MQTT nos tópicos de status com QoS 1 para fechar a malha do simulador
def _on_connect(client, userdata, flags, reason_code, properties) -> None:
    if reason_code == 0:
        client.subscribe(config.TOPIC_STATUS_BOMBA, qos=1)
        client.subscribe(config.TOPIC_STATUS_EXAUSTOR, qos=1)
        print("[SENSOR] Conectado ao broker MQTT. Assinando feedback dos atuadores.")
    else:
        print(f"[SENSOR] Falha na conexão MQTT: {reason_code}")


# Callback de recepção MQTT: atualiza bomba/exaustor e ignora payloads malformados
def _on_message(client, userdata, msg) -> None:
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(payload, dict):
        return

    atuador = payload.get("atuador")
    if atuador not in ("bomba", "exaustor") or "ligado" not in payload:
        return

    ligado = bool(payload["ligado"])
    userdata.atualizar_atuador(atuador, ligado)
    print(f"[SENSOR] Feedback recebido: {atuador} -> {'ON' if ligado else 'OFF'}")


def publicar_leitura(client: mqtt.Client, topico: str, valor: float, unidade: str) -> None:
    """Publica leitura JSON no tópico MQTT com entrega garantida (QoS 1)."""
    payload = json.dumps({
        "valor": round(valor, 2),
        "unidade": unidade,
        "timestamp": time.time(),
    })
    # QoS 1 garante que todos os controladores recebam a leitura sem perdas silenciosas
    info = client.publish(topico, payload, qos=1)
    info.wait_for_publish()
    print(f"[SENSOR] {topico}: {valor:.2f}{unidade}")


def executar_sensor(
    temp_inicial: float = 28.0,
    umidade_inicial: float = 42.0,
    intervalo: float = 2.0,
    max_iteracoes: int | None = None,
) -> None:
    """Inicia o cliente MQTT (callbacks antes do connect) e publica leituras contínuas."""
    if isinstance(intervalo, bool) or float(intervalo) <= 0.05:
        raise ValueError(f"Intervalo inválido: {intervalo} (deve ser maior que 0.05s).")

    simulador = SimuladorAmbiente(temp_inicial=temp_inicial, umidade_inicial=umidade_inicial)
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="sensor_estufa",
        userdata=simulador,
    )
    # Callbacks registrados antes do connect() evitam perder SUBACK/mensagens iniciais
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    client.loop_start()

    iteracao = 0
    try:
        while True:
            temperatura, umidade = simulador.proxima_leitura()
            publicar_leitura(client, config.TOPIC_TEMPERATURA, temperatura, "°C")
            publicar_leitura(client, config.TOPIC_UMIDADE_SOLO, umidade, "%")

            iteracao += 1
            if max_iteracoes is not None and iteracao >= max_iteracoes:
                break
            time.sleep(float(intervalo))
    except KeyboardInterrupt:
        print("\n[SENSOR] Encerrando sensor.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensor Contínuo da Estufa Agrícola")
    parser.add_argument("--temp", type=float, default=28.0, help="Temperatura inicial (°C, -50..100)")
    parser.add_argument("--umidade", type=float, default=42.0, help="Umidade inicial (%%, 0..100)")
    parser.add_argument("--intervalo", type=float, default=2.0, help="Intervalo entre leituras (> 0.05s)")
    args = parser.parse_args()

    executar_sensor(
        temp_inicial=args.temp,
        umidade_inicial=args.umidade,
        intervalo=args.intervalo,
    )
