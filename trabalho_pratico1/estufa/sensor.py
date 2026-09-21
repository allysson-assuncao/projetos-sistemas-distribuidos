"""
sensor.py — Processo Sensor da Estufa.

Simula dois sensores físicos:
  - Sensor de Temperatura (ºC)
  - Sensor de Umidade do Solo (%)

Publica leituras no broker MQTT nos tópicos definidos em config.py.
Pode ser executado diretamente ou importado para testes.

Uso:
    python -m estufa.sensor [--intervalo SEGUNDOS] [--modo {normal,seco,quente,frio}]
"""

import argparse
import json
import random
import time
# pyrefly: ignore [missing-import]
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────
# Perfis de simulação pré-configurados
# ─────────────────────────────────────────
PERFIS = {
    "normal": {"temp": (20.0, 30.0), "umidade": (40.0, 65.0)},
    "seco":   {"temp": (25.0, 33.0), "umidade": (10.0, 29.0)},  # dispara bomba
    "quente": {"temp": (36.0, 42.0), "umidade": (35.0, 55.0)},  # dispara exaustor
    "frio":   {"temp": (10.0, 14.0), "umidade": (50.0, 70.0)},  # nenhum atuador
}


def _criar_cliente_mqtt(client_id: str) -> mqtt.Client:
    """Cria e conecta um cliente MQTT ao broker configurado."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    return client


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


def executar_sensor(intervalo: float = 2.0, perfil: str = "normal", max_iteracoes: int = None):
    """
    Loop principal do sensor.

    Args:
        intervalo: Intervalo entre publicações em segundos.
        perfil: Um dos perfis em PERFIS (normal, seco, quente, frio).
        max_iteracoes: Se definido, encerra após N publicações (útil para testes).
    """
    client = _criar_cliente_mqtt("sensor_estufa")
    client.loop_start()

    ranges = PERFIS.get(perfil, PERFIS["normal"])
    iteracao = 0

    try:
        while True:
            temperatura = random.uniform(*ranges["temp"])
            umidade = random.uniform(*ranges["umidade"])

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
