"""
test_broker_local.py — Testes do Broker MQTT v3.1.1 enxuto em Python puro.
"""

import json
import socket
import threading
import time
import paho.mqtt.client as mqtt
import pytest

from estufa.broker_local import (
    BrokerMQTTLocal,
    _codificar_remaining_length,
    _decodificar_remaining_length_bytes,
    executar_broker,
)


def _conectar_paho(client_id: str, port: int, topic: str | None = None, recebidos: list | None = None):
    conectado = threading.Event()
    inscrito = threading.Event()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    def on_connect(c, userdata, flags, rc, props):
        if rc == 0:
            conectado.set()
            if topic:
                c.subscribe(topic, qos=1)

    def on_subscribe(c, userdata, mid, rc_list, props):
        inscrito.set()

    def on_message(c, userdata, msg):
        if recebidos is not None:
            recebidos.append(json.loads(msg.payload.decode("utf-8")))

    cli.on_connect = on_connect
    cli.on_subscribe = on_subscribe
    cli.on_message = on_message
    cli.connect("127.0.0.1", port, 60)
    cli.loop_start()
    assert conectado.wait(timeout=3.0)
    if topic:
        assert inscrito.wait(timeout=3.0)
    return cli


def test_tp04_publish_qos1_wait_for_publish_e_fanout():
    """TP-04: Publicação QoS 1 libera wait_for_publish() e entrega aos 3 assinantes."""
    broker = BrokerMQTTLocal(host="127.0.0.1", port=0, silencioso=True)
    porta = broker.iniciar_em_background()

    listas = [[], [], []]
    assinantes = [
        _conectar_paho(f"sub_{i}", porta, "estufa/sensores/temperatura", listas[i - 1])
        for i in (1, 2, 3)
    ]
    pub = _conectar_paho("pub_sensor", porta)

    try:
        payload = {"valor": 36.2, "unidade": "°C", "timestamp": 1700000000.0}
        info = pub.publish("estufa/sensores/temperatura", json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=3.0)

        limite = time.monotonic() + 3.0
        while time.monotonic() < limite and any(len(lst) == 0 for lst in listas):
            time.sleep(0.05)

        assert listas == [[payload], [payload], [payload]]
    finally:
        for c in [*assinantes, pub]:
            c.loop_stop()
            c.disconnect()
        broker.parar()


def test_te01_validacao_parametros_e_varint_multibyte():
    """TE-01: Valida limites de host/porta e codificação varint multi-byte (max 4 bytes)."""
    for tamanho in (0, 127, 128, 300, 16384):
        assert _decodificar_remaining_length_bytes(_codificar_remaining_length(tamanho)) == tamanho

    with pytest.raises(ValueError):
        BrokerMQTTLocal(host="127.0.0.1", port=70000)
    with pytest.raises(ValueError):
        BrokerMQTTLocal(host="", port=1883)
    with pytest.raises(ValueError):
        executar_broker(host="127.0.0.1", port=0)
    with pytest.raises(ValueError):
        _decodificar_remaining_length_bytes(b"\x80\x80\x80\x80\x01")


def test_te03_desconexao_abrupta_e_pacote_malformado_nao_derrubam_broker():
    """TE-03: Cliente com pacote malformado ou queda abrupta não afeta assinantes estáveis."""
    broker = BrokerMQTTLocal(host="127.0.0.1", port=0, silencioso=True)
    porta = broker.iniciar_em_background()

    recebidos = []
    estavel = _conectar_paho("estavel", porta, "estufa/atuadores/bomba", recebidos)

    try:
        # Envia pacote MQTT com varint malformado (> 4 bytes) e fecha bruscamente
        with socket.create_connection(("127.0.0.1", porta), timeout=2.0) as ruim:
            ruim.sendall(b"\x10\x0e\x00\x04MQTT\x04\x02\x00\x3c\x00\x02r1")
            ruim.recv(4)
            ruim.sendall(b"\x30\x80\x80\x80\x80\x01")

        # Cliente estável continua operando normalmente
        pub = _conectar_paho("pub_ok", porta)
        try:
            info = pub.publish("estufa/atuadores/bomba", json.dumps({"acao": "ligar"}), qos=1)
            info.wait_for_publish(timeout=3.0)
            limite = time.monotonic() + 3.0
            while time.monotonic() < limite and not recebidos:
                time.sleep(0.05)
            assert recebidos == [{"acao": "ligar"}]
        finally:
            pub.loop_stop()
            pub.disconnect()
    finally:
        estavel.loop_stop()
        estavel.disconnect()
        broker.parar()


def test_te04_executar_broker_sai_limpo_quando_porta_ocupada(capsys):
    """TE-04: Se a porta já estiver em uso, executar_broker informa e retorna sem travar."""
    broker = BrokerMQTTLocal(host="127.0.0.1", port=0, silencioso=True)
    porta_ocupada = broker.iniciar_em_background()

    try:
        t0 = time.monotonic()
        executar_broker(host="127.0.0.1", port=porta_ocupada)
        duracao = time.monotonic() - t0
        saida = capsys.readouterr().out

        assert duracao < 2.0
        assert "já está em uso" in saida
    finally:
        broker.parar()
