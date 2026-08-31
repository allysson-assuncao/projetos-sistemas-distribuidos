# Plano de Implementação — AP3: Sistema MQTT Casa Inteligente

## Contexto e Decisões Técnicas

| Decisão | Escolha |
|---|---|
| Broker | Mosquitto via Docker / Docker Compose |
| Python | 3.10+ |
| Tema | Casa Inteligente (temperatura + sensor de porta) |
| Experimentos | Automatizados (script orquestrador + CSVs) |
| Relatório | Script Python gera tabela Markdown + gráficos matplotlib |
| QoS | 3 níveis (QoS 0, 1 e 2) |

> [!IMPORTANT]
> Este plano é **autossuficiente**: cada fase é executada por um agente independente sem necessidade de contexto externo. Cada fase descreve exatamente o que criar, o código completo e os comandos de validação.

---

## Estrutura de Diretórios Final

```
atividade_pratica3/
├── broker/
│   ├── docker-compose.yml
│   └── mosquitto.conf
├── src/
│   ├── config.py
│   ├── pub_temperatura.py
│   ├── pub_porta.py
│   ├── sub_alarme.py
│   └── sub_dashboard.py
├── experiments/
│   ├── run_experiment.py        # orquestrador automatizado
│   └── results/                 # CSVs gerados automaticamente
│       ├── qos0_temperatura.csv
│       ├── qos1_temperatura.csv
│       ├── qos2_temperatura.csv
│       ├── qos0_porta.csv
│       ├── qos1_porta.csv
│       └── qos2_porta.csv
├── analysis/
│   ├── analyze.py               # lê CSVs e gera tabela + gráficos
│   └── output/                  # gerado automaticamente
│       ├── tabela_resultados.md
│       ├── grafico_perdas.png
│       └── grafico_latencia.png
├── requirements.txt
└── README.md
```

---

## Taxonomia de Tópicos MQTT

```
casa/
├── sala/
│   └── temperatura          → Publisher: pub_temperatura.py
├── frente/
│   └── porta                → Publisher: pub_porta.py
└── status/
    └── sensores             → LWT automático do pub_porta.py
```

## Formato do Payload (JSON obrigatório para todos os publishers)

```json
{
  "id": "sensor_temperatura_sala",
  "seq": 42,
  "timestamp": "2026-08-31T20:00:00.000Z",
  "dado": 24.5,
  "unidade": "°C"
}
```
```json
{
  "id": "sensor_porta_frente",
  "seq": 7,
  "timestamp": "2026-08-31T20:00:00.000Z",
  "dado": "Aberta",
  "qos_used": 1
}
```

---

## FASE 1 — Infraestrutura do Broker (Docker)

**Agente executor:** Cria os arquivos de configuração e sobe o broker.

### Arquivo: `broker/mosquitto.conf`

```conf
# mosquitto.conf — configuração mínima para fins didáticos
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_type all
```

### Arquivo: `broker/docker-compose.yml`

```yaml
version: "3.8"

services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mqtt_broker_ap3
    restart: unless-stopped
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
      - mosquitto_data:/mosquitto/data
      - mosquitto_log:/mosquitto/log

volumes:
  mosquitto_data:
  mosquitto_log:
```

### Comandos de validação (executar na pasta `broker/`):

```powershell
# 1. Subir o broker
docker compose up -d

# 2. Verificar se está rodando
docker ps

# 3. Testar conectividade (requer mosquitto_pub/sub instalado ou via container)
docker exec mqtt_broker_ap3 mosquitto_pub -h localhost -t "teste/ping" -m "ok" -q 1
docker exec mqtt_broker_ap3 mosquitto_sub -h localhost -t "teste/ping" -C 1
# Deve imprimir: ok
```

---

## FASE 2 — Dependências e Configuração Compartilhada Python

**Agente executor:** Cria `requirements.txt` e `src/config.py`.

### Arquivo: `requirements.txt`

```
paho-mqtt==2.1.0
```

### Arquivo: `src/config.py`

