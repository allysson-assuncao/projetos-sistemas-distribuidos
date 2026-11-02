"""
cliente.py — Interface de linha de comando para monitoramento e controle da estufa.

Comunica-se exclusivamente com o servidor de Middleware via XML-RPC (porta 9000),
mantendo transparência de localização e de replicação em relação aos controladores.

Uso:
    python -m estufa.cliente
    python -m estufa.cliente --auto [--intervalo SEGUNDOS]
    python -m estufa.cliente --host HOST --port PORT
"""

import argparse
import time
import xmlrpc.client
from estufa import config


def _criar_proxy(host: str, port: int) -> xmlrpc.client.ServerProxy:
    """Cria um proxy XML-RPC apontando para o servidor de Middleware."""
    return xmlrpc.client.ServerProxy(f"http://{host}:{port}", allow_none=True)


def exibir_estado(estado: dict) -> None:
    """Formata e exibe no terminal o estado consolidado da estufa."""
    print("\n" + "=" * 50)
    print("           ESTADO ATUAL DA ESTUFA")
    print("=" * 50)

    temp = estado.get("temperatura")
    umidade = estado.get("umidade_solo")
    bomba = estado.get("bomba_ligada")
    exaustor = estado.get("exaustor_ligado")

    print(f"  Temperatura:   {f'{temp:.2f}°C' if temp is not None else 'N/A'}")
    print(f"  Umidade solo:  {f'{umidade:.2f}%' if umidade is not None else 'N/A'}")
    print(f"  Bomba:         {'LIGADA' if bomba else 'DESLIGADA'}")
    print(f"  Exaustor:      {'LIGADO' if exaustor else 'DESLIGADO'}")
    print("=" * 50 + "\n")


def menu_interativo(proxy: xmlrpc.client.ServerProxy, endereco: str = "") -> None:
    """Loop principal do menu interativo de operação."""
    if not endereco:
        endereco = f"{config.MIDDLEWARE_HOST}:{config.MIDDLEWARE_PORT}"

    while True:
        print("\nMENU — Estufa Agrícola Distribuída")
        print(f"  [Middleware: {endereco}]")
        print("  1. Consultar estado atual")
        print("  2. Ligar bomba de irrigação")
        print("  3. Desligar bomba de irrigação")
        print("  4. Ligar exaustor")
        print("  5. Desligar exaustor")
        print("  6. Verificar saúde dos controladores")
        print("  0. Sair")

        escolha = input("\nEscolha: ").strip()

        try:
            if escolha == "1":
                estado = proxy.obter_estado()
                exibir_estado(estado)

            elif escolha == "2":
                resp = proxy.comandar_bomba("ligar")
                print(f"[OK] {resp.get('mensagem', resp)}")

            elif escolha == "3":
                resp = proxy.comandar_bomba("desligar")
                print(f"[OK] {resp.get('mensagem', resp)}")

            elif escolha == "4":
                resp = proxy.comandar_exaustor("ligar")
                print(f"[OK] {resp.get('mensagem', resp)}")

            elif escolha == "5":
                resp = proxy.comandar_exaustor("desligar")
                print(f"[OK] {resp.get('mensagem', resp)}")

            elif escolha == "6":
                saude = proxy.verificar_saude()
                print("\nSaúde dos Controladores:")
                for ctrl_id, status in saude.items():
                    tag = "[OK]" if status == "ok" else "[FALHA]"
                    print(f"  {tag} {ctrl_id}: {status}")

            elif escolha == "0":
                print("Encerrando cliente.")
                break

            else:
                print("[AVISO] Opção inválida.")

        except xmlrpc.client.Fault as e:
            print(f"\n[ERRO DO MIDDLEWARE] {e.faultString}")
            print("  O sistema não conseguiu atingir quórum. Verifique os controladores.")
        except ConnectionRefusedError:
            print(f"\n[MIDDLEWARE OFFLINE] Não foi possível conectar em {endereco}.")
            print("  Certifique-se de que 'python -m estufa.middleware_server' está em execução.")


def modo_automatico(proxy: xmlrpc.client.ServerProxy, intervalo: float = 3.0) -> None:
    """Consulta e exibe periodicamente o estado da estufa."""
    print(f"Modo automático ativo (intervalo: {intervalo}s). Pressione Ctrl+C para encerrar.")
    try:
        while True:
            try:
                estado = proxy.obter_estado()
                exibir_estado(estado)
            except xmlrpc.client.Fault as e:
                print(f"[ERRO DO MIDDLEWARE] {e.faultString}")
            except ConnectionRefusedError:
                print(f"[MIDDLEWARE OFFLINE] Falha de conexão na porta {config.MIDDLEWARE_PORT}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\nEncerrando.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente — Estufa Agrícola Distribuída")
    parser.add_argument("--auto", action="store_true", help="Modo de consulta contínua")
    parser.add_argument("--intervalo", type=float, default=3.0, help="Intervalo do modo contínuo (s)")
    parser.add_argument("--host", default=config.MIDDLEWARE_HOST, help="Host do Middleware")
    parser.add_argument("--port", default=config.MIDDLEWARE_PORT, type=int, help="Porta do Middleware")
    args = parser.parse_args()

    proxy = _criar_proxy(args.host, args.port)
    endereco_mw = f"{args.host}:{args.port}"

    if args.auto:
        modo_automatico(proxy, intervalo=args.intervalo)
    else:
        menu_interativo(proxy, endereco=endereco_mw)
