"""
sub_alarme.py — Subscriber: Central de Alarme da Casa.

Assina:
    - casa/frente/porta   (eventos de abertura/fechamento)
    - casa/status/sensores (LWT: aviso de sensor offline)

Uso:
    python sub_alarme.py --qos 1
    python sub_alarme.py --qos 2 --output alarme_qos2.csv
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


# ─── Estado compartilhado entre callbacks ─────────────────────────────────────
state = {
    "csv_writer": None,
    "csv_file":   None,
    "qos":        1,
    "seq_esperado": 0,
    "perdas":     0,
    "total":      0,
}


# ─── Callbacks ────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[ALARME] Conectado ao broker.")
        client.subscribe(config.TOPIC_PORTA,  qos=state["qos"])
        client.subscribe(config.TOPIC_STATUS, qos=1)
        print(f"[ALARME] Inscrito em: {config.TOPIC_PORTA} e {config.TOPIC_STATUS} | QoS={state['qos']}")
    else:
        print(f"[ALARME] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_message(client, userdata, msg):
    ts_chegada = datetime.now(timezone.utc).isoformat()
    state["total"] += 1

    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[ALARME] ⚠️  Payload inválido recebido em {msg.topic}")
        return
    except Exception as e:
        print(f"[ALARME] ⚠️  Erro inesperado no processamento do payload: {e}")
        return

    # O uso do dict.get() garante robustez caso as chaves não existam no JSON
    seq  = payload.get("seq", -1)
    dado = payload.get("dado", "?")
    id_  = payload.get("id", "?")

    # ── Detecção de LWT (sensor offline) ────────────────────────────────────
    if msg.topic == config.TOPIC_STATUS and dado == "OFFLINE":
        print(f"\n[ALARME] 🚨 ALERTA CRÍTICO: Sensor '{id_}' ficou OFFLINE (LWT recebido)!")
        print(f"[ALARME] 🚨 Verifique o sensor imediatamente!\n")
        state["csv_writer"].writerow([
            seq, ts_chegada, dado, msg.topic, msg.qos, True, "LWT_RECEBIDO"
        ])
        state["csv_file"].flush()
        return

    # ── Detecção de perda por número de sequência ────────────────────────────
    observacao = "OK"
    if msg.topic == config.TOPIC_PORTA and seq != -1:
        if seq > state["seq_esperado"]:
            perdidas = seq - state["seq_esperado"]
            state["perdas"] += perdidas
            observacao = f"PERDA_SEQ_{state['seq_esperado']}_a_{seq - 1}"
            print(f"[ALARME] ⚠️  {perdidas} mensagem(ns) perdida(s)! Esperado seq={state['seq_esperado']}, recebido seq={seq}")
        elif seq < state["seq_esperado"]:
            observacao = f"DUPLICATA_seq_{seq}"
            print(f"[ALARME] 🔁 Duplicata detectada! seq={seq}")
            
        # Atualiza o esperado apenas se avançou na sequência (evita retroceder com duplicatas)
        state["seq_esperado"] = max(state["seq_esperado"], seq + 1)

    # ── Alerta de porta ──────────────────────────────────────────────────────
    icone = "🔓" if dado == "Aberta" else "🔒"
    print(f"[ALARME] {icone} seq={seq:03d} | Porta={dado:8s} | QoS={msg.qos} | {ts_chegada}")

    state["csv_writer"].writerow([
        seq, ts_chegada, dado, msg.topic, msg.qos, msg.retain, observacao
    ])
    state["csv_file"].flush()


def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"[ALARME] Desconectado. Código: {reason_code}")


# ─── Função principal ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Subscriber: Central de Alarme")
    parser.add_argument("--qos",     type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--output",  type=str, default=None,
                        help="Nome do arquivo CSV de saída (opcional)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Tempo máximo de execução em segundos (default: 120)")
    args = parser.parse_args()

    state["qos"] = args.qos

    # ── CSV ──────────────────────────────────────────────────────────────────
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_name   = args.output or f"sub_alarme_qos{args.qos}.csv"
    csv_path   = results_dir / csv_name
    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_chegada", "dado", "topic", "qos", "retained", "observacao"])

    state["csv_file"]   = csv_file
    state["csv_writer"] = csv_writer

    # ── Cliente MQTT ─────────────────────────────────────────────────────────
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sub_alarme_qos{args.qos}"
    )
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)

    print(f"[ALARME] Aguardando mensagens por {args.timeout}s... (Ctrl+C para parar)")
    try:
        client.loop_start()
        time.sleep(args.timeout)
    except KeyboardInterrupt:
        print("\n[ALARME] Encerrado pelo usuário.")
    finally:
        client.loop_stop()
        client.disconnect()
        csv_file.close()
        print(f"\n[ALARME] ─── RESUMO ───────────────────────────────────────────")
        print(f"[ALARME] Total recebido : {state['total']}")
        print(f"[ALARME] Perdas (seq)   : {state['perdas']}")
        print(f"[ALARME] Log salvo em   : {csv_path}")


if __name__ == "__main__":
    main()
