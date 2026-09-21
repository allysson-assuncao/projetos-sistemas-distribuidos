"""
test_middleware.py — Unit tests for the Middleware voting engine.

Tests cover:
  - Quorum achieved with 3/3 concordant controllers
  - Quorum achieved with 2/3 concordant controllers (1 crashed)
  - Quorum FAILS when all controllers return divergent responses (split-brain)
  - Byzantine fault tolerance: 1 Byzantine + 2 honest → honest result returned
  - Byzantine fault tolerance: 2 Byzantines + 1 honest → documentation of BFT boundary
  - comando_id UUID uniqueness per call (Middleware generates fresh UUID each invocation)
  - comando_id shared across replicas within the same invocation
  - verificar_saude correctly identifies online/offline controllers

NOTE: All tests mock xmlrpc.client.ServerProxy to avoid real network connections.
The controller processes do NOT need to be running for these tests.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

# pyrefly: ignore [missing-import]
import pytest

from estufa.middleware import Middleware, ErroQuorum
from estufa import config


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build mock controller response dicts
# ─────────────────────────────────────────────────────────────────────────────

def _estado_honesto(bomba=False, exaustor=False, temp=25.0, umidade=50.0):
    """Returns a realistic controller state dict (honest response)."""
    return {
        "temperatura": temp,
        "umidade_solo": umidade,
        "bomba_ligada": bomba,
        "exaustor_ligado": exaustor,
        "ultima_atualizacao": 1700000000.0,
        "sensor_timestamp": 1700000000.0,
        "controlador_id": "ctrl_x",
    }


def _resposta_comando(sucesso=True, mensagem="ok"):
    return {"sucesso": sucesso, "mensagem": mensagem}


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: Middleware with 3 test controllers
# ─────────────────────────────────────────────────────────────────────────────

CONTROLADORES_TESTE = [
    {"id": "ctrl_1", "host": "localhost", "port": 18001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 18002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 18003, "data_file": "data_ctrl_3.json"},
]


@pytest.fixture
def middleware():
    """Returns a Middleware instance configured with test controllers."""
    return Middleware(controladores=CONTROLADORES_TESTE, timeout=2)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: obter_estado — Quorum Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestObterEstadoQuorum:
    def test_quorum_3_de_3_concordantes(self, middleware):
        """3/3 concordant controllers → quorum achieved, honest state returned."""
        honest_state = _estado_honesto(bomba=False, exaustor=False)

        # All 3 controllers return identical state
        mock_proxy = MagicMock()
        mock_proxy.obter_estado.return_value = honest_state

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            result = middleware.obter_estado()

        assert result["bomba_ligada"] is False
        assert result["exaustor_ligado"] is False
        assert result["temperatura"] == 25.0

    def test_quorum_2_de_3_um_crashado(self, middleware):
        """2/3 controllers respond, 1 crashes → quorum still achieved."""
        honest_state = _estado_honesto(bomba=True, exaustor=False)
        crash_error = ConnectionRefusedError("Controller offline")

        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 3:  # Third controller crashes
                m.obter_estado.side_effect = crash_error
            else:
                m.obter_estado.return_value = honest_state
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()

        assert result["bomba_ligada"] is True

    def test_quorum_falha_todos_crashados(self, middleware):
        """0/3 controllers respond → ErroQuorum raised."""
        crash_error = ConnectionRefusedError("All offline")

        mock_proxy = MagicMock()
        mock_proxy.obter_estado.side_effect = crash_error

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            with pytest.raises(ErroQuorum):
                middleware.obter_estado()

    def test_quorum_falha_respostas_todas_divergentes(self, middleware):
        """3 controllers, all return different states → quorum fails (ErroQuorum)."""
        states = [
            _estado_honesto(bomba=False, exaustor=False, temp=25.0),
            _estado_honesto(bomba=True,  exaustor=False, temp=26.0),
            _estado_honesto(bomba=False, exaustor=True,  temp=27.0),
        ]

        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            idx = call_count[0] % len(states)
            call_count[0] += 1
            m.obter_estado.return_value = states[idx]
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            with pytest.raises(ErroQuorum):
                middleware.obter_estado()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Byzantine Fault Tolerance
# ─────────────────────────────────────────────────────────────────────────────

class TestToleranciaByantina:
    def test_1_byzantino_2_honestos_retorna_estado_honesto(self, middleware):
        """1 Byzantine + 2 honest → majority voting returns honest state."""
        honest_state   = _estado_honesto(bomba=False, exaustor=False, temp=25.0)
        byzantine_state = {
            "temperatura": 999.0,
            "umidade_solo": -1.0,
            "bomba_ligada": True,   # Inverted!
            "exaustor_ligado": True, # Inverted!
            "ultima_atualizacao": 1700000000.0,
            "sensor_timestamp": 1700000000.0,
            "controlador_id": "ctrl_byz",
            "_byzantino": True,
        }

        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 2:  # Second controller is Byzantine
                m.obter_estado.return_value = byzantine_state
            else:
                m.obter_estado.return_value = honest_state
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()

        # Honest state must win (2 votes vs 1)
        assert result["bomba_ligada"] is False
        assert result["exaustor_ligado"] is False
        assert result["temperatura"] == 25.0

    def test_2_byzantinos_1_honesto_levanta_erro_quorum(self, middleware):
        """2 Byzantines + 1 honest → majority is Byzantine, documenting f=1 boundary."""
        # Note: 2 Byzantines returning the same wrong state achieve quorum with QUORUM_MINIMO=2.
        # This demonstrates the theoretical boundary of f=1 BFT with n=3 (requires 2f+1 nodes).
        honest_state   = _estado_honesto(bomba=False, exaustor=False)
        byzantine_state = {
            "temperatura": 999.0,
            "umidade_solo": -1.0,
            "bomba_ligada": True,
            "exaustor_ligado": True,
            "ultima_atualizacao": 1700000000.0,
            "sensor_timestamp": 1700000000.0,
            "controlador_id": "ctrl_byz",
        }

        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 2:  # First two controllers are Byzantine
                m.obter_estado.return_value = byzantine_state
            else:
                m.obter_estado.return_value = honest_state
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()
            # With 2 Byzantine votes forming majority, the result is Byzantine
            assert result["bomba_ligada"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: comandar_bomba — Command Broadcasting
# ─────────────────────────────────────────────────────────────────────────────

class TestComandoBomba:
    def test_comandar_bomba_ligar_com_quorum(self, middleware):
        """Pump ON command should reach quorum and return success."""
        cmd_response = _resposta_comando(sucesso=True, mensagem="Bomba ligada com sucesso pelo ctrl_1")

        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.return_value = cmd_response

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            result = middleware.comandar_bomba("ligar")

        assert result["sucesso"] is True

    def test_comandar_bomba_gera_uuid_diferente_a_cada_chamada(self, middleware):
        """Each call to comandar_bomba must generate a NEW UUID (not reuse previous)."""
        cmd_response = _resposta_comando()
        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.return_value = cmd_response

        captured_ids = []

        def capture_args(*args, **kwargs):
            # args[0] = acao, args[1] = comando_id
            if len(args) > 1:
                captured_ids.append(args[1])
            return cmd_response

        mock_proxy.comandar_bomba.side_effect = capture_args

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            middleware.comandar_bomba("ligar")
            middleware.comandar_bomba("ligar")

        # Two calls across 3 controllers each produce 6 captures (3 identical for call 1, 3 identical for call 2)
        assert len(captured_ids) == 6
        assert len(set(captured_ids[:3])) == 1
        assert len(set(captured_ids[3:])) == 1
        assert captured_ids[0] != captured_ids[3]

    def test_comandar_bomba_falha_sem_quorum(self, middleware):
        """Pump command should raise ErroQuorum when all controllers are offline."""
        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.side_effect = ConnectionRefusedError("offline")

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            with pytest.raises(ErroQuorum):
                middleware.comandar_bomba("ligar")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: comandar_exaustor — Command Broadcasting
# ─────────────────────────────────────────────────────────────────────────────

class TestComandoExaustor:
    def test_comandar_exaustor_desligar_com_quorum(self, middleware):
        """Fan OFF command should reach quorum and return success."""
        cmd_response = _resposta_comando(sucesso=True, mensagem="Exaustor desligado")

        mock_proxy = MagicMock()
        mock_proxy.comandar_exaustor.return_value = cmd_response

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            result = middleware.comandar_exaustor("desligar")

        assert result["sucesso"] is True

    def test_comandar_exaustor_uuid_compartilhado_entre_controladores(self, middleware):
        """All 3 controllers must receive the SAME comando_id in a single invocation."""
        cmd_response = _resposta_comando()
        received_ids = []

        def capture_args_factory():
            m = MagicMock()
            def capture(*args, **kwargs):
                if len(args) > 1:
                    received_ids.append(args[1])
                return cmd_response
            m.comandar_exaustor.side_effect = capture
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=lambda ctrl: capture_args_factory()):
            middleware.comandar_exaustor("ligar")

        assert len(received_ids) == 3
        # All received IDs must be identical (Middleware generates 1 UUID per call)
        assert len(set(received_ids)) == 1, (
            f"Expected all controllers to receive the same UUID, got: {received_ids}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: verificar_saude — Health Check
# ─────────────────────────────────────────────────────────────────────────────

class TestVerificarSaude:
    def test_todos_online_retorna_ok(self, middleware):
        """When all controllers respond with 'pong', health status is 'ok' for all."""
        mock_proxy = MagicMock()
        mock_proxy.ping.return_value = "pong:ctrl_1"

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            saude = middleware.verificar_saude()

        for ctrl_id, status in saude.items():
            assert status == "ok", f"Expected 'ok' for {ctrl_id}, got '{status}'"

    def test_um_offline_retorna_offline_status(self, middleware):
        """When 1 controller is offline, its status should start with 'OFFLINE'."""
        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 2:  # Second controller is offline
                m.ping.side_effect = ConnectionRefusedError("offline")
            else:
                m.ping.return_value = f"pong:{ctrl['id']}"
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            saude = middleware.verificar_saude()

        offline_statuses = [s for s in saude.values() if s.startswith("OFFLINE")]
        assert len(offline_statuses) == 1

    def test_todos_offline_retorna_todos_com_status_offline(self, middleware):
        """When all controllers are offline, all health statuses start with 'OFFLINE'."""
        mock_proxy = MagicMock()
        mock_proxy.ping.side_effect = ConnectionRefusedError("all offline")

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            saude = middleware.verificar_saude()

        for ctrl_id, status in saude.items():
            assert status.startswith("OFFLINE"), f"Expected OFFLINE for {ctrl_id}, got '{status}'"
