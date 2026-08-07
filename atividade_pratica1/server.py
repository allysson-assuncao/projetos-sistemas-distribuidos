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
    import tomllib
except ImportError:
    try:
        # pyrefly: ignore [missing-import]
        import tomli as tomllib
    except ImportError:
        tomllib = None

HOST = '127.0.0.1'
PORT = 65432
FORMAT_LENGTH = 10

COLORS = {
    'csv':  '\033[96m',   # Ciano
    'json': '\033[92m',   # Verde
    'xml':  '\033[93m',   # Amarelo
    'yaml': '\033[95m',   # Magenta
    'toml': '\033[94m',   # Azul
}
RESET = '\033[0m'
BOLD  = '\033[1m'


def recv_all(conn, length):
    data = b''
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            raise ConnectionError("Conexão encerrada pelo cliente")
        data += chunk
    return data


def recv_message(conn):
    raw_len = recv_all(conn, 4)
    msg_len = struct.unpack('>I', raw_len)[0]
    raw_fmt = recv_all(conn, FORMAT_LENGTH)
    fmt = raw_fmt.decode('utf-8').strip()
    payload = recv_all(conn, msg_len)
    return fmt, payload.decode('utf-8')


def display_csv(data_str, color):
    reader = csv.DictReader(io.StringIO(data_str))
    rows = list(reader)
    if not rows:
        return
    keys = list(rows[0].keys())
    col_widths = [max(len(k), max(len(r[k]) for r in rows)) for k in keys]
    sep = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'
    header = '|' + '|'.join(f' {k:<{w}} ' for k, w in zip(keys, col_widths)) + '|'
    print(color + BOLD)
    print('╔══ [CSV] ' + '═' * 50)
    print(sep)
    print(header)
    print(sep)
    for row in rows:
        line = '|' + '|'.join(f' {row[k]:<{w}} ' for k, w in zip(keys, col_widths)) + '|'
        print(line)
    print(sep)
    print('╚' + '═' * 59 + RESET)


def display_json(data_str, color):
    obj = json.loads(data_str)
    print(color + BOLD)
    print('╔══ [JSON] ' + '═' * 49)
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    print('╚' + '═' * 59 + RESET)


def display_xml(data_str, color):
    root = ET.fromstring(data_str)
    ET.indent(root, space='  ')
    print(color + BOLD)
    print('╔══ [XML] ' + '═' * 50)
    print('<?xml version="1.0" encoding="UTF-8"?>')
    print(ET.tostring(root, encoding='unicode'))
    print('╚' + '═' * 59 + RESET)


def display_yaml(data_str, color):
    if yaml is None:
        print("PyYAML não instalado!")
        return
    obj = yaml.safe_load(data_str)
    print(color + BOLD)
    print('╔══ [YAML] ' + '═' * 49)
    print('---')
    print(yaml.dump(obj, allow_unicode=True, default_flow_style=False).strip())
    print('╚' + '═' * 59 + RESET)


def display_toml(data_str, color):
    if tomllib is None:
        print("tomllib/tomli não instalado!")
        return
    obj = tomllib.loads(data_str)
    print(color + BOLD)
    print('╔══ [TOML] ' + '═' * 49)
    for section, values in obj.items():
        print(f'[{section}]')
        for k, v in values.items():
            val_str = f'"{v}"' if isinstance(v, str) else str(v)
            print(f'{k} = {val_str}')
    print('╚' + '═' * 59 + RESET)


DISPLAY_HANDLERS = {
    'csv':  display_csv,
    'json': display_json,
    'xml':  display_xml,
    'yaml': display_yaml,
    'toml': display_toml,
}


def handle_client(conn, addr):
    print(f"\n{'='*60}")
    print(f"  Nova conexão de {addr}")
    print(f"{'='*60}")
    try:
        for i in range(5):
            fmt, data_str = recv_message(conn)
            color = COLORS.get(fmt, '')
            print(f"\n{'─'*60}")
            print(f"  Mensagem {i+1}/5 — Formato: {BOLD}{fmt.upper()}{RESET}")
            print(f"{'─'*60}")
            handler = DISPLAY_HANDLERS.get(fmt)
            if handler:
                handler(data_str, color)
            else:
                print(f"Formato desconhecido: {fmt}")
            ack = f"ACK:{fmt.upper()}:OK".encode('utf-8')
            conn.sendall(struct.pack('>I', len(ack)) + ack)
    except Exception as e:
        print(f"Erro ao processar cliente: {e}")
    finally:
        conn.close()
        print(f"\n{'='*60}")
        print("  Conexão encerrada.")
        print(f"{'='*60}")


def main():
    print(f"\n{'='*60}")
    print("  SERVIDOR DE SERIALIZAÇÃO — Atividade Prática 1 SD")
    print(f"  Escutando em {HOST}:{PORT}")
    print(f"{'='*60}\n")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            handle_client(conn, addr)


if __name__ == '__main__':
    main()