```python
"""
config.py — Configurações centralizadas do sistema MQTT Casa Inteligente.
Todos os publishers e subscribers importam deste módulo.
"""

# ─── Broker ───────────────────────────────────────────────────────────────────
BROKER_HOST = "localhost"
BROKER_PORT = 1883
BROKER_KEEPALIVE = 60

# ─── Tópicos ──────────────────────────────────────────────────────────────────
TOPIC_TEMPERATURA  = "casa/sala/temperatura"
TOPIC_PORTA        = "casa/frente/porta"
TOPIC_STATUS       = "casa/status/sensores"

# ─── IDs dos sensores ─────────────────────────────────────────────────────────
ID_SENSOR_TEMP  = "sensor_temperatura_sala"
ID_SENSOR_PORTA = "sensor_porta_frente"

# ─── Parâmetros de publicação ─────────────────────────────────────────────────
PUBLISH_INTERVAL_TEMP  = 1.0   # segundos entre publicações do sensor de temperatura
PUBLISH_INTERVAL_PORTA = 3.0   # segundos entre publicações do sensor de porta

# ─── Payloads LWT ─────────────────────────────────────────────────────────────
LWT_PORTA_PAYLOAD = '{"id": "sensor_porta_frente", "dado": "OFFLINE", "seq": -1, "timestamp": null}'

# ─── Diretórios de saída ──────────────────────────────────────────────────────
RESULTS_DIR  = "../experiments/results"
ANALYSIS_DIR = "../analysis/output"
```

### Comandos de instalação:

```powershell
# Criar e ativar ambiente virtual (recomendado)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
```

---

## FASE 3 — Publisher 1: Sensor de Temperatura (`pub_temperatura.py`)

**Agente executor:** Cria o script do publisher de temperatura.

**Comportamento:**
- Publica no tópico `casa/sala/temperatura`.
- Simula leituras entre 18°C e 35°C com ruído aleatório gaussiano.
- Aceita argumento de linha de comando `--qos [0|1|2]` para facilitar os experimentos.
- Registra cada mensagem publicada em CSV no diretório `experiments/results/`.

### Arquivo: `src/pub_temperatura.py`

```python
"""
pub_temperatura.py — Publisher do sensor de temperatura da sala.

Uso:
    python pub_temperatura.py --qos 0 --count 60
    python pub_temperatura.py --qos 1 --count 60 --interval 1.0
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

# Adiciona o diretório pai ao path para importar config
sys.path.insert(0, str(Path(__file__).parent))
import config


# ─── Callbacks ────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[TEMP] Conectado ao broker {config.BROKER_HOST}:{config.BROKER_PORT}")
    else:
        print(f"[TEMP] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_publish(client, userdata, mid, reason_code, properties):
    print(f"[TEMP] ACK recebido para MID={mid}")


# ─── Função principal ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Publisher: Sensor de Temperatura")
    parser.add_argument("--qos",      type=int, default=0, choices=[0, 1, 2],
                        help="Nível de QoS para publicação (default: 0)")
    parser.add_argument("--count",    type=int, default=60,
                        help="Número de mensagens a publicar (default: 60)")
    parser.add_argument("--interval", type=float, default=config.PUBLISH_INTERVAL_TEMP,
                        help="Intervalo em segundos entre publicações (default: 1.0)")
    args = parser.parse_args()

    # ── Configuração do CSV de saída ─────────────────────────────────────────
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / f"qos{args.qos}_temperatura.csv"

    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_pub", "dado", "qos", "topic", "mid"])

    # ── Configuração do cliente MQTT ─────────────────────────────────────────
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"pub_temperatura_qos{args.qos}"
    )
    client.on_connect = on_connect
    client.on_publish = on_publish

    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)
    client.loop_start()

    time.sleep(0.5)  # aguarda conexão estabilizar

    # ── Loop de publicação ───────────────────────────────────────────────────
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
```

---

## FASE 4 — Publisher 2: Sensor de Porta (`pub_porta.py`)

**Agente executor:** Cria o script do publisher do sensor de porta.

**Comportamento:**
- Publica no tópico `casa/frente/porta`.
- Configura **LWT** (Last Will and Testament) no tópico `casa/status/sensores` — disparado automaticamente se o processo cair.
- Publica mensagem **Retained** com o último estado da porta.
- Aceita `--qos`, `--count`, `--interval`.
- Registra cada mensagem em CSV.

### Arquivo: `src/pub_porta.py`

