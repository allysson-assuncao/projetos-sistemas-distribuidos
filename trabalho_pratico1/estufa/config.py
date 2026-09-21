"""
config.py — Global constants for the Distributed Agricultural Greenhouse System.

All MQTT topics, XML-RPC ports, and control thresholds are centralized here.
"""

# ──────────────────────────────────────────────
# MQTT — Broker
# ──────────────────────────────────────────────
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# ──────────────────────────────────────────────
# MQTT — Topics
# ──────────────────────────────────────────────
TOPIC_TEMPERATURA   = "estufa/sensores/temperatura"
TOPIC_UMIDADE_SOLO  = "estufa/sensores/umidade_solo"
TOPIC_ATUADOR_BOMBA = "estufa/atuadores/bomba"
TOPIC_ATUADOR_EXAUSTOR = "estufa/atuadores/exaustor"
TOPIC_STATUS_BOMBA  = "estufa/status/bomba"
TOPIC_STATUS_EXAUSTOR = "estufa/status/exaustor"

# ──────────────────────────────────────────────
# XML-RPC — Controllers (internal cluster)
# ──────────────────────────────────────────────
CONTROLADORES = [
    {"id": "ctrl_1", "host": "localhost", "port": 8001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 8002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 8003, "data_file": "data_ctrl_3.json"},
]

# ──────────────────────────────────────────────
# XML-RPC — Middleware Server (external-facing)
# ──────────────────────────────────────────────
MIDDLEWARE_HOST = "localhost"
MIDDLEWARE_PORT = 9000   # Single entry point for all clients

# ──────────────────────────────────────────────
# Greenhouse Control Thresholds
# ──────────────────────────────────────────────
TEMP_MAX_CELSIUS     = 35.0   # Above: turn on exhaust fan
TEMP_MIN_CELSIUS     = 15.0   # Below: turn off exhaust fan
UMIDADE_MIN_PERCENT  = 30.0   # Below: turn on irrigation pump
UMIDADE_MAX_PERCENT  = 70.0   # Above: turn off irrigation pump

# ──────────────────────────────────────────────
# Middleware — Voting Parameters
# ──────────────────────────────────────────────
TIMEOUT_RPC_SEGUNDOS = 3       # Per XML-RPC call timeout
QUORUM_MINIMO        = 2       # Minimum concordant responses for quorum

# ──────────────────────────────────────────────
# Actuator Deduplication
# ──────────────────────────────────────────────
DEDUP_CACHE_SIZE     = 50      # LRU cache size for comando_id deduplication
