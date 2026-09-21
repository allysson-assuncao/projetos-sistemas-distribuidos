"""
atuador.py — Actuator Process for the Greenhouse System.

Subscribes to command topics on MQTT and simulates:
  - Irrigation pump (on/off)
  - Exhaust fan (on/off)

DEDUPLICATION: Since the Middleware sends the same command to all 3 controllers,
all 3 may publish to MQTT simultaneously. The actuator deduplicates using a
UUID-based 'comando_id' included in the payload. An LRU cache tracks the last
DEDUP_CACHE_SIZE processed IDs and silently discards duplicates.

Usage:
    python -m estufa.atuador
"""

import json
import time
import collections
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────────────────────────
# Internal State
# ─────────────────────────────────────────────────────────────
_estado_bomba    = {"ligado": False}
_estado_exaustor = {"ligado": False}

# LRU Cache for comando_id deduplication
# Uses OrderedDict: newest at end, oldest at front (evicted when full)
_dedup_cache: collections.OrderedDict = collections.OrderedDict()


def _is_duplicado(comando_id: str) -> bool:
    """
    Checks if a comando_id has already been processed (LRU cache lookup).

    Returns True if the command is a duplicate and should be discarded.
    Side effect: adds new IDs to the cache and evicts oldest if at capacity.
    """
    if not comando_id:
        # No ID provided — cannot deduplicate, process the command
        return False

    if comando_id in _dedup_cache:
        # Move to end to mark as recently seen (LRU refresh)
        _dedup_cache.move_to_end(comando_id)
        return True  # Duplicate — discard

    # New ID: add to cache
    _dedup_cache[comando_id] = True
    _dedup_cache.move_to_end(comando_id)

    # Evict oldest entry if cache exceeds capacity
    if len(_dedup_cache) > config.DEDUP_CACHE_SIZE:
        _dedup_cache.popitem(last=False)

    return False  # Not a duplicate — process


def _on_connect(client, userdata, flags, reason_code, properties):
    """Connection callback: subscribe to actuator command topics."""
    if reason_code == 0:
        print("[ATUADOR] Conectado ao broker MQTT.")
        client.subscribe(config.TOPIC_ATUADOR_BOMBA,    qos=1)
        client.subscribe(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_BOMBA}")
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_EXAUSTOR}")
    else:
        print(f"[ATUADOR] Falha na conexão: {reason_code}")


def _processar_bomba(client: mqtt.Client, payload: dict) -> None:
    """Processes pump command and publishes confirmation status."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_bomba["ligado"] = novo_estado
    status = "LIGADA" if novo_estado else "DESLIGADA"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] 💧 Bomba de Irrigação → {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_BOMBA, "bomba", novo_estado)


def _processar_exaustor(client: mqtt.Client, payload: dict) -> None:
    """Processes exhaust fan command and publishes confirmation status."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_exaustor["ligado"] = novo_estado
    status = "LIGADO" if novo_estado else "DESLIGADO"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] 🌬️ Exaustor → {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_EXAUSTOR, "exaustor", novo_estado)


def _publicar_status(client: mqtt.Client, topico: str, nome: str, ligado: bool) -> None:
    """Publishes execution confirmation on the status topic."""
    payload = json.dumps({
        "atuador": nome,
        "ligado": ligado,
        "timestamp": time.time(),
    })
    client.publish(topico, payload, qos=1)


def _on_message(client, userdata, msg):
    """
    Message callback: deduplicates via LRU cache, then routes to handler.

    Deduplication flow:
    1. Parse payload and extract 'comando_id'
    2. If 'comando_id' is in LRU cache → discard (duplicate from another controller)
    3. If new → process and add to cache
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[ATUADOR] Payload inválido em {msg.topic}: {msg.payload}")
        return

    # ── Deduplication Check ────────────────────────────────────
    comando_id = payload.get("comando_id", "")
    if _is_duplicado(comando_id):
        print(f"[ATUADOR] 🔁 Comando duplicado ignorado: {comando_id[:8]}... (tópico: {msg.topic})")
        return

    # ── Route to handler ───────────────────────────────────────
    if msg.topic == config.TOPIC_ATUADOR_BOMBA:
        _processar_bomba(client, payload)
    elif msg.topic == config.TOPIC_ATUADOR_EXAUSTOR:
        _processar_exaustor(client, payload)


def executar_atuador():
    """Starts the actuator and waits for commands indefinitely."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="atuador_estufa")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print("[ATUADOR] Aguardando comandos... (deduplicação LRU ativa)")
    client.loop_forever()


if __name__ == "__main__":
    executar_atuador()