```python
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
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).parent))
import config


# ─── Callbacks ────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[PORTA] Conectado ao broker {config.BROKER_HOST}:{config.BROKER_PORT}")
        print(f"[PORTA] LWT configurado em: {config.TOPIC_STATUS}")
    else:
        print(f"[PORTA] Falha na conexão. Código: {reason_code}")
        sys.exit(1)


def on_publish(client, userdata, mid, reason_code, properties):
    print(f"[PORTA] ACK recebido para MID={mid}")


# ─── Função principal ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Publisher: Sensor de Porta com LWT e Retained")
    parser.add_argument("--qos",      type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--count",    type=int, default=60)
    parser.add_argument("--interval", type=float, default=config.PUBLISH_INTERVAL_PORTA)
    parser.add_argument("--simulate-crash", action="store_true",
                        help="Simula falha abrupta após metade das mensagens (para testar LWT)")
    args = parser.parse_args()

    # ── CSV ──────────────────────────────────────────────────────────────────
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path   = results_dir / f"qos{args.qos}_porta.csv"
    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_pub", "dado", "qos", "topic", "mid", "retained"])

    # ── Configuração MQTT com LWT ─────────────────────────────────────────────
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

    # ── Loop de publicação ────────────────────────────────────────────────────
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
```

---

## FASE 5 — Subscriber 1: Central de Alarme (`sub_alarme.py`)

**Agente executor:** Cria o script do subscriber da central de alarme.

**Comportamento:**
- Assina `casa/frente/porta` e `casa/status/sensores`.
- Exibe alertas diferenciados: se receber LWT, exibe `⚠️  FALHA NO SENSOR`.
- Registra todas as mensagens recebidas com timestamp de chegada em CSV.
- Aceita `--qos` para definir com qual QoS se inscreve.

### Arquivo: `src/sub_alarme.py`

```python
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
        state["seq_esperado"] = seq + 1

    # ── Alerta de porta ──────────────────────────────────────────────────────
    icone = "🔓" if dado == "Aberta" else "🔒"
    print(f"[ALARME] {icone} seq={seq:03d} | Porta={dado:8s} | QoS={msg.qos} | {ts_chegada}")

    state["csv_writer"].writerow([
        seq, ts_chegada, dado, msg.topic, msg.qos, msg.retain, observacao
    ])


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
```

---

## FASE 6 — Subscriber 2: Dashboard Global (`sub_dashboard.py`)

**Agente executor:** Cria o subscriber do dashboard que monitora todos os tópicos.

**Comportamento:**
- Assina `casa/#` (wildcard — todos os tópicos da casa).
- Exibe dados formatados simulando um painel de controle.
- Detecta e registra mensagens retidas (flag `retain=True`).
- Registra mensagens em CSV.

### Arquivo: `src/sub_dashboard.py`

```python
"""
sub_dashboard.py — Subscriber: Dashboard Global da Casa Inteligente.

Usa wildcard 'casa/#' para receber TODOS os eventos da casa.

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


# ─── Callbacks ────────────────────────────────────────────────────────────────

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
        print(f"[DASH] Payload inválido em {msg.topic}")
        return

    dado      = payload.get("dado", "?")
    seq       = payload.get("seq", -1)
    unidade   = payload.get("unidade", "")
    retained_flag = "📌 RETAINED" if msg.retain else ""

    # ── Display formatado por tópico ─────────────────────────────────────────
    if msg.topic == config.TOPIC_TEMPERATURA:
        print(f"[DASH] 🌡️  Temperatura: {dado}{unidade:3s} | seq={seq:03d} | QoS={msg.qos} {retained_flag}")
    elif msg.topic == config.TOPIC_PORTA:
        icone = "🔓" if dado == "Aberta" else "🔒"
        print(f"[DASH] {icone} Porta: {dado:8s} | seq={seq:03d} | QoS={msg.qos} {retained_flag}")
    elif msg.topic == config.TOPIC_STATUS:
        print(f"[DASH] 🚨 STATUS SISTEMA: {dado} | seq={seq} | QoS={msg.qos} {retained_flag}")

    state["csv_writer"].writerow([
        seq, ts_chegada, msg.topic, dado, msg.qos, msg.retain
    ])


def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"\n[DASH] Desconectado. Código: {reason_code}")


# ─── Função principal ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Subscriber: Dashboard Global")
    parser.add_argument("--qos",     type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    state["qos"] = args.qos

    # ── CSV ──────────────────────────────────────────────────────────────────
    results_dir = Path(__file__).parent.parent / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path   = results_dir / f"sub_dashboard_qos{args.qos}.csv"
    csv_file   = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["seq", "timestamp_chegada", "topic", "dado", "qos", "retained"])

    state["csv_file"]   = csv_file
    state["csv_writer"] = csv_writer

    # ── Cliente ───────────────────────────────────────────────────────────────
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
        print(f"\n[DASH] ─── RESUMO ─────────────────────────────────────────────")
        print(f"[DASH] Total recebido    : {state['total']}")
        print(f"[DASH] Retained recebidos: {state['retained_recv']}")
        for topico, count in state["por_topico"].items():
            print(f"[DASH]   {topico}: {count} msgs")
        print(f"[DASH] Log salvo em      : {csv_path}")


if __name__ == "__main__":
    main()
```

