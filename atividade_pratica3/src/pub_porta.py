"""
pub_porta.py — Publisher do sensor de segurança da porta da frente.

Uso:
    python pub_porta.py --qos 1 --count 60
    python pub_porta.py --qos 2 --count 60 --interval 3.0

Funcionalidades especiais:
    - LWT: Se o processo morrer abruptamente, o broker publica a mensagem
      de "sensor offline" automaticamente em casa/status/sensores.
    - Retained: O último estado da porta fica retido no broker.
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).parent))
import config


# Callbacks
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[PORTA] Conectado ao broker {config.BROKER_HOST}:{config.BROKER_PORT}")
        print(f"[PORTA] LWT configurado em: {config.TOPIC_STATUS}")
    else:
        print(f"[PORTA] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_publish(client, userdata, mid, reason_code, properties):
    print(f"[PORTA] ACK recebido para MID={mid}")


# Função principal
def main():
    parser = argparse.ArgumentParser(description="Publisher: Sensor de Porta com LWT e Retained")
    parser.add_argument("--qos",      type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--count",    type=int, default=60)
    parser.add_argument("--interval", type=float, default=config.PUBLISH_INTERVAL_PORTA)
    parser.add_argument("--simulate-crash", action="store_true",
                        help="Simula falha abrupta após metade das mensagens (para testar LWT)")
    args = parser.parse_args()

    # CSV
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path   = results_dir / f"qos{args.qos}_porta.csv"
    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_pub", "dado", "qos", "topic", "mid", "retained"])

    # Configuração MQTT com LWT
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"pub_porta_qos{args.qos}"
    )
    client.on_connect = on_connect
    client.on_publish = on_publish

    # Configurar LWT ANTES de conectar
    client.will_set(
        topic   = config.TOPIC_STATUS,
        payload = config.LWT_PORTA_PAYLOAD,
        qos     = 1,
        retain  = True,
    )

    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)
    client.loop_start()
    time.sleep(0.5)

    # Loop de publicação
    estados   = ["Aberta", "Fechada"]
    estado    = "Fechada"
    seq       = 0
    crash_seq = args.count // 2 if args.simulate_crash else -1

    print(f"[PORTA] Iniciando publicação de {args.count} mensagens com QoS {args.qos}...")
    if args.simulate_crash:
        print(f"[PORTA] Simulação de crash ativada na seq={crash_seq}")

    try:
        for seq in range(args.count):
            # Simula crash abrupto (sem disconnect() — LWT será disparado)
            if seq == crash_seq:
                print(f"\n[PORTA] *** SIMULANDO CRASH na seq={seq} — processo morto abruptamente ***")
                csv_file.close()
                client.loop_stop()
                # NÃO chama disconnect() para que o broker dispare o LWT
                os._exit(1)

            # Alterna estado de forma aleatória com 30% de chance de mudança
            if random.random() < 0.3:
                estado = "Aberta" if estado == "Fechada" else "Fechada"

            timestamp = datetime.now(timezone.utc).isoformat()
            payload   = {
                "id":        config.ID_SENSOR_PORTA,
                "seq":       seq,
                "timestamp": timestamp,
                "dado":      estado,
                "qos_used":  args.qos,
            }

            result = client.publish(
                topic   = config.TOPIC_PORTA,
                payload = json.dumps(payload),
                qos     = args.qos,
                retain  = True,   # Retained: novo subscriber recebe o último estado
            )

            print(f"[PORTA] seq={seq:03d} | Estado={estado:8s} | QoS={args.qos} | MID={result.mid}")
            csv_writer.writerow([seq, timestamp, estado, args.qos, config.TOPIC_PORTA, result.mid, True])

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[PORTA] Publicação interrompida pelo usuário (graceful).")
    finally:
        # Desconexão limpa (LWT NÃO é disparado neste caminho)
        try:
            csv_file.close()
        except Exception:
            pass
        client.loop_stop()
        client.disconnect()
        print(f"[PORTA] Publicação encerrada. Total: {seq + 1} mensagens. Log: {csv_path}")


if __name__ == "__main__":
    main()
