"""
config.py — Parâmetros globais do sistema de controle da estufa agrícola.

Centraliza tópicos MQTT, topologia do cluster XML-RPC de controladores,
limiares de acionamento e parâmetros de eleição e consenso.
"""

# Configuração do Broker MQTT v3.1.1 (camada IoT: sensores <-> controladores <-> atuador)
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# Tópicos MQTT divididos por fluxo de telemetria, comando oficial e feedback
TOPIC_TEMPERATURA = "estufa/sensores/temperatura"
TOPIC_UMIDADE_SOLO = "estufa/sensores/umidade_solo"
TOPIC_ATUADOR_BOMBA = "estufa/atuadores/bomba"
TOPIC_ATUADOR_EXAUSTOR = "estufa/atuadores/exaustor"
TOPIC_STATUS_BOMBA = "estufa/status/bomba"
TOPIC_STATUS_EXAUSTOR = "estufa/status/exaustor"

# Topologia do cluster distribuído (Middleware lógico embarcado via XML-RPC direto).
# O 'rank' define a prioridade na eleição de líder pelo algoritmo Bully (1 < 2 < 3).
MAPA_CONTROLADORES = {
    1: {"id": "ctrl_1", "rank": 1, "host": "127.0.0.1", "port": 8001, "data_file": "data_ctrl_1.json"},
    2: {"id": "ctrl_2", "rank": 2, "host": "127.0.0.1", "port": 8002, "data_file": "data_ctrl_2.json"},
    3: {"id": "ctrl_3", "rank": 3, "host": "127.0.0.1", "port": 8003, "data_file": "data_ctrl_3.json"},
}

CONTROLADORES = [
    (cfg["host"], cfg["port"]) for cfg in MAPA_CONTROLADORES.values()
]


def obter_config_controlador(identificador: str | int) -> dict:
    """Resolve a configuração de um controlador pelo número (1..3) ou ID ('ctrl_1'..'ctrl_3')."""
    if isinstance(identificador, bool):
        raise ValueError(f"Identificador de controlador inválido: {identificador}")

    if isinstance(identificador, int):
        chave = identificador
    elif isinstance(identificador, str):
        texto = identificador.strip().lower()
        if texto.isdigit():
            chave = int(texto)
        elif texto.startswith("ctrl_") and texto[5:].isdigit():
            chave = int(texto[5:])
        else:
            raise ValueError(f"Identificador de controlador inválido: '{identificador}'")
    else:
        raise ValueError(f"Identificador de controlador inválido: {identificador!r}")

    if chave not in MAPA_CONTROLADORES:
        raise ValueError(f"Controlador '{identificador}' fora do mapa permitido (1..3).")

    return dict(MAPA_CONTROLADORES[chave])


# Faixas de histerese ambiental avaliadas pelos controladores antes do consenso
TEMP_MAX_CELSIUS = 35.0      # Acima: liga o exaustor
TEMP_MIN_CELSIUS = 15.0      # Abaixo: desliga o exaustor
UMIDADE_MIN_PERCENT = 30.0   # Abaixo: liga a bomba de irrigação
UMIDADE_MAX_PERCENT = 70.0   # Acima: desliga a bomba de irrigação

# Timeouts explícitos de RPC e intervalo de heartbeat para detecção rápida de queda
TIMEOUT_RPC_SEGUNDOS = 0.6
INTERVALO_HEARTBEAT_SEGUNDOS = 2.0
