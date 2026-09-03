"""
pub_temperatura.py — Publisher do sensor de temperatura da sala.

Uso:
    python pub_temperatura.py --qos 0 --count 60
    python pub_temperatura.py --qos 1 --count 60 --interval 1.0
"""

import argparse
import csv
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

# Adiciona o diretório pai ao path para importar config
sys.path.insert(0, str(Path(__file__).parent))
import config


# Callbacks
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[TEMP] Conectado ao broker {config.BROKER_HOST}:{config.BROKER_PORT}")
    else:
        print(f"[TEMP] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_publish(client, userdata, mid, reason_code, properties):
    print(f"[TEMP] ACK recebido para MID={mid}")


# Função principal
def main():
    parser = argparse.ArgumentParser(description="Publisher: Sensor de Temperatura")
    parser.add_argument("--qos",      type=int, default=0, choices=[0, 1, 2],
                        help="Nível de QoS para publicação (default: 0)")
    parser.add_argument("--count",    type=int, default=60,
                        help="Número de mensagens a publicar (default: 60)")
    parser.add_argument("--interval", type=float, default=config.PUBLISH_INTERVAL_TEMP,
                        help="Intervalo em segundos entre publicações (default: 1.0)")
    args = parser.parse_args()

    # Configuração do CSV de saída
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / f"qos{args.qos}_temperatura.csv"

    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_pub", "dado", "qos", "topic", "mid"])

    # Configuração do cliente MQTT
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"pub_temperatura_qos{args.qos}"
    )
    client.on_connect = on_connect
    client.on_publish = on_publish

    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)
    client.loop_start()

    time.sleep(0.5)  # aguarda conexão estabilizar

    # Loop de publicação
    temperatura_base = 24.0
    seq = 0

    print(f"[TEMP] Iniciando publicação de {args.count} mensagens com QoS {args.qos}...")

    try:
        for seq in range(args.count):
            temperatura = round(temperatura_base + random.gauss(0, 1.5), 2)
            timestamp   = datetime.now(timezone.utc).isoformat()

            payload = {
                "id":        config.ID_SENSOR_TEMP,
                "seq":       seq,
                "timestamp": timestamp,
                "dado":      temperatura,
                "unidade":   "°C",
                "qos_used":  args.qos,
            }

            result = client.publish(
                topic   = config.TOPIC_TEMPERATURA,
                payload = json.dumps(payload),
                qos     = args.qos,
                retain  = False,
            )

            print(f"[TEMP] seq={seq:03d} | {temperatura}°C | QoS={args.qos} | MID={result.mid}")
            csv_writer.writerow([seq, timestamp, temperatura, args.qos, config.TOPIC_TEMPERATURA, result.mid])

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[TEMP] Publicação interrompida pelo usuário.")
    finally:
        csv_file.close()
        client.loop_stop()
        client.disconnect()
        print(f"[TEMP] Publicação encerrada. Total: {seq + 1} mensagens. Log: {csv_path}")


if __name__ == "__main__":
    main()
