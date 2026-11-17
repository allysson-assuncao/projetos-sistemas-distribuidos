"""
broker_local.py — Broker MQTT v3.1.1 local em Python.

Implementa o servidor TCP MQTT utilizado para a comunicação pub/sub entre
sensores, controladores e atuadores usando a biblioteca padrão do Python.
Suporta CONNECT/CONNACK, SUBSCRIBE/SUBACK, PUBLISH/PUBACK (QoS 0 e 1),
PINGREQ/PINGRESP e DISCONNECT em localhost (127.0.0.1).
"""

import argparse
import socket
import threading
from typing import Dict, List, Optional, Set
from estufa import config


def _codificar_remaining_length(tamanho: int) -> bytes:
    """Codifica o campo Remaining Length no padrão varint do MQTT v3.1.1 (1 a 4 bytes)."""
    if tamanho < 0 or tamanho > 268_435_455:
        raise ValueError(f"Remaining length fora dos limites MQTT: {tamanho}")
    saida = bytearray()
    while True:
        byte = tamanho % 128
        tamanho //= 128
        if tamanho > 0:
            byte |= 0x80
        saida.append(byte)
        if tamanho == 0:
            break
    return bytes(saida)


def _decodificar_remaining_length_bytes(dados: bytes) -> int:
    """Decodifica varint MQTT (máximo 4 bytes) rejeitando pacotes corrompidos."""
    multiplicador = 1
    valor = 0
    for idx, byte in enumerate(dados):
        if idx >= 4:
            raise ValueError("Remaining Length excede 4 bytes (pacote MQTT malformado)")
        valor += (byte & 0x7F) * multiplicador
        if (byte & 0x80) == 0:
            return valor
        multiplicador *= 128
    raise ValueError("Remaining Length incompleto")