---

## FASE 7 — Script Orquestrador de Experimentos (`run_experiment.py`)

**Agente executor:** Cria o script que automatiza TODOS os cenários de experimento, coletando logs sem intervenção manual.

**Cenários executados automaticamente:**

| # | Cenário | Publisher QoS | Subscriber QoS | Observação |
|---|---|---|---|---|
| 1 | Baseline QoS 0 | 0 | 0 | Possível perda de mensagens |
| 2 | Baseline QoS 1 | 1 | 1 | At-least-once (possível duplicata) |
| 3 | Baseline QoS 2 | 2 | 2 | Exactly-once (mais lento) |
| 4 | Falha controlada | 1 | 1 | pub_porta killed → LWT verificado |
| 5 | Retained state | 1 | 1 | Sub conecta depois da pub → recebe estado |

### Arquivo: `experiments/run_experiment.py`

```python
"""
run_experiment.py — Orquestrador automatizado de todos os experimentos da AP3.

Executa cada cenário como subprocesso, aguarda a conclusão e consolida os logs.

Uso:
    python run_experiment.py
    python run_experiment.py --count 60 --interval 0.5
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Caminhos
SCRIPT_DIR = Path(__file__).parent
SRC_DIR    = SCRIPT_DIR.parent / "src"
RESULTS    = SCRIPT_DIR / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

PYTHON = sys.executable


def banner(msg: str):
    linha = "═" * 60
    print(f"\n{linha}")
    print(f"  {msg}")
    print(f"{linha}\n")


def run_scenario(scenario_name: str, pub_cmd: list, sub_cmds: list, duration: int):
    """
    Inicia os subscribers, aguarda 1s, inicia os publishers,
    aguarda o publisher terminar, e depois encerra os subscribers.
    """
    banner(f"CENÁRIO: {scenario_name}")
    procs = []

    # 1. Iniciar subscribers primeiro (para não perder mensagens iniciais)
    for cmd in sub_cmds:
        print(f"  [ORQ] Iniciando subscriber: {' '.join(cmd)}")
        p = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        procs.append(p)

    time.sleep(2)  # aguarda subscribers se conectarem

    # 2. Iniciar publisher
    print(f"  [ORQ] Iniciando publisher: {' '.join(pub_cmd)}")
    pub = subprocess.Popen(pub_cmd, stdout=sys.stdout, stderr=sys.stderr)

    # 3. Aguardar publisher terminar
    pub.wait()
    time.sleep(2)  # aguarda subscribers processarem as últimas mensagens

    # 4. Encerrar subscribers
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()

    print(f"  [ORQ] Cenário '{scenario_name}' concluído.\n")
    time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description="Orquestrador de Experimentos MQTT")
    parser.add_argument("--count",    type=int, default=60,
                        help="Número de mensagens por experimento (default: 60)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Intervalo entre publicações em segundos (default: 1.0)")
    args = parser.parse_args()

    count    = str(args.count)
    interval = str(args.interval)

    banner("INICIANDO BATERIA DE EXPERIMENTOS — AP3 MQTT Casa Inteligente")
    print(f"  Mensagens por cenário : {count}")
    print(f"  Intervalo             : {interval}s")
    print(f"  Resultados em         : {RESULTS}\n")

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 1: QoS 0 — Fire and Forget
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 0 (Fire and Forget)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "0", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "0",
             "--output", "sub_alarme_qos0.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "0", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 2: QoS 1 — At Least Once
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 1 (At Least Once)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "1", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "1",
             "--output", "sub_alarme_qos1.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "1", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 3: QoS 2 — Exactly Once
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 2 (Exactly Once)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "2", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "2",
             "--output", "sub_alarme_qos2.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "2", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 4: Falha Controlada — LWT + Retained
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Falha Controlada: LWT + Retained (QoS 1)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_porta.py"),
            "--qos", "1", "--count", count, "--interval", interval,
            "--simulate-crash"   # mata o processo na metade → LWT disparado
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "1",
             "--output", "sub_alarme_lwt.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "1",
             "--timeout", "300"],
        ],
        duration = int((args.count // 2) * args.interval) + 20
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 5: Retained — Subscriber Tardio
    # (Demonstra que subscriber que conecta depois recebe o último estado)
    # ─────────────────────────────────────────────────────────────────────────
    banner("CENÁRIO: Retained — Subscriber Tardio (QoS 1)")
    print("  [ORQ] Publisher publicando estado retido da porta...")
    pub = subprocess.Popen([
        PYTHON, str(SRC_DIR / "pub_porta.py"),
        "--qos", "1", "--count", "5", "--interval", "0.5"
    ], stdout=sys.stdout, stderr=sys.stderr)
    pub.wait()

    print("  [ORQ] Aguardando 3s antes de conectar o subscriber tardio...")
    time.sleep(3)

    print("  [ORQ] Subscriber tardio conectando — deve receber estado retido imediatamente:")
    tardio = subprocess.Popen([
        PYTHON, str(SRC_DIR / "sub_dashboard.py"),
        "--qos", "1", "--timeout", "5"
    ], stdout=sys.stdout, stderr=sys.stderr)
    tardio.wait()
    print("  [ORQ] Cenário 'Retained' concluído.\n")

    banner("✅ TODOS OS EXPERIMENTOS CONCLUÍDOS")
    print(f"  CSVs disponíveis em: {RESULTS}")
    print(f"  Execute a análise  : python analysis/analyze.py\n")


if __name__ == "__main__":
    main()
```

