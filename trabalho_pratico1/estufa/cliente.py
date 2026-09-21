"""
cliente.py — User Interface for the Greenhouse Control System.

The client connects EXCLUSIVELY to the Middleware Server (port 9000) via XML-RPC.
It has no knowledge of individual controllers, voting, or fault tolerance.
All distributed system complexity is encapsulated in the Middleware Server.

Architecture:
    [Client] --XML-RPC:9000--> [Middleware Server @ :9000] --XML-RPC--> [Controllers]

Usage:
    python -m estufa.cliente
    python -m estufa.cliente --auto         # Auto mode: polls state every 3s
    python -m estufa.cliente --host HOST --port PORT  # Custom middleware address
"""

import argparse
import time
import xmlrpc.client
from estufa import config


class ErroMiddleware(Exception):
    """Raised when the Middleware Server is unreachable or returns an error."""
    pass


def _criar_proxy(host: str, port: int) -> xmlrpc.client.ServerProxy:
    """Creates an XML-RPC proxy connected to the Middleware Server."""
    return xmlrpc.client.ServerProxy(
        f"http://{host}:{port}",
        allow_none=True
    )


def exibir_estado(estado: dict) -> None:
    """Formats and displays the current greenhouse state."""
    print("\n" + "═" * 50)
    print("         🌿 ESTADO ATUAL DA ESTUFA 🌿")
    print("═" * 50)

    temp     = estado.get("temperatura")
    umidade  = estado.get("umidade_solo")
    bomba    = estado.get("bomba_ligada")
    exaustor = estado.get("exaustor_ligado")

    print(f"  🌡️  Temperatura:   {f'{temp:.2f}°C' if temp is not None else 'N/A'}")
    print(f"  💧 Umidade solo:  {f'{umidade:.2f}%' if umidade is not None else 'N/A'}")
    print(f"  🚿 Bomba:         {'🟢 LIGADA' if bomba else '🔴 DESLIGADA'}")
    print(f"  💨 Exaustor:      {'🟢 LIGADO' if exaustor else '🔴 DESLIGADO'}")
    print("═" * 50 + "\n")


def menu_interativo(proxy: xmlrpc.client.ServerProxy) -> None:
    """Main interactive menu loop."""
    while True:
        print("\n📋 MENU — Estufa Agrícola Distribuída")
        print(f"  [Middleware: {proxy._ServerProxy__host}]")
        print("  1. Consultar estado atual")
        print("  2. Ligar bomba de irrigação")
        print("  3. Desligar bomba de irrigação")
        print("  4. Ligar exaustor")
        print("  5. Desligar exaustor")
        print("  6. Verificar saúde dos controladores")
        print("  0. Sair")

        escolha = input("\n▶ Escolha: ").strip()

        try:
            if escolha == "1":
                estado = proxy.obter_estado()
                exibir_estado(estado)

            elif escolha == "2":
                resp = proxy.comandar_bomba("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "3":
                resp = proxy.comandar_bomba("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "4":
                resp = proxy.comandar_exaustor("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "5":
                resp = proxy.comandar_exaustor("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "6":
                saude = proxy.verificar_saude()
                print("\n🏥 Saúde dos Controladores:")
                for ctrl_id, status in saude.items():
                    icone = "🟢" if status == "ok" else "🔴"
                    print(f"  {icone} {ctrl_id}: {status}")

            elif escolha == "0":
                print("👋 Encerrando cliente.")
                break

            else:
                print("⚠️  Opção inválida.")

        except xmlrpc.client.Fault as e:
            print(f"\n❌ ERRO DO MIDDLEWARE: {e.faultString}")
            print("   O sistema não conseguiu atingir consenso. Verifique os controladores.")
        except ConnectionRefusedError:
            print(f"\n❌ MIDDLEWARE OFFLINE: Não foi possível conectar a porta {config.MIDDLEWARE_PORT}.")
            print("   Execute: python -m estufa.middleware_server")


def modo_automatico(proxy: xmlrpc.client.ServerProxy, intervalo: float = 3.0) -> None:
    """Displays greenhouse state in an auto-polling loop."""
    print(f"🤖 Modo automático: consultando a cada {intervalo}s. Ctrl+C para parar.")
    try:
        while True:
            try:
                estado = proxy.obter_estado()
                exibir_estado(estado)
            except xmlrpc.client.Fault as e:
                print(f"❌ ERRO DO MIDDLEWARE: {e.faultString}")
            except ConnectionRefusedError:
                print(f"❌ MIDDLEWARE OFFLINE em porta {config.MIDDLEWARE_PORT}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\n👋 Encerrando.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente — Estufa Agrícola Distribuída")
    parser.add_argument("--auto",      action="store_true",              help="Auto mode (polling)")
    parser.add_argument("--intervalo", type=float, default=3.0,          help="Auto mode interval (seconds)")
    parser.add_argument("--host",      default=config.MIDDLEWARE_HOST,   help="Middleware host")
    parser.add_argument("--port",      default=config.MIDDLEWARE_PORT,   type=int, help="Middleware port")
    args = parser.parse_args()

    proxy = _criar_proxy(args.host, args.port)

    if args.auto:
        modo_automatico(proxy, intervalo=args.intervalo)
    else:
        menu_interativo(proxy)
