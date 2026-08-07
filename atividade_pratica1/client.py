import socket
import struct
import csv
import json
import xml.etree.ElementTree as ET
import io

try:
    import yaml
except ImportError:
    yaml = None

try:
    import tomli_w
except ImportError:
    tomli_w = None

HOST = '127.0.0.1'
PORT = 65432
FORMAT_LENGTH = 10
BOLD  = '\033[1m'
RESET = '\033[0m'

DADOS = {
    'nome':     'Fulano da Silva',
    'cpf':      '10326709722',
    'idade':    25,
    'mensagem': 'mensagem de teste enviada pelo cliente',
}

# ── Serializadores específicos por formato ────────────────────────────────────

def serialize_csv(dados: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=dados.keys())
    writer.writeheader()
    writer.writerow(dados)
    return output.getvalue()


def serialize_json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2)


def serialize_xml(dados: dict) -> str:
    root = ET.Element('pessoa')
    for key, value in dados.items():
        child = ET.SubElement(root, key)
        child.text = str(value)
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode', xml_declaration=False)


def serialize_yaml(dados: dict) -> str:
    if yaml is None:
        raise RuntimeError("PyYAML não instalado. Execute: pip install pyyaml")
    return yaml.dump(dados, allow_unicode=True, default_flow_style=False)


def serialize_toml(dados: dict) -> str:
    if tomli_w is None:
        raise RuntimeError("tomli-w não instalado. Execute: pip install tomli-w")
    # TOML requer estrutura com seção; encapsulamos em [pessoa]
    wrapped = {'pessoa': {k: str(v) if isinstance(v, int) else v for k, v in dados.items()}}
    return tomli_w.dumps(wrapped)


SERIALIZERS = [
    ('csv',  serialize_csv),
    ('json', serialize_json),
    ('xml',  serialize_xml),
    ('yaml', serialize_yaml),
    ('toml', serialize_toml),
]

COLORS = {
    'csv':  '\033[96m',
    'json': '\033[92m',
    'xml':  '\033[93m',
    'yaml': '\033[95m',
    'toml': '\033[94m',
}

# Utilitários pro protocolo de mensagens
def send_message(sock, fmt: str, data_str: str):
    payload = data_str.encode('utf-8')
    fmt_bytes = fmt.ljust(FORMAT_LENGTH).encode('utf-8')
    header = struct.pack('>I', len(payload))
    sock.sendall(header + fmt_bytes + payload)


def recv_ack(sock) -> str:
    raw_len = b''
    while len(raw_len) < 4:
        raw_len += sock.recv(4 - len(raw_len))
    msg_len = struct.unpack('>I', raw_len)[0]
    data = b''
    while len(data) < msg_len:
        data += sock.recv(msg_len - len(data))
    return data.decode('utf-8')

# Main
def main():
    print(f"\n{'='*60}")
    print("  CLIENTE DE SERIALIZAÇÃO — Atividade Prática 1 SD")
    print(f"  Conectando a {HOST}:{PORT}")
    print(f"{'='*60}\n")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        print(f"  Conectado com sucesso!\n")

        for i, (format, serializer) in enumerate(SERIALIZERS, start=1):
            color = COLORS.get(format, '')
            serialized = serializer(DADOS)

            print(f"{'─'*60}")
            print(f"  Enviando mensagem {i}/5 — Formato: {BOLD}{format.upper()}{RESET}")
            print(f"{'─'*60}")
            print(color + serialized.strip() + RESET)

            send_message(s, format, serialized)
            ack = recv_ack(s)
            print(f"\n  ✔ Servidor respondeu: {BOLD}{ack}{RESET}\n")


if __name__ == '__main__':
    main()
