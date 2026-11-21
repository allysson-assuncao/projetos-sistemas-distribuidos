"""
cliente.py — Interface de linha de comando para monitoramento e controle da estufa.

Comunica-se diretamente com os controladores ativos via camada lógica XML-RPC
(ClusterMiddleware), com descoberta automática de líder e failover transparente
caso algum controlador seja encerrado durante a apresentação.

Uso:
    python -m estufa.cliente
    python -m estufa.cliente --auto [--intervalo SEGUNDOS]
"""

import argparse
import socket
import time
import xmlrpc.client
from estufa.middleware import ClusterMiddleware, ErroQuorum


def exibir_estado(estado: dict) -> None:
    """Formata e exibe no terminal o estado consolidado da estufa."""
    print("\n" + "=" * 52)
    print("             ESTADO ATUAL DA ESTUFA")
    print("=" * 52)

    temp = estado.get("temperatura")
    umidade = estado.get("umidade")
    bomba = estado.get("bomba_ligada")
    exaustor = estado.get("exaustor_ligado")
    lider = estado.get("lider_id") or "N/A"

    print(f"  Temperatura:   {f'{temp:.2f}°C' if temp is not None else 'N/A'}")
    print(f"  Umidade solo:  {f'{umidade:.2f}%' if umidade is not None else 'N/A'}")
    print(f"  Bomba:         {'LIGADA' if bomba else 'DESLIGADA'}")
    print(f"  Exaustor:      {'LIGADO' if exaustor else 'DESLIGADO'}")
    print(f"  Líder atual:   {lider}")
    print("=" * 52 + "\n")


# Tratamento resiliente de falhas RPC/rede: cliente continua operando mesmo com queda de nós
def _executar_acao_segura(funcao, *args) -> None:
    """Executa uma chamada ao cluster tratando falhas de quórum ou rede sem abortar o cliente."""
    try:
        resultado = funcao(*args)
        if isinstance(resultado, dict) and "mensagem" in resultado:
            lider = resultado.get("lider_id", "N/A")
            print(f"[OK] {resultado['mensagem']} (via líder: {lider})")
        elif isinstance(resultado, dict):
            exibir_estado(resultado)
        else:
            print(f"[OK] {resultado}")
    except ErroQuorum as e:
        print(f"\n[FALHA DE CONSENSO/QUÓRUM] {e}")
    except xmlrpc.client.Fault as e:
        print(f"\n[ERRO DO CONTROLADOR] {e.faultString}")
    except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError) as e:
        print(f"\n[CLUSTER INDISPONÍVEL] Nenhum controlador respondeu: {e}")


def menu_interativo(middleware: ClusterMiddleware) -> None:
    """Loop principal do menu interativo de operação direta com o cluster."""
    acoes = {
        "2": ("Ligar bomba", middleware.comandar_bomba, True),
        "3": ("Desligar bomba", middleware.comandar_bomba, False),
        "4": ("Ligar exaustor", middleware.comandar_exaustor, True),
        "5": ("Desligar exaustor", middleware.comandar_exaustor, False),
    }

    while True:
        nos = ", ".join(f"{c['id']}:{c['port']}" for c in middleware.controladores)
        print("\nMENU — Estufa Agrícola Distribuída (RPC Direto)")
        print(f"  [Cluster: {nos}]")
        print("  1. Consultar estado atual (com consenso)")
        print("  2. Ligar bomba de irrigação")
        print("  3. Desligar bomba de irrigação")
        print("  4. Ligar exaustor")
        print("  5. Desligar exaustor")
        print("  6. Verificar saúde e liderança dos controladores")
        print("  0. Sair")

        try:
            escolha = input("\nEscolha: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando cliente.")
            break

        if escolha == "1":
            _executar_acao_segura(middleware.obter_estado)
        elif escolha in acoes:
            _, funcao, valor = acoes[escolha]
            _executar_acao_segura(funcao, valor)
        elif escolha == "6":
            saude = middleware.verificar_saude()
            print(
                f"\nSaúde do Cluster ({saude['ativos']}/{saude['total']} ativos | "
                f"Líder: {saude.get('lider_id') or 'indefinido'}):"
            )
            for ctrl_id, status in saude["detalhes"].items():
                tag = "[OK]" if status.startswith("ok") else "[FALHA]"
                print(f"  {tag} {ctrl_id}: {status}")
        elif escolha == "0":
            print("Encerrando cliente.")
            break
        else:
            print("[AVISO] Opção inválida.")


def modo_automatico(middleware: ClusterMiddleware, intervalo: float = 3.0) -> None:
    """Consulta e exibe periodicamente o estado oficial da estufa."""
    print(f"Modo automático ativo (intervalo: {intervalo}s). Pressione Ctrl+C para encerrar.")
    try:
        while True:
            _executar_acao_segura(middleware.obter_estado)
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\nEncerrando.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente — Estufa Agrícola Distribuída")
    parser.add_argument("--auto", action="store_true", help="Modo de consulta contínua")
    parser.add_argument("--intervalo", type=float, default=3.0, help="Intervalo do modo contínuo (s)")
    args = parser.parse_args()

    # Middleware embarcado no cliente: descobre e roteia direto para o controlador líder
    mw = ClusterMiddleware()
    if args.auto:
        modo_automatico(mw, intervalo=args.intervalo)
    else:
        menu_interativo(mw)
