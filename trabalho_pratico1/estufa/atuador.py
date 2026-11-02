"""
atuador.py — Processo Atuador do sistema da estufa agrícola.

Subscreve aos tópicos de comando no broker MQTT e simula o acionamento da
bomba de irrigação e do exaustor. Como os três controladores operam em
replicação ativa e publicam comandos simultaneamente, o atuador utiliza um
cache LRU baseado em 'comando_id' para descartar mensagens duplicadas.

Uso:
    python -m estufa.atuador
"""

import collections
import json
import time
import paho.mqtt.client as mqtt
from estufa import config


_estado_bomba = {"ligado": False}
_estado_exaustor = {"ligado": False}
_dedup_cache: collections.OrderedDict = collections.OrderedDict()


def _is_duplicado(comando_id: str) -> bool:
    """
    Verifica no cache LRU se o comando_id já foi processado.
    Retorna True se for duplicado; caso contrário, registra o ID no cache.
    """
    if not comando_id:
        return False

    if comando_id in _dedup_cache:
        _dedup_cache.move_to_end(comando_id)
        return True

    _dedup_cache[comando_id] = True
    if len(_dedup_cache) > config.DEDUP_CACHE_SIZE:
        _dedup_cache.popitem(last=False)

    return False


def _on_connect(client, userdata, flags, reason_code, properties):
    """Callback de conexão: subscreve aos tópicos de comando dos atuadores."""
    if reason_code == 0:
        print("[ATUADOR] Conectado ao broker MQTT.")
        client.subscribe(config.TOPIC_ATUADOR_BOMBA, qos=1)
        client.subscribe(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_BOMBA}")
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_EXAUSTOR}")
    else:
        print(f"[ATUADOR] Falha na conexão: {reason_code}")


def _processar_bomba(client: mqtt.Client, payload: dict) -> None:
    """Atualiza o estado da bomba de irrigação e publica confirmação."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_bomba["ligado"] = novo_estado
    status = "LIGADA" if novo_estado else "DESLIGADA"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] Bomba de irrigação -> {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_BOMBA, "bomba", novo_estado)


def _processar_exaustor(client: mqtt.Client, payload: dict) -> None:
    """Atualiza o estado do exaustor e publica confirmação."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_exaustor["ligado"] = novo_estado
    status = "LIGADO" if novo_estado else "DESLIGADO"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] Exaustor -> {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_EXAUSTOR, "exaustor", novo_estado)


def _publicar_status(client: mqtt.Client, topico: str, nome: str, ligado: bool) -> None:
    """Publica o estado atual do atuador no tópico de status correspondente."""
    payload = json.dumps({
        "atuador": nome,
        "ligado": ligado,
        "timestamp": time.time(),
    })
    client.publish(topico, payload, qos=1)


def _on_message(client, userdata, msg):
    """Filtra comandos duplicados via cache LRU e encaminha ao atuador alvo."""
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[ATUADOR] Payload inválido em {msg.topic}: {msg.payload}")
        return

    comando_id = payload.get("comando_id", "")
    if _is_duplicado(comando_id):
        print(f"[ATUADOR] Comando duplicado descartado: {comando_id[:8]}... (tópico: {msg.topic})")
        return

    if msg.topic == config.TOPIC_ATUADOR_BOMBA:
        _processar_bomba(client, payload)
    elif msg.topic == config.TOPIC_ATUADOR_EXAUSTOR:
        _processar_exaustor(client, payload)


def executar_atuador():
    """Inicia o cliente MQTT do atuador e aguarda comandos."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="atuador_estufa")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print("[ATUADOR] Aguardando comandos (deduplicação LRU ativa)...")
    client.loop_forever()


if __name__ == "__main__":
    executar_atuador()