---

## FASE 8 — Script de Análise e Relatório (`analysis/analyze.py`)

**Agente executor:** Cria o script que lê os CSVs dos experimentos e gera a tabela de resultados em Markdown e gráficos PNG.

### Arquivo: `analysis/analyze.py`

```python
"""
analyze.py — Análise dos resultados dos experimentos MQTT.

Lê os CSVs gerados pelo run_experiment.py e produz:
    1. tabela_resultados.md — tabela comparativa em Markdown
    2. grafico_perdas.png   — gráfico de barras de mensagens recebidas vs enviadas
    3. grafico_latencia.png — histograma de latência estimada (se timestamps disponíveis)

Uso:
    python analyze.py
    python analyze.py --results ../experiments/results --output ./output
"""

import argparse
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sem GUI para Windows
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd


# ─── Configuração ─────────────────────────────────────────────────────────────

SCENARIO_MAP = {
    "sub_alarme_qos0.csv": {"qos": 0, "semantica": "Fire and Forget",  "topico": "temperatura"},
    "sub_alarme_qos1.csv": {"qos": 1, "semantica": "At Least Once",    "topico": "temperatura"},
    "sub_alarme_qos2.csv": {"qos": 2, "semantica": "Exactly Once",     "topico": "temperatura"},
    "sub_alarme_lwt.csv":  {"qos": 1, "semantica": "Falha c/ LWT",     "topico": "porta"},
}


# ─── Funções auxiliares ───────────────────────────────────────────────────────

def load_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        return df
    except FileNotFoundError:
        print(f"  [ANALISE] ⚠️  Arquivo não encontrado: {path}")
        return None
    except Exception as e:
        print(f"  [ANALISE] Erro ao ler {path}: {e}")
        return None


def analisa_cenario(df: pd.DataFrame, qos: int, enviadas: int = 60) -> dict:
    """Calcula métricas de um cenário a partir do DataFrame do subscriber."""
    if df is None or df.empty:
        return {}

    recebidas  = len(df)
    duplicatas = recebidas - df["seq"].nunique() if "seq" in df.columns else 0
    lwt_events = len(df[df["observacao"] == "LWT_RECEBIDO"]) if "observacao" in df.columns else 0

    # Perdas estimadas via sequência
    if "seq" in df.columns:
        seqs_validos = df[df["seq"] >= 0]["seq"]
        if not seqs_validos.empty:
            seq_max = seqs_validos.max()
            perdas  = max(0, seq_max + 1 - len(seqs_validos.unique()))
        else:
            perdas = 0
    else:
        perdas = 0

    taxa_entrega = round((recebidas / max(enviadas, 1)) * 100, 1)

    return {
        "qos":          qos,
        "enviadas":     enviadas,
        "recebidas":    recebidas,
        "perdas":       perdas,
        "duplicatas":   duplicatas,
        "lwt_events":   lwt_events,
        "taxa_entrega": taxa_entrega,
    }


def gera_tabela_md(resultados: list[dict], output_path: Path):
    """Gera a tabela comparativa em Markdown."""
    linhas = [
        "# Tabela de Resultados — Experimentos MQTT Casa Inteligente\n",
        "| QoS | Semântica | Enviadas | Recebidas | Perdas | Duplicatas | Eventos LWT | Taxa de Entrega |",
        "|-----|-----------|----------|-----------|--------|------------|-------------|-----------------|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r.get('qos', '?')} "
            f"| {r.get('semantica', '?')} "
            f"| {r.get('enviadas', '?')} "
            f"| {r.get('recebidas', '?')} "
            f"| {r.get('perdas', '?')} "
            f"| {r.get('duplicatas', '?')} "
            f"| {r.get('lwt_events', '?')} "
            f"| {r.get('taxa_entrega', '?')}% |"
        )
    content = "\n".join(linhas) + "\n"
    output_path.write_text(content, encoding="utf-8")
    print(f"  [ANALISE] ✅ Tabela gerada: {output_path}")


def gera_grafico_perdas(resultados: list[dict], output_path: Path):
    """Gráfico de barras agrupado: Enviadas vs Recebidas por cenário."""
    labels    = [f"QoS {r['qos']}\n({r.get('semantica', '')})" for r in resultados]
    enviadas  = [r.get("enviadas", 0)  for r in resultados]
    recebidas = [r.get("recebidas", 0) for r in resultados]

    x     = range(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar([i - width/2 for i in x], enviadas,  width, label="Enviadas",  color="#4A90D9")
    bars2 = ax.bar([i + width/2 for i in x], recebidas, width, label="Recebidas", color="#5CB85C")

    ax.set_xlabel("Cenário", fontsize=12)
    ax.set_ylabel("Número de Mensagens", fontsize=12)
    ax.set_title("Comparação: Mensagens Enviadas vs Recebidas por Nível de QoS", fontsize=14)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend()
    ax.bar_label(bars1, padding=3)
    ax.bar_label(bars2, padding=3)
    ax.set_ylim(0, max(enviadas + recebidas) * 1.2 if enviadas else 10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  [ANALISE] ✅ Gráfico de perdas gerado: {output_path}")


def gera_grafico_taxa(resultados: list[dict], output_path: Path):
    """Gráfico de linha: Taxa de entrega (%) por nível de QoS."""
    labels = [f"QoS {r['qos']}" for r in resultados]
    taxas  = [r.get("taxa_entrega", 0) for r in resultados]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(labels, taxas, marker="o", linewidth=2, color="#E67E22", markersize=8)
    ax.fill_between(range(len(labels)), taxas, alpha=0.15, color="#E67E22")

    for i, (label, taxa) in enumerate(zip(labels, taxas)):
        ax.annotate(f"{taxa}%", (i, taxa), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=11, fontweight="bold")

    ax.set_ylim(0, 110)
    ax.set_xlabel("Nível de QoS", fontsize=12)
    ax.set_ylabel("Taxa de Entrega (%)", fontsize=12)
    ax.set_title("Taxa de Entrega de Mensagens por Nível de QoS", fontsize=14)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  [ANALISE] ✅ Gráfico de taxa gerado: {output_path}")


# ─── Função principal ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Análise dos resultados MQTT")
    parser.add_argument("--results", type=str,
                        default=str(Path(__file__).parent.parent / "experiments" / "results"))
    parser.add_argument("--output",  type=str,
                        default=str(Path(__file__).parent / "output"))
    parser.add_argument("--enviadas", type=int, default=60,
                        help="Número de mensagens enviadas por cenário (default: 60)")
    args = parser.parse_args()

    results_dir = Path(args.results)
    output_dir  = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n[ANALISE] Lendo resultados dos experimentos...")

    resultados = []
    for filename, meta in SCENARIO_MAP.items():
        csv_path = results_dir / filename
        df       = load_csv(csv_path)
        metricas = analisa_cenario(df, qos=meta["qos"], enviadas=args.enviadas)
        if metricas:
            metricas["semantica"] = meta["semantica"]
            metricas["topico"]    = meta["topico"]
            resultados.append(metricas)
            print(f"  [ANALISE] {filename}: {metricas['recebidas']} recebidas, "
                  f"{metricas['perdas']} perdas, {metricas['taxa_entrega']}% entregues")

    if not resultados:
        print("[ANALISE] ⚠️  Nenhum resultado encontrado. Execute run_experiment.py primeiro.")
        return

    # Gerar outputs
    gera_tabela_md(resultados, output_dir / "tabela_resultados.md")
    gera_grafico_perdas(resultados, output_dir / "grafico_perdas.png")
    gera_grafico_taxa(resultados,   output_dir / "grafico_taxa.png")

    print(f"\n[ANALISE] ✅ Análise completa. Outputs em: {output_dir}")


if __name__ == "__main__":
    main()
```