class BrokerMQTTLocal:
    """Servidor MQTT v3.1.1 enxuto com roteamento exato de tópicos e entrega QoS 0/1."""

    def __init__(self, host: str = "127.0.0.1", port: int = config.MQTT_PORT, silencioso: bool = False):
        if isinstance(port, bool) or not isinstance(port, int) or not (0 <= port <= 65535):
            raise ValueError(f"Porta inválida: {port}. Deve estar entre 0 e 65535.")
        if not host or not isinstance(host, str):
            raise ValueError("Host inválido.")
        self.host = host
        self.port = port
        self.silencioso = silencioso

        self._sock_servidor: Optional[socket.socket] = None
        self._rodando = threading.Event()
        self._lock = threading.Lock()
        self._assinaturas: Dict[str, Set[socket.socket]] = {}
        self._clientes: Set[socket.socket] = set()
        self._client_ids: Dict[socket.socket, str] = {}
        self._thread_aceitacao: Optional[threading.Thread] = None

    def _log(self, msg: str) -> None:
        if not self.silencioso:
            print(msg, flush=True)

    def iniciar_em_background(self) -> int:
        """Abre o socket TCP em thread daemon e retorna a porta vinculada."""
        self._sock_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock_servidor.bind((self.host, self.port))
        self.port = self._sock_servidor.getsockname()[1]
        self._sock_servidor.listen(64)
        self._sock_servidor.settimeout(0.5)
        self._rodando.set()

        self._thread_aceitacao = threading.Thread(
            target=self._loop_aceitacao,
            name="BrokerMQTT-Accept",
            daemon=True,
        )
        self._thread_aceitacao.start()
        self._log(f"[BROKER-MQTT] Ativo em {self.host}:{self.port} (MQTT v3.1.1 QoS 0/1)")
        return self.port

    def servir_para_sempre(self) -> None:
        """Mantém o broker ativo até receber Ctrl+C."""
        self.iniciar_em_background()
        try:
            while self._rodando.is_set():
                self._rodando.wait(timeout=1.0)
        except KeyboardInterrupt:
            self._log("\n[BROKER-MQTT] Encerrando broker...")
        finally:
            self.parar()

    def parar(self) -> None:
        """Encerra o socket servidor e desconecta clientes ativos."""
        self._rodando.clear()
        if self._sock_servidor is not None:
            try:
                self._sock_servidor.close()
            except OSError:
                pass
            self._sock_servidor = None

        with self._lock:
            clientes = list(self._clientes)
            self._clientes.clear()
            self._assinaturas.clear()
            self._client_ids.clear()

        for cli in clientes:
            try:
                cli.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                cli.close()
            except OSError:
                pass

        if self._thread_aceitacao is not None and self._thread_aceitacao.is_alive():
            self._thread_aceitacao.join(timeout=2.0)

    def _loop_aceitacao(self) -> None:
        while self._rodando.is_set() and self._sock_servidor is not None:
            try:
                conn, addr = self._sock_servidor.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._lock:
                self._clientes.add(conn)
            threading.Thread(
                target=self._atender_cliente,
                args=(conn, addr),
                daemon=True,
            ).start()

    @staticmethod
    def _ler_exato(conn: socket.socket, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _ler_remaining_length(self, conn: socket.socket) -> Optional[int]:
        multiplicador = 1
        valor = 0
        for _ in range(4):
            b = self._ler_exato(conn, 1)
            if b is None:
                return None
            byte = b[0]
            valor += (byte & 0x7F) * multiplicador
            if (byte & 0x80) == 0:
                return valor
            multiplicador *= 128
        raise ValueError("Remaining Length MQTT inválido (> 4 bytes)")

    def _remover_cliente(self, conn: socket.socket) -> None:
        """Remove assinaturas e fecha socket de clientes desconectados ou inválidos."""
        with self._lock:
            self._clientes.discard(conn)
            client_id = self._client_ids.pop(conn, None)
            for inscritos in self._assinaturas.values():
                inscritos.discard(conn)
        try:
            conn.close()
        except OSError:
            pass
        if client_id:
            self._log(f"[BROKER-MQTT] Cliente desconectado: {client_id}")

    # Loop de atendimento MQTT v3.1.1: trata conexão, assinatura, publicação e desconexão
    def _atender_cliente(self, conn: socket.socket, addr) -> None:
        try:
            while self._rodando.is_set():
                cabecalho = self._ler_exato(conn, 1)
                if cabecalho is None:
                    break
                primeiro_byte = cabecalho[0]
                tipo_pacote = primeiro_byte & 0xF0

                rem_len = self._ler_remaining_length(conn)
                if rem_len is None:
                    break

                payload = self._ler_exato(conn, rem_len) if rem_len > 0 else b""
                if payload is None:
                    break

                if tipo_pacote == 0x10:  # CONNECT
                    self._processar_connect(conn, payload, addr)
                elif tipo_pacote == 0x80:  # SUBSCRIBE
                    self._processar_subscribe(conn, payload)
                elif tipo_pacote == 0x30:  # PUBLISH
                    self._processar_publish(conn, primeiro_byte, payload)
                elif tipo_pacote == 0x40:  # PUBACK
                    pass
                elif tipo_pacote == 0xC0:  # PINGREQ
                    conn.sendall(b"\xD0\x00")
                elif tipo_pacote == 0xE0:  # DISCONNECT
                    break
                else:
                    raise ValueError(f"Tipo de pacote MQTT não suportado: 0x{tipo_pacote:02x}")
        except (ValueError, UnicodeDecodeError, IndexError, OSError):
            pass
        finally:
            self._remover_cliente(conn)

    def _processar_connect(self, conn: socket.socket, payload: bytes, addr) -> None:
        if len(payload) < 10:
            raise ValueError("Pacote CONNECT muito curto")
        proto_len = int.from_bytes(payload[0:2], "big")
        idx = 2 + proto_len + 4
        client_id = f"{addr[0]}:{addr[1]}"
        if len(payload) >= idx + 2:
            cid_len = int.from_bytes(payload[idx : idx + 2], "big")
            if len(payload) >= idx + 2 + cid_len:
                texto_id = payload[idx + 2 : idx + 2 + cid_len].decode("utf-8")
                if texto_id:
                    client_id = texto_id

        with self._lock:
            self._client_ids[conn] = client_id

        conn.sendall(b"\x20\x02\x00\x00")  # CONNACK aceito
        self._log(f"[BROKER-MQTT] Cliente conectado: {client_id}")

    def _processar_subscribe(self, conn: socket.socket, payload: bytes) -> None:
        if len(payload) < 5:
            raise ValueError("Pacote SUBSCRIBE inválido")
        packet_id = payload[0:2]
        idx = 2
        codigos: List[int] = []

        while idx < len(payload):
            if idx + 2 > len(payload):
                raise ValueError("Tópico truncado no SUBSCRIBE")
            topico_len = int.from_bytes(payload[idx : idx + 2], "big")
            idx += 2
            if idx + topico_len + 1 > len(payload):
                raise ValueError("Conteúdo truncado no SUBSCRIBE")
            topico = payload[idx : idx + topico_len].decode("utf-8")
            idx += topico_len
            qos = min(payload[idx] & 0x03, 1)
            idx += 1

            with self._lock:
                self._assinaturas.setdefault(topico, set()).add(conn)
                cid = self._client_ids.get(conn, "cliente")

            codigos.append(qos)
            self._log(f"[BROKER-MQTT] Assinatura: {cid} -> '{topico}' (QoS {qos})")

        corpo = packet_id + bytes(codigos)
        conn.sendall(b"\x90" + _codificar_remaining_length(len(corpo)) + corpo)

    def _processar_publish(self, conn: socket.socket, primeiro_byte: int, payload: bytes) -> None:
        if len(payload) < 2:
            raise ValueError("Pacote PUBLISH inválido")
        qos = (primeiro_byte >> 1) & 0x03
        topico_len = int.from_bytes(payload[0:2], "big")
        idx = 2 + topico_len
        if len(payload) < idx:
            raise ValueError("Tópico truncado no PUBLISH")
        topico = payload[2:idx].decode("utf-8")

        if qos > 0:
            if len(payload) < idx + 2:
                raise ValueError("Packet ID ausente em PUBLISH QoS > 0")
            packet_id = payload[idx : idx + 2]
            idx += 2
            if qos == 1:
                # PUBACK imediato garante confirmação de entrega QoS 1 ao publicador
                conn.sendall(b"\x40\x02" + packet_id)

        mensagem = payload[idx:]
        topico_bytes = topico.encode("utf-8")
        corpo = len(topico_bytes).to_bytes(2, "big") + topico_bytes + mensagem
        pacote = b"\x30" + _codificar_remaining_length(len(corpo)) + corpo

        with self._lock:
            destinatarios = set(self._assinaturas.get(topico, ()))

        falhos: List[socket.socket] = []
        for sock in destinatarios:
            try:
                sock.sendall(pacote)
            except OSError:
                falhos.append(sock)

        for sock in falhos:
            self._remover_cliente(sock)


def _porta_em_uso(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def executar_broker(host: str = "127.0.0.1", port: int = config.MQTT_PORT) -> None:
    """Valida parâmetros, verifica disponibilidade da porta e inicia o broker local."""
    if not host or not isinstance(host, str):
        raise ValueError("Host inválido.")
    if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"Porta inválida: {port}. Deve estar entre 1 e 65535.")

    if _porta_em_uso(host, port):
        print(f"[BROKER-MQTT] Porta {port} já está em uso em {host}. Encerrando.")
        return

    BrokerMQTTLocal(host=host, port=port).servir_para_sempre()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Broker MQTT v3.1.1 Local (Python Puro)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="IP de bind (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=config.MQTT_PORT, help=f"Porta TCP (padrão: {config.MQTT_PORT})")
    args = parser.parse_args()
    executar_broker(host=args.host, port=args.port)
