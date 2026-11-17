"""
atuador.py — Processo Atuador do sistema da estufa agrícola.

Assina os tópicos de comando da bomba e do exaustor no broker MQTT,
atualiza o estado físico dos equipamentos e publica confirmação de status
para fechar a malha de controle com o sensor.

Uso:
    python -m estufa.atuador
"""

import json
import time
import paho.mqtt.client as mqtt
from estufa import config

_estado_bomba = {"ligado": False}
_estado_exaustor = {"ligado": False}


# Inscrição nos tópicos de comando com QoS 1 após conectar ao broker MQTT
def _on_connect(client, userdata, flags, reason_code, properties) -> None:
    if reason_code == 0:
        client.subscribe(config.TOPIC_ATUADOR_BOMBA, qos=1)
        client.subscribe(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)
        print("[ATUADOR] Conectado ao broker MQTT. Assinando comandos de bomba e exaustor.")
    else:
        print(f"[ATUADOR] Falha na conexão MQTT: {reason_code}")


def _publicar_status(client: mqtt.Client, topico: str, nome: str, ligado: bool) -> None:
    """Publica confirmação do estado atual do atuador para retroalimentar o sensor."""
    payload = json.dumps({
        "atuador": nome,
        "ligado": ligado,
        "timestamp": time.time(),
    })
    # Publica status com QoS 1 para atualizar a simulação de malha fechada do sensor
    client.publish(topico, payload, qos=1)


def _processar_atuador(
    client: mqtt.Client,
    nome: str,
    estado_ref: dict,
    topico_status: str,
    payload: dict,
) -> bool:
    """Valida a ação ('ligar'/'desligar'), atualiza o estado local e publica confirmação."""
    if not isinstance(payload, dict):
        return False

    acao = str(payload.get("acao", "")).strip().lower()
    if acao not in ("ligar", "desligar"):
        print(f"[ATUADOR] Ação inválida ignorada para {nome}: '{acao}'")
        return False

    novo_estado = (acao == "ligar")
    estado_ref["ligado"] = novo_estado
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] {nome.capitalize()} -> {'LIGADO' if novo_estado else 'DESLIGADO'} (líder: {origem})")
    _publicar_status(client, topico_status, nome, novo_estado)
    return True


def _on_message(client, userdata, msg) -> None:
    """Decodifica comando JSON e roteia para bomba ou exaustor."""
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[ATUADOR] Payload inválido ignorado em {msg.topic}")
        return

    if msg.topic == config.TOPIC_ATUADOR_BOMBA:
        _processar_atuador(client, "bomba", _estado_bomba, config.TOPIC_STATUS_BOMBA, payload)
    elif msg.topic == config.TOPIC_ATUADOR_EXAUSTOR:
        _processar_atuador(client, "exaustor", _estado_exaustor, config.TOPIC_STATUS_EXAUSTOR, payload)


def executar_atuador() -> None:
    """Inicia o cliente MQTT do atuador e aguarda comandos oficiais do Líder."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="atuador_estufa")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print("[ATUADOR] Aguardando comandos oficiais via MQTT...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[ATUADOR] Encerrando atuador.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    executar_atuador()
