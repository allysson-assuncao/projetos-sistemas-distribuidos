"""
test_carteira.py — Automated Tests: Digital Wallet gRPC Service
Atividade Prática 4 — Distributed Systems

Testing strategy (Fix 3 — deterministic isolation):
  1. OS-assigned ports (port=0): each test class gets an ephemeral port
     chosen by the OS, guaranteeing no collision even under parallel runners.
  2. Channel readiness barrier: grpc.channel_ready_future().result(timeout=5)
     replaces the fragile time.sleep(0.3) heuristic.
  3. Isolated AccountStore per class: each setUpClass creates a fresh store,
     so test classes never share or corrupt each other's account state.
  4. Graceful teardown: server.stop(grace=0) + channel.close() in tearDownClass.
"""

import sys
import os
import unittest

import grpc
from concurrent import futures

# Importing the carteira package triggers __init__.py → sys.path fix (Fix 1)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import carteira  # noqa: F401  — triggers __init__.py sys.path injection

import carteira_pb2
import carteira_pb2_grpc
from carteira.store import AccountStore
from carteira.server import CarteiraServicer


# ─────────────────────────────────────────────────────────────────────────────
# Base Fixture
# ─────────────────────────────────────────────────────────────────────────────

class GrpcTestCase(unittest.TestCase):
    """
    Base class that spins up an isolated gRPC server for each test class.

    Key decisions:
      - port=0  → OS assigns an ephemeral port; no hardcoded values
      - channel_ready_future → deterministic readiness (no sleep)
      - fresh AccountStore   → no shared state between test classes
    """

    server  = None
    stub    = None
    channel = None
    port    = None

    @classmethod
    def setUpClass(cls):
        # Independent store per test class — Fix 3
        store    = AccountStore(seed=True)
        servicer = CarteiraServicer(store=store, delay_seconds=0.0)

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(servicer, cls.server)

        # OS-assigned port — Fix 3
        cls.port = cls.server.add_insecure_port("[::]:0")
        cls.server.start()

        cls.channel = grpc.insecure_channel(f"localhost:{cls.port}")
        cls.stub    = carteira_pb2_grpc.CarteiraServiceStub(cls.channel)

        # Deterministic readiness check — Fix 3
        grpc.channel_ready_future(cls.channel).result(timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop(grace=0)


# ─────────────────────────────────────────────────────────────────────────────
# CriarConta Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCriarConta(GrpcTestCase):

    def test_criar_conta_success(self):
        """Should create account with initial balance and return TransacaoResponse."""
        resp = self.stub.CriarConta(
            carteira_pb2.CriarContaRequest(conta_id="T01", nome_titular="Test One", saldo_inicial=500.0),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "T01")
        self.assertAlmostEqual(resp.saldo_atual, 500.0)
        self.assertIn("T01", resp.mensagem)

    def test_criar_conta_duplicate_returns_already_exists(self):
        """Should return ALREADY_EXISTS when creating account with existing ID."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="001", nome_titular="Alice Dup", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.ALREADY_EXISTS)

    def test_criar_conta_negative_balance_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when initial balance is negative."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T99", nome_titular="Invalid", saldo_inicial=-100.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_criar_conta_empty_name_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when nome_titular is empty."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T98", nome_titular="", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# ConsultarSaldo Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultarSaldo(GrpcTestCase):

    def test_consultar_saldo_existing_account(self):
        """Should return SaldoResponse with correct data for an existing account."""
        resp = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "001")
        self.assertEqual(resp.nome_titular, "Alice Silva")
        self.assertAlmostEqual(resp.saldo_atual, 1000.0, places=2)

    def test_consultar_saldo_nonexistent_returns_not_found(self):
        """Should return NOT_FOUND for a non-existent account."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id="999"),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)

    def test_consultar_saldo_empty_id_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when conta_id is empty."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id=""),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Depositar Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDepositar(GrpcTestCase):

    def test_depositar_success(self):
        """Balance should increase by deposited amount."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="002"), timeout=5
        ).saldo_atual

        resp = self.stub.Depositar(
            carteira_pb2.TransacaoRequest(conta_id="002", valor=100.0, descricao="Test"),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes + 100.0, places=2)

    def test_depositar_negative_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for negative deposit."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_zero_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for zero deposit."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=0.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_nonexistent_account_returns_not_found(self):
        """Should return NOT_FOUND when depositing to non-existent account."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="999", valor=50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# Sacar Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSacar(GrpcTestCase):

    def test_sacar_success(self):
        """Balance should decrease by withdrawn amount."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"), timeout=5
        ).saldo_atual

        resp = self.stub.Sacar(
            carteira_pb2.TransacaoRequest(conta_id="001", valor=50.0),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes - 50.0, places=2)

    def test_sacar_insufficient_funds_returns_failed_precondition(self):
        """Should return FAILED_PRECONDITION when withdrawing more than available balance."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="003", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)

    def test_sacar_negative_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for negative withdrawal."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Transferir Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTransferir(GrpcTestCase):

    def test_transferir_success(self):
        """Should debit source and credit destination atomically."""
        saldo_001 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="001"), timeout=5).saldo_atual
        saldo_002 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="002"), timeout=5).saldo_atual

        self.stub.Transferir(
            carteira_pb2.TransferirRequest(conta_origem="001", conta_destino="002", valor=30.0),
            timeout=5,
        )

        novo_saldo_001 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="001"), timeout=5).saldo_atual
        novo_saldo_002 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="002"), timeout=5).saldo_atual

        self.assertAlmostEqual(novo_saldo_001, saldo_001 - 30.0, places=2)
        self.assertAlmostEqual(novo_saldo_002, saldo_002 + 30.0, places=2)

    def test_transferir_same_account_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when source equals destination."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="001", conta_destino="001", valor=10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_transferir_insufficient_funds_returns_failed_precondition(self):
        """Should return FAILED_PRECONDITION when source balance is insufficient."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="003", conta_destino="001", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)


# ─────────────────────────────────────────────────────────────────────────────
# Deadline Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadline(GrpcTestCase):
    """
    Tests client-side deadline enforcement.
    Uses a small artificial delay to ensure Windows coarse timers don't miss the deadline.
    """

    @classmethod
    def setUpClass(cls):
        store    = AccountStore(seed=True)
        # Introduce a 0.5s delay to ensure the deadline is triggered
        servicer = CarteiraServicer(store=store, delay_seconds=0.5)

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(servicer, cls.server)

        cls.port = cls.server.add_insecure_port("[::]:0")
        cls.server.start()

        cls.channel = grpc.insecure_channel(f"localhost:{cls.port}")
        cls.stub    = carteira_pb2_grpc.CarteiraServiceStub(cls.channel)

        grpc.channel_ready_future(cls.channel).result(timeout=5)

    def test_deadline_exceeded(self):
        """Should return DEADLINE_EXCEEDED when timeout < delay_seconds."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=10.0),
                timeout=0.1,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.DEADLINE_EXCEEDED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