---

## FASE 9 — README e Diagrama de Arquitetura

**Agente executor:** Cria o README.md completo com instruções de execução passo a passo.

### Arquivo: `README.md`

```markdown
# AP3 — Sistemas Distribuídos: MQTT Casa Inteligente

Sistema de monitoramento IoT distribuído usando protocolo MQTT, Docker e Python 3.10+.

## Arquitetura

```
                         ┌─────────────────────────────────┐
                         │   Broker Mosquitto (Docker:1883) │
                         └────────────────┬────────────────┘
                                          │
             ┌────────────────────────────┼────────────────────────────┐
             │                            │                            │
    ┌────────▼────────┐        ┌──────────▼──────────┐     ┌──────────▼──────────┐
    │ pub_temperatura │        │     sub_alarme       │     │   sub_dashboard     │
    │ (sala/temp)     │        │ (porta + status)     │     │ (casa/#  wildcard)  │
    │ QoS 0/1/2       │        │ Detecta LWT e perdas │     │ Dashboard global    │
    └─────────────────┘        └─────────────────────┘     └─────────────────────┘
    ┌────────────────┐
    │   pub_porta    │ ─── LWT ──► casa/status/sensores
    │ (frente/porta) │ ─── Retained (último estado)
    │ QoS 0/1/2      │
    └────────────────┘
```

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows)
- Python 3.10+
- Git (opcional)

## Instalação

```powershell
# 1. Entrar no diretório do projeto
cd atividade_pratica3

# 2. Criar e ativar ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependências Python
pip install -r requirements.txt

# 4. Instalar matplotlib para análise (experimentos)
pip install matplotlib pandas
```

## Execução

### Passo 1: Subir o Broker MQTT

```powershell
cd broker
docker compose up -d
docker ps  # verificar se mqtt_broker_ap3 está UP
cd ..
```

### Passo 2: Executar todos os experimentos automaticamente

```powershell
cd experiments
python run_experiment.py --count 60 --interval 1.0
```

Esse comando executa todos os 5 cenários em sequência e gera os CSVs em `experiments/results/`.

### Passo 3: Gerar análise e gráficos

```powershell
cd analysis
pip install matplotlib pandas
python analyze.py
```

Outputs gerados em `analysis/output/`:
- `tabela_resultados.md`
- `grafico_perdas.png`
- `grafico_taxa.png`

### Execução manual (alternativa — terminais separados)

```powershell
# Terminal 1: Dashboard (subscriber global)
cd src && python sub_dashboard.py --qos 1 --timeout 120

# Terminal 2: Central de Alarme (subscriber específico)
cd src && python sub_alarme.py --qos 1 --timeout 120

# Terminal 3: Publisher temperatura
cd src && python pub_temperatura.py --qos 1 --count 60

# Terminal 4: Publisher porta
cd src && python pub_porta.py --qos 1 --count 20

# Para testar LWT (falha controlada):
cd src && python pub_porta.py --qos 1 --count 20 --simulate-crash
```

## Cenários de Experimento

| # | Cenário | QoS | Feature MQTT |
|---|---------|-----|--------------|
| 1 | Baseline | 0 | Fire and Forget |
| 2 | Baseline | 1 | At Least Once |
| 3 | Baseline | 2 | Exactly Once |
| 4 | Falha Controlada | 1 | LWT (Last Will and Testament) |
| 5 | Subscriber Tardio | 1 | Retained Messages |

## Taxonomia de Tópicos

```
casa/
├── sala/temperatura      → float (°C)
├── frente/porta          → "Aberta" | "Fechada"  [RETAINED]
└── status/sensores       → LWT automático do sensor de porta
```

## Estrutura do Payload

```json
{
  "id":        "sensor_temperatura_sala",
  "seq":       42,
  "timestamp": "2026-08-31T20:00:00Z",
  "dado":      24.5,
  "unidade":   "°C",
  "qos_used":  1
}
```

## Derrubar o Broker

```powershell
cd broker
docker compose down
```
```

---

## FASE 10 — Comandos de Verificação Final e Checklist

**Agente executor:** Valida que toda a estrutura foi criada corretamente.

### Checklist de verificação

Execute os seguintes comandos para confirmar o estado do projeto:

```powershell
# 1. Verificar estrutura de arquivos
tree atividade_pratica3 /f

# 2. Verificar broker rodando
docker ps | Select-String "mqtt_broker_ap3"

# 3. Smoke test do publisher de temperatura (5 mensagens, QoS 0)
cd atividade_pratica3/src
python pub_temperatura.py --qos 0 --count 5 --interval 0.5
# Esperado: 5 linhas de log com seq=000 a seq=004

# 4. Smoke test do subscriber (em outro terminal, antes do publisher)
python sub_dashboard.py --qos 0 --timeout 10
# Esperado: recebe as 5 mensagens do passo anterior se executados em paralelo

# 5. Verificar que o CSV foi gerado
ls ../experiments/results/qos0_temperatura.csv

# 6. Smoke test do LWT (publisher com crash simulado)
python pub_porta.py --qos 1 --count 10 --simulate-crash
# Esperado: publica ~5 mensagens, então mata o processo
# O sub_alarme deve imprimir: "ALERTA CRÍTICO: Sensor ficou OFFLINE"
```

### Critérios de aceite por requisito do trabalho

| Requisito | Como verificar |
|---|---|
| ≥ 4 clientes (2 pub + 2 sub) | pub_temperatura, pub_porta, sub_alarme, sub_dashboard |
| ≥ 50 mensagens por cenário | `--count 60` em todos os scripts |
| ≥ 2 níveis de QoS | Cenários 1, 2, 3 (QoS 0, 1, 2) |
| Payload com ID e seq | Verificar CSV: colunas `id`, `seq` |
| Retained messages | Cenário 5 (subscriber tardio) |
| LWT | Cenário 4 (--simulate-crash) |
| Falha/desconexão | Cenário 4 |
| Análise comparativa | `analyze.py` → tabela + gráficos |
| Logs como evidência | CSVs em `experiments/results/` |
| README com instruções | `README.md` |

---

## Resumo de Fases por Agente

| Fase | Arquivos Criados | Dependências |
|------|-----------------|--------------|
| 1 | `broker/docker-compose.yml`, `broker/mosquitto.conf` | Docker |
| 2 | `requirements.txt`, `src/config.py` | Python, venv |
| 3 | `src/pub_temperatura.py` | Fase 2 |
| 4 | `src/pub_porta.py` | Fase 2 |
| 5 | `src/sub_alarme.py` | Fase 2 |
| 6 | `src/sub_dashboard.py` | Fase 2 |
| 7 | `experiments/run_experiment.py` | Fases 3–6 |
| 8 | `analysis/analyze.py` | Fase 7 (precisa de resultados) |
| 9 | `README.md` | Todas |
| 10 | — (validação) | Todas |
