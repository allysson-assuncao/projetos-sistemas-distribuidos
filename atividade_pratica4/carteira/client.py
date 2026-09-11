"""
client.py — gRPC Client: Digital Wallet Service
Atividade Prática 4 — Distributed Systems

Features:
  - All calls use configurable deadlines (timeout parameter)
  - gRPC errors are caught and displayed with status code
  - Functions are importable by run_experiments.py

Import note: this file is inside the carteira/ package. When imported externally,
__init__.py ensures sys.path is set correctly for carteira_pb2 stubs.
"""

import grpc
import carteira_pb2
import carteira_pb2_grpc

DEFAULT_HOST    = "localhost"
DEFAULT_PORT    = 50051
DEFAULT_TIMEOUT = 5.0  # seconds — default deadline


def get_stub(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Create and return a CarteiraService stub and its underlying channel."""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub    = carteira_pb2_grpc.CarteiraServiceStub(channel)
    return stub, channel


def criar_conta(
    stub,
    conta_id: str,
    nome_titular: str,
    saldo_inicial: float,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the CriarConta RPC with deadline."""
    try:
        req  = carteira_pb2.CriarContaRequest(
            conta_id=conta_id,
            nome_titular=nome_titular,
            saldo_inicial=saldo_inicial,
        )
        resp = stub.CriarConta(req, timeout=timeout)
        print(f"[CriarConta] ✓ {resp.mensagem} | Balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[CriarConta] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def consultar_saldo(
    stub,
    conta_id: str,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the ConsultarSaldo RPC with deadline."""
    try:
        req  = carteira_pb2.ContaRequest(conta_id=conta_id)
        resp = stub.ConsultarSaldo(req, timeout=timeout)
        print(f"[ConsultarSaldo] ✓ Account: {resp.conta_id} | Holder: {resp.nome_titular} | Balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[ConsultarSaldo] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def depositar(
    stub,
    conta_id: str,
    valor: float,
    descricao: str = "",
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Depositar RPC with deadline."""
    try:
        req  = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Depositar(req, timeout=timeout)
        print(f"[Depositar] ✓ {resp.mensagem} | New balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Depositar] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def sacar(
    stub,
    conta_id: str,
    valor: float,
    descricao: str = "",
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Sacar RPC with deadline."""
    try:
        req  = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Sacar(req, timeout=timeout)
        print(f"[Sacar] ✓ {resp.mensagem} | New balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Sacar] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def transferir(
    stub,
    conta_origem: str,
    conta_destino: str,
    valor: float,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Transferir RPC with deadline."""
    try:
        req  = carteira_pb2.TransferirRequest(
            conta_origem=conta_origem,
            conta_destino=conta_destino,
            valor=valor,
        )
        resp = stub.Transferir(req, timeout=timeout)
        print(f"[Transferir] ✓ {resp.mensagem} | Source balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Transferir] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


# Interactive demo — run directly
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Client — Digital Wallet")
    parser.add_argument("--host",    type=str,   default=DEFAULT_HOST,    help="Server host")
    parser.add_argument("--port",    type=int,   default=DEFAULT_PORT,    help="Server port")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Deadline in seconds")
    args = parser.parse_args()

    print(f"\n=== Digital Wallet Client | {args.host}:{args.port} | timeout={args.timeout}s ===\n")

    stub, channel = get_stub(args.host, args.port)

    with channel:
        print("─── Creating new account ───")
        criar_conta(stub, "099", "Diego Teste", 100.0, timeout=args.timeout)

        print("\n─── Querying initial balances ───")
        consultar_saldo(stub, "001", timeout=args.timeout)
        consultar_saldo(stub, "002", timeout=args.timeout)

        print("\n─── Deposit ───")
        depositar(stub, "001", 250.0, "Salary", timeout=args.timeout)

        print("\n─── Withdrawal ───")
        sacar(stub, "001", 100.0, "Rent", timeout=args.timeout)

        print("\n─── Transfer ───")
        transferir(stub, "001", "002", 50.0, timeout=args.timeout)

        print("\n─── Expected error cases ───")

        print("\n[Test] Query non-existent account (NOT_FOUND):")
        consultar_saldo(stub, "999", timeout=args.timeout)

        print("\n[Test] Deposit with negative value (INVALID_ARGUMENT):")
        depositar(stub, "001", -50.0, timeout=args.timeout)

        print("\n[Test] Withdrawal with insufficient funds (FAILED_PRECONDITION):")
        sacar(stub, "003", 99999.0, timeout=args.timeout)

        print("\n[Test] Create duplicate account (ALREADY_EXISTS):")
        criar_conta(stub, "001", "Alice Duplicate", 0.0, timeout=args.timeout)

    print("\n=== End of Demo ===\n")
