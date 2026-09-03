"""
sub_dashboard.py — Subscriber: Dashboard Global da Casa Inteligente.

Uso:
    python sub_dashboard.py --qos 0
    python sub_dashboard.py --qos 1 --timeout 120
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).parent))
import config

WILDCARD_TOPIC = "casa/#"

state = {
    "csv_writer":    None,
    "csv_file":      None,
    "qos":           0,
    "total":         0,
    "retained_recv": 0,
    "por_topico":    {},
}


# Callbacks
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[DASH] Conectado ao broker.")
        client.subscribe(WILDCARD_TOPIC, qos=state["qos"])
        print(f"[DASH] Inscrito em: {WILDCARD_TOPIC} | QoS={state['qos']}")
        print(f"[DASH] ═══════════════════════════════════════════════════")
        print(f"[DASH]        🏠 DASHBOARD — CASA INTELIGENTE            ")
        print(f"[DASH] ═══════════════════════════════════════════════════")
    else:
        print(f"[DASH] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_message(client, userdata, msg):
    ts_chegada = datetime.now(timezone.utc).isoformat()
    state["total"] += 1
    state["por_topico"][msg.topic] = state["por_topico"].get(msg.topic, 0) + 1

    if msg.retain:
        state["retained_recv"] += 1

    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[DASH] ⚠️ Payload inválido recebido em {msg.topic}")
        return
    except Exception as e:
        print(f"[DASH] ⚠️ Erro inesperado no processamento do payload: {e}")
        return

    # O uso do dict.get() garante robustez caso as chaves não existam no JSON
    dado      = payload.get("dado", "?")
    seq       = payload.get("seq", -1)
    unidade   = payload.get("unidade", "")
    retained_flag = "📌 RETAINED" if msg.retain else ""

    # Display formatado por tópico
    if msg.topic == config.TOPIC_TEMPERATURA:
        print(f"[DASH] 🌡️  Temperatura: {dado}{unidade:3s} | seq={seq:03d} | QoS={msg.qos} {retained_flag}")
    elif msg.topic == config.TOPIC_PORTA:
        icone = "🔓" if dado == "Aberta" else "🔒"
        print(f"[DASH] {icone} Porta: {dado:8s} | seq={seq:03d} | QoS={msg.qos} {retained_flag}")
    elif msg.topic == config.TOPIC_STATUS:
        print(f"[DASH] 🚨 STATUS SISTEMA: {dado} | seq={seq} | QoS={msg.qos} {retained_flag}")
    else:
        print(f"[DASH] ❓ Tópico Desconhecido: {msg.topic} | Dado={dado} | seq={seq} {retained_flag}")

    state["csv_writer"].writerow([
        seq, ts_chegada, msg.topic, dado, msg.qos, msg.retain
    ])
    state["csv_file"].flush()


def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"\n[DASH] Desconectado. Código: {reason_code}")


# Função principal
def main():
    parser = argparse.ArgumentParser(description="Subscriber: Dashboard Global")
    parser.add_argument("--qos",     type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    state["qos"] = args.qos

    # CSV
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path   = results_dir / f"sub_dashboard_qos{args.qos}.csv"
    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_chegada", "topic", "dado", "qos", "retained"])

    state["csv_file"]   = csv_file
    state["csv_writer"] = csv_writer

    # Cliente
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sub_dashboard_qos{args.qos}"
    )
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)

    try:
        client.loop_start()
        time.sleep(args.timeout)
    except KeyboardInterrupt:
        print("\n[DASH] Encerrado pelo usuário.")
    finally:
        client.loop_stop()
        client.disconnect()
        csv_file.close()
        print(f"\n[DASH] ─── RESUMO DASHBOARD ──────────────────────────────────")
        print(f"[DASH] Total recebido : {state['total']}")
        print(f"[DASH] Retained flags : {state['retained_recv']}")
        for k, v in state["por_topico"].items():
            print(f"[DASH]   - {k}: {v}")
        print(f"[DASH] Log salvo em   : {csv_path}")


if __name__ == "__main__":
    main()
