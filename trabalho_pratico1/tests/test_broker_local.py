"""Testes unitários e de integração do Broker MQTT v3.1.1 em Python puro (`broker_local.py`)."""

from collections import deque
import json
import socket
import threading
import time
from typing import Optional
import paho.mqtt.client as mqtt
import pytest

from estufa.broker_local import (
    BrokerMQTTLocal,
    _codificar_remaining_length,
    _decodificar_remaining_length_bytes,
    _topico_casa_filtro,
)


class _CanalBytes:
    """Fila de bytes thread-safe para simular stream TCP bidirecional em memória."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._cond = threading.Condition()
        self._fechado = False

    def escrever(self, dados: bytes) -> None:
        with self._cond:
            if self._fechado:
                raise OSError("Socket fechado")
            self._buf.extend(dados)
            self._cond.notify_all()

    def ler(self, n: int, timeout: float = 3.0) -> bytes:
        limite = time.time() + timeout
        with self._cond:
            while len(self._buf) == 0 and not self._fechado:
                restante = limite - time.time()
                if restante <= 0:
                    raise socket.timeout("Timeout lendo do socket em memória")
                self._cond.wait(timeout=restante)
            if len(self._buf) == 0 and self._fechado:
                return b""
            fatia = bytes(self._buf[:n])
            del self._buf[:n]
            return fatia

    def fechar(self) -> None:
        with self._cond:
            self._fechado = True
            self._cond.notify_all()


class SocketEmMemoria:
    """Par de endpoints compatíveis com `recv`, `sendall`, `shutdown` e `close`."""

    def __init__(self, entrada: _CanalBytes, saida: _CanalBytes) -> None:
        self._entrada = entrada
        self._saida = saida

    def recv(self, bufsize: int) -> bytes:
        return self._entrada.ler(bufsize)

    def sendall(self, data: bytes) -> None:
        self._saida.escrever(data)

    def shutdown(self, how: int) -> None:
        self.close()

    def close(self) -> None:
        self._entrada.fechar()
        self._saida.fechar()


def criar_par_sockets_memoria():
    """Cria um par conectado `(sock_cliente, sock_servidor)` em memória."""
    c_para_s = _CanalBytes()
    s_para_c = _CanalBytes()
    return SocketEmMemoria(s_para_c, c_para_s), SocketEmMemoria(c_para_s, s_para_c)


def _montar_connect(client_id: str) -> bytes:
    cid = client_id.encode("utf-8")
    corpo = b"\x00\x04MQTT\x04\x02\x00\x3c" + len(cid).to_bytes(2, "big") + cid
    return b"\x10" + _codificar_remaining_length(len(corpo)) + corpo


def _montar_subscribe(packet_id: int, topico: str, qos: int = 1) -> bytes:
    top_bytes = topico.encode("utf-8")
    corpo = (
        packet_id.to_bytes(2, "big")
        + len(top_bytes).to_bytes(2, "big")
        + top_bytes
        + bytes([qos])
    )
    return b"\x82" + _codificar_remaining_length(len(corpo)) + corpo


def _montar_publish(topico: str, payload_bytes: bytes, qos: int = 1, packet_id: int = 1) -> bytes:
    top_bytes = topico.encode("utf-8")
    cabecalho_var = len(top_bytes).to_bytes(2, "big") + top_bytes
    if qos > 0:
        cabecalho_var += packet_id.to_bytes(2, "big")
    corpo = cabecalho_var + payload_bytes
    primeiro_byte = 0x30 | ((qos & 0x03) << 1)
    return bytes([primeiro_byte]) + _codificar_remaining_length(len(corpo)) + corpo


def _ler_pacote_mqtt(sock: SocketEmMemoria):
    b0 = sock.recv(1)
    assert len(b0) == 1
    primeiro_byte = b0[0]
    mult = 1
    rem_len = 0
    while True:
        b = sock.recv(1)[0]
        rem_len += (b & 0x7F) * mult
        if (b & 0x80) == 0:
            break
        mult *= 128
    corpo = bytearray()
    while len(corpo) < rem_len:
        corpo.extend(sock.recv(rem_len - len(corpo)))
    return primeiro_byte, bytes(corpo)


@pytest.fixture
def broker_memoria():
    """Instância do BrokerMQTTLocal pronta para atender conexões em memória."""
    broker = BrokerMQTTLocal(host="127.0.0.1", port=1883, silencioso=True)
    broker._rodando.set()

    def conectar_cliente(client_id: str) -> SocketEmMemoria:
        s_cli, s_srv = criar_par_sockets_memoria()
        with broker._lock:
            broker._clientes.add(s_srv)
        t = threading.Thread(
            target=broker._atender_cliente,
            args=(s_srv, ("127.0.0.1", 50000)),
            daemon=True,
        )
        t.start()
        s_cli.sendall(_montar_connect(client_id))
        assert s_cli.recv(4) == b"\x20\x02\x00\x00"
        return s_cli

    yield broker, conectar_cliente
    broker.parar()


def test_tp01_publish_qos1_wait_for_publish_e_recepcao(broker_memoria):
    """TP-01: Publicação com QoS 1 retorna PUBACK com mesmo packet_id e entrega payload ao assinante."""
    _, conectar = broker_memoria
    assinante = conectar("teste_sub_1")
    assinante.sendall(_montar_subscribe(packet_id=10, topico="estufa/sensores/umidade_solo", qos=1))
    tipo_suback, corpo_suback = _ler_pacote_mqtt(assinante)
    assert tipo_suback == 0x90
    assert corpo_suback == b"\x00\x0a\x01"

    publicador = conectar("teste_pub_1")
    payload_esperado = {"valor": 22.5, "unidade": "%", "timestamp": 1700000000.0}
    dados_json = json.dumps(payload_esperado).encode("utf-8")
    publicador.sendall(
        _montar_publish("estufa/sensores/umidade_solo", dados_json, qos=1, packet_id=42)
    )

    # Verifica PUBACK imediato para QoS 1 (libera wait_for_publish() do paho-mqtt)
    tipo_puback, corpo_puback = _ler_pacote_mqtt(publicador)
    assert tipo_puback == 0x40
    assert corpo_puback == (42).to_bytes(2, "big")

    # Verifica entrega ao assinante
    tipo_pub, corpo_pub = _ler_pacote_mqtt(assinante)
    assert (tipo_pub & 0xF0) == 0x30
    top_len = int.from_bytes(corpo_pub[0:2], "big")
    topico_recebido = corpo_pub[2 : 2 + top_len].decode("utf-8")
    payload_recebido = json.loads(corpo_pub[2 + top_len :].decode("utf-8"))
    assert topico_recebido == "estufa/sensores/umidade_solo"
    assert payload_recebido == payload_esperado


def test_tp02_fanout_multiplos_assinantes(broker_memoria):
    """TP-02: 3 assinantes no mesmo tópico recebem simultaneamente a leitura do sensor."""
    _, conectar = broker_memoria
    replicas = [conectar(f"ctrl_{i}") for i in (1, 2, 3)]
    for idx, rep in enumerate(replicas, start=1):
        rep.sendall(_montar_subscribe(packet_id=idx, topico="estufa/sensores/temperatura", qos=1))
        tipo, _ = _ler_pacote_mqtt(rep)
        assert tipo == 0x90

    sensor = conectar("sensor_estufa")
    leitura_bytes = json.dumps({"valor": 38.4, "unidade": "°C", "timestamp": 1700000100.0}).encode(
        "utf-8"
    )
    sensor.sendall(
        _montar_publish("estufa/sensores/temperatura", leitura_bytes, qos=1, packet_id=99)
    )
    tipo_ack, corpo_ack = _ler_pacote_mqtt(sensor)
    assert tipo_ack == 0x40 and corpo_ack == (99).to_bytes(2, "big")

    valores = []
    for rep in replicas:
        _, corpo = _ler_pacote_mqtt(rep)
        t_len = int.from_bytes(corpo[0:2], "big")
        valores.append(json.loads(corpo[2 + t_len :].decode("utf-8"))["valor"])

    assert valores == [38.4, 38.4, 38.4]


def test_te01_desconexao_abrupta_nao_afeta_outros_assinantes(broker_memoria):
    """TE-01: Desconexão abrupta de um cliente limpa o socket sem derrubar o broker."""
    _, conectar = broker_memoria
    cli_fantasma = conectar("fantasma")
    cli_fantasma.sendall(_montar_subscribe(packet_id=1, topico="estufa/atuadores/bomba", qos=1))
    _ler_pacote_mqtt(cli_fantasma)
    cli_fantasma.close()

    cli_estavel = conectar("cli_estavel")
    cli_estavel.sendall(_montar_subscribe(packet_id=2, topico="estufa/atuadores/bomba", qos=1))
    _ler_pacote_mqtt(cli_estavel)

    cli_estavel.sendall(
        _montar_publish("estufa/atuadores/bomba", b'{"acao": "ligar"}', qos=1, packet_id=7)
    )
    # Deve receber tanto o PUBACK quanto a mensagem publicada
    pacotes = {_ler_pacote_mqtt(cli_estavel)[0] & 0xF0, _ler_pacote_mqtt(cli_estavel)[0] & 0xF0}
    assert pacotes == {0x30, 0x40}


def test_te02_payload_maior_que_127_bytes_varint_multibyte(broker_memoria):
    """TE-02: Payloads > 127 bytes (varint de 2+ bytes) são codificados e entregues intactos."""
    for tamanho in (0, 127, 128, 300, 16384):
        codificado = _codificar_remaining_length(tamanho)
        assert _decodificar_remaining_length_bytes(codificado) == tamanho

    _, conectar = broker_memoria
    cli = conectar("cli_grande")
    cli.sendall(_montar_subscribe(packet_id=5, topico="estufa/status/bomba", qos=1))
    _ler_pacote_mqtt(cli)

    payload_grande = json.dumps({"dados": "X" * 512, "atuador": "bomba", "ligado": True}).encode(
        "utf-8"
    )
    cli.sendall(_montar_publish("estufa/status/bomba", payload_grande, qos=1, packet_id=55))

    recebido_publish = None
    for _ in range(2):
        tipo, corpo = _ler_pacote_mqtt(cli)
        if (tipo & 0xF0) == 0x30:
            t_len = int.from_bytes(corpo[0:2], "big")
            recebido_publish = corpo[2 + t_len :]

    assert recebido_publish == payload_grande


def test_te03_pacote_malformado_e_validacao_parametros(broker_memoria):
    """TE-03: Broker rejeita parâmetros inválidos e fecha conexões com pacotes malformados sem cair."""
    with pytest.raises(ValueError):
        BrokerMQTTLocal(host="127.0.0.1", port=70000)

    with pytest.raises(ValueError):
        BrokerMQTTLocal(host="", port=1883)

    with pytest.raises(ValueError):
        _decodificar_remaining_length_bytes(b"\x80\x80\x80\x80\x01")

    _, conectar = broker_memoria
    cli_ruim = conectar("cli_ruim")
    # Envia pacote com varint inválido (5 bytes com bit 0x80)
    cli_ruim.sendall(b"\x30\x80\x80\x80\x80\x01")

    # Outra conexão envia PINGREQ (0xC0 0x00) e recebe PINGRESP (0xD0 0x00), depois UNSUBSCRIBE e DISCONNECT
    cli_ping = conectar("cli_ping")
    cli_ping.sendall(b"\xC0\x00")
    assert cli_ping.recv(2) == b"\xD0\x00"

    top = b"estufa/teste"
    corpo_unsub = b"\x00\x09" + len(top).to_bytes(2, "big") + top
    cli_ping.sendall(b"\xA2" + _codificar_remaining_length(len(corpo_unsub)) + corpo_unsub)
    assert cli_ping.recv(4) == b"\xB0\x02\x00\x09"

    cli_ping.sendall(b"\xE0\x00")


def test_matching_topicos_wildcards():
    """Verifica casamento exato e wildcards '+' e '#'."""
    assert _topico_casa_filtro("estufa/sensores/temperatura", "estufa/sensores/temperatura")
    assert _topico_casa_filtro("estufa/sensores/temperatura", "estufa/+/temperatura")
    assert _topico_casa_filtro("estufa/sensores/temperatura", "estufa/#")
    assert not _topico_casa_filtro("estufa/sensores/temperatura", "estufa/atuadores/#")
