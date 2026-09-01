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
