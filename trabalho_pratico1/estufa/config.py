"""
config.py — Parâmetros globais do sistema de controle da estufa agrícola.

Centraliza tópicos MQTT, endereços XML-RPC, limiares de acionamento e
configurações de votação e deduplicação.
"""

# Broker MQTT
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# Tópicos MQTT
TOPIC_TEMPERATURA = "estufa/sensores/temperatura"
TOPIC_UMIDADE_SOLO = "estufa/sensores/umidade_solo"
TOPIC_ATUADOR_BOMBA = "estufa/atuadores/bomba"
TOPIC_ATUADOR_EXAUSTOR = "estufa/atuadores/exaustor"
TOPIC_STATUS_BOMBA = "estufa/status/bomba"
TOPIC_STATUS_EXAUSTOR = "estufa/status/exaustor"

# Réplicas de controladores (cluster XML-RPC interno)
CONTROLADORES = [
    {"id": "ctrl_1", "host": "localhost", "port": 8001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 8002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 8003, "data_file": "data_ctrl_3.json"},
]

# Servidor de Middleware XML-RPC (ponto único de entrada para clientes)
MIDDLEWARE_HOST = "localhost"
MIDDLEWARE_PORT = 9000

# Limiares de controle ambiental (com histerese)
TEMP_MAX_CELSIUS = 35.0      # Acima: liga o exaustor
TEMP_MIN_CELSIUS = 15.0      # Abaixo: desliga o exaustor
UMIDADE_MIN_PERCENT = 30.0   # Abaixo: liga a bomba de irrigação
UMIDADE_MAX_PERCENT = 70.0   # Acima: desliga a bomba de irrigação

# Parâmetros de votação do Middleware
TIMEOUT_RPC_SEGUNDOS = 3
QUORUM_MINIMO = 2

# Capacidade do cache LRU de deduplicação no atuador
DEDUP_CACHE_SIZE = 50
