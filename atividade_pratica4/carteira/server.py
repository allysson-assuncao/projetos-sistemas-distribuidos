"""
server.py — gRPC Server: Digital Wallet Service
Atividade Prática 4 — Distributed Systems

Features:
  - In-memory storage via AccountStore (granular per-account locking)
  - Synchronous style with ThreadPoolExecutor
  - Validation using at least 4 distinct gRPC status codes:
      INVALID_ARGUMENT, NOT_FOUND, ALREADY_EXISTS, FAILED_PRECONDITION
  - Optional artificial delay for deadline experiments (--delay flag)
"""

import time
import grpc
from concurrent import futures

# Fix 1 — importing from the carteira package triggers __init__.py,
# which injects carteira/ into sys.path, making protoc stubs resolvable.
import carteira_pb2
import carteira_pb2_grpc
from store import AccountStore


# ─────────────────────────────────────────────────────────────────────────────
# Servicer Implementation
# ─────────────────────────────────────────────────────────────────────────────

class CarteiraServicer(carteira_pb2_grpc.CarteiraServiceServicer):
    """
    Implements all RPC methods defined in carteira.proto.

    gRPC status codes used:
      INVALID_ARGUMENT    → negative/zero values, empty required fields
      NOT_FOUND           → account does not exist
      ALREADY_EXISTS      → duplicate account creation
      FAILED_PRECONDITION → insufficient funds
    """

    def __init__(self, store: AccountStore, delay_seconds: float = 0.0):
        self._store = store
        self._delay_seconds = delay_seconds

    def _apply_delay(self):
        """Inject artificial latency for deadline experiments."""
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

    # ------------------------------------------------------------------
    # CriarConta
    # ------------------------------------------------------------------
    def CriarConta(self, request, context):
        conta_id      = request.conta_id.strip()
        nome_titular  = request.nome_titular.strip()
        saldo_inicial = request.saldo_inicial

        if not conta_id or not nome_titular:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_id and nome_titular are required and cannot be empty.",
            )

        if saldo_inicial < 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"saldo_inicial cannot be negative. Received: {saldo_inicial}",
            )

        try:
            saldo = self._store.create(conta_id, nome_titular, saldo_inicial)
        except KeyError as exc:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(exc))

        print(f"[CriarConta] conta={conta_id}, titular={nome_titular}, saldo_inicial={saldo_inicial:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=saldo,
            mensagem=f"Account '{conta_id}' successfully created for {nome_titular}.",
        )

    # ------------------------------------------------------------------
    # ConsultarSaldo
    # ------------------------------------------------------------------
    def ConsultarSaldo(self, request, context):
        conta_id = request.conta_id.strip()

        if not conta_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "conta_id is required.")

        try:
            data = self._store.query(conta_id)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        print(f"[ConsultarSaldo] conta={conta_id}, saldo={data['saldo_atual']:.2f}")
        return carteira_pb2.SaldoResponse(
            conta_id=data["conta_id"],
            nome_titular=data["nome_titular"],
            saldo_atual=data["saldo_atual"],
        )

    # ------------------------------------------------------------------
    # Depositar
    # ------------------------------------------------------------------
    def Depositar(self, request, context):
        self._apply_delay()

        conta_id = request.conta_id.strip()
        valor    = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Deposit amount must be positive. Received: {valor}",
            )

        try:
            novo_saldo = self._store.deposit(conta_id, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        print(f"[Depositar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Deposit of R$ {valor:.2f} completed successfully.",
        )

    # ------------------------------------------------------------------
    # Sacar
    # ------------------------------------------------------------------
    def Sacar(self, request, context):
        self._apply_delay()

        conta_id = request.conta_id.strip()
        valor    = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Withdrawal amount must be positive. Received: {valor}",
            )

        try:
            novo_saldo = self._store.withdraw(conta_id, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except ArithmeticError as exc:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))

        print(f"[Sacar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Withdrawal of R$ {valor:.2f} completed successfully.",
        )

    # ------------------------------------------------------------------
    # Transferir
    # ------------------------------------------------------------------
    def Transferir(self, request, context):
        self._apply_delay()

        origem  = request.conta_origem.strip()
        destino = request.conta_destino.strip()
        valor   = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Transfer amount must be positive. Received: {valor}",
            )

        if origem == destino:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_origem and conta_destino cannot be the same.",
            )

        try:
            novo_saldo_origem = self._store.transfer(origem, destino, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except ArithmeticError as exc:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))

        print(f"[Transferir] {origem} -> {destino}, valor={valor:.2f}, novo_saldo_origem={novo_saldo_origem:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=origem,
            saldo_atual=novo_saldo_origem,
            mensagem=f"Transfer of R$ {valor:.2f} from '{origem}' to '{destino}' completed.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Server Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def serve(port: int = 50051, max_workers: int = 10, delay_seconds: float = 0.0):
    """
    Start the gRPC server.

    Args:
        port         : TCP port to listen on (default 50051).
        max_workers  : Thread pool size (concurrency experiment variable).
        delay_seconds: Artificial per-request delay (deadline experiment variable).
    """
    store = AccountStore(seed=True)
    servicer = CarteiraServicer(store=store, delay_seconds=delay_seconds)

    if delay_seconds > 0:
        print(f"[WARNING] Delay mode active: {delay_seconds}s per request on Depositar/Sacar/Transferir")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()

    print(f"[SERVER] Digital Wallet started on port {port} with {max_workers} worker(s).")
    print(f"[SERVER] Seeded accounts: {store.known_accounts()}")
    print("[SERVER] Press Ctrl+C to stop.")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down gracefully...")
        server.stop(grace=5)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Server — Digital Wallet")
    parser.add_argument("--port",    type=int,   default=50051, help="TCP port (default: 50051)")
    parser.add_argument("--workers", type=int,   default=10,    help="Thread pool size (default: 10)")
    parser.add_argument("--delay",   type=float, default=0.0,   help="Artificial delay per request in seconds (default: 0)")
    args = parser.parse_args()

    serve(port=args.port, max_workers=args.workers, delay_seconds=args.delay)
