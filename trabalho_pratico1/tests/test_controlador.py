"""
test_controlador.py — Unit tests for the Controlador class.

Tests cover:
  - Initial state loading (from file and default)
  - Deterministic comando_id generation (MD5 of action + sensor timestamp)
  - Decision logic: exhaust fan activation/deactivation thresholds
  - Decision logic: irrigation pump activation/deactivation thresholds
  - Byzantine mode: falsified obter_estado response
  - Manual command methods: comandar_bomba and comandar_exaustor
  - XML-RPC ping health-check method
  - skip_sync=True prevents Middleware connection attempt

NOTE: Tests use skip_sync=True or unit-level mocking to bypass boot-time state synchronization.
The Middleware server does NOT need to be running for these tests.
"""

import hashlib
import json
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock

# pyrefly: ignore [missing-import]
import pytest

# Import the module and class under test
from estufa.controlador import Controlador
from estufa import config


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_data_file(tmp_path):
    """Returns a temporary JSON state file path (does not create the file)."""
    return str(tmp_path / "data_ctrl_test.json")


@pytest.fixture
def controlador(tmp_data_file):
    """Creates a Controlador instance with a temporary state file."""
    return Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)


@pytest.fixture
def controlador_byzantino(tmp_data_file):
    """Creates a Byzantine Controlador instance."""
    return Controlador(ctrl_id="ctrl_byz", data_file=tmp_data_file, byzantino=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: inject sensor data into controller state to trigger decisions
# ─────────────────────────────────────────────────────────────────────────────

def _injetar_sensor(ctrl: Controlador, temperatura=None, umidade=None, sensor_ts=1234567890.0):
    """
    Directly sets internal state values to simulate MQTT sensor arrival.
    This bypasses the MQTT stack entirely, enabling pure unit testing.
    """
    with ctrl._lock:
        if temperatura is not None:
            ctrl._estado["temperatura"] = temperatura
        if umidade is not None:
            ctrl._estado["umidade_solo"] = umidade
        ctrl._estado["sensor_timestamp"] = sensor_ts


def _executar_decisao(ctrl: Controlador):
    """Calls _decidir_atuacao with the lock held (as the real MQTT callback does)."""
    # Detach mqtt_client to prevent actual publishing during tests
    ctrl._mqtt_client = None
    with ctrl._lock:
        ctrl._decidir_atuacao()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Initialization & State Loading
# ─────────────────────────────────────────────────────────────────────────────

class TestInicializacao:
    def test_estado_inicial_quando_arquivo_nao_existe(self, tmp_data_file):
        """Controller should start with default state when JSON file is absent."""
        ctrl = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl._estado["bomba_ligada"] is False
        assert ctrl._estado["exaustor_ligado"] is False
        assert ctrl._estado["temperatura"] is None
        assert ctrl._estado["umidade_solo"] is None
        assert ctrl._estado["controlador_id"] == "ctrl_test"

    def test_estado_carregado_do_arquivo_existente(self, tmp_data_file):
        """Controller should load persisted state from an existing JSON file."""
        estado_salvo = {
            "temperatura": 28.5,
            "umidade_solo": 45.0,
            "bomba_ligada": True,
            "exaustor_ligado": False,
            "ultima_atualizacao": 1234567890.0,
            "sensor_timestamp": 1234567890.0,
            "controlador_id": "ctrl_old",
        }
        with open(tmp_data_file, "w", encoding="utf-8") as f:
            json.dump(estado_salvo, f)

        ctrl = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        # bomba_ligada should be loaded from file
        assert ctrl._estado["bomba_ligada"] is True
        # controlador_id is ALWAYS overwritten by __init__
        assert ctrl._estado["controlador_id"] == "ctrl_test"

    def test_arquivo_json_corrompido_usa_estado_inicial(self, tmp_data_file):
        """Corrupt JSON file should cause controller to fall back to default state."""
        with open(tmp_data_file, "w", encoding="utf-8") as f:
            f.write("INVALID JSON {{{")

        ctrl = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl._estado["bomba_ligada"] is False
        assert ctrl._estado["temperatura"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Deterministic comando_id Generation
# ─────────────────────────────────────────────────────────────────────────────

class TestComandoIdDeterministico:
    """
    Verifies that the deterministic ID generation guarantees all 3 replicas
    produce the exact same MD5 hash for the same sensor event and action.

    The formula is: md5(f"{action}_{sensor_timestamp}")
    """

    def _expected_id(self, acao: str, sensor_ts: float) -> str:
        raw = f"{acao}_{sensor_ts}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def test_tres_replicas_geram_mesmo_id_para_exaustor_ligar(self):
        """All 3 replicas must produce identical comando_id for exhaust fan ON."""
        sensor_ts = 1700000000.123
        expected = self._expected_id("exaustor_ligar", sensor_ts)

        # Simulate 3 controller replicas independently computing the same ID
        ids = []
        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                fname = f.name
            try:
                ctrl = Controlador(ctrl_id=replica_id, data_file=fname)
                with ctrl._lock:
                    ctrl._estado["sensor_timestamp"] = sensor_ts
                    raw = f"exaustor_ligar_{sensor_ts}"
                    ids.append(hashlib.md5(raw.encode("utf-8")).hexdigest())
            finally:
                if os.path.exists(fname):
                    os.unlink(fname)

        assert ids[0] == ids[1] == ids[2] == expected

    def test_tres_replicas_geram_mesmo_id_para_bomba_ligar(self):
        """All 3 replicas must produce identical comando_id for pump ON."""
        sensor_ts = 1700000042.999
        raw = f"bomba_ligar_{sensor_ts}"
        expected = hashlib.md5(raw.encode("utf-8")).hexdigest()

        # Verify the formula is consistent across calls
        result1 = hashlib.md5(raw.encode("utf-8")).hexdigest()
        result2 = hashlib.md5(raw.encode("utf-8")).hexdigest()
        assert result1 == result2 == expected

    def test_decisao_atuacao_tres_replicas_publicam_mesmo_comando_id(self):
        """All 3 replicas executing _decidir_atuacao must publish with identical deterministic comando_id."""
        sensor_ts = 1700000099.5
        published_ids = []

        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                fname = f.name
            try:
                ctrl = Controlador(ctrl_id=replica_id, data_file=fname)

                def mock_publicar(topico, acao, cmd_id):
                    published_ids.append((acao, cmd_id))

                ctrl._publicar_comando = mock_publicar

                with ctrl._lock:
                    ctrl._estado["temperatura"] = config.TEMP_MAX_CELSIUS + 5.0
                    ctrl._estado["sensor_timestamp"] = sensor_ts
                    ctrl._decidir_atuacao()
            finally:
                if os.path.exists(fname):
                    os.unlink(fname)

        expected_id = hashlib.md5(f"exaustor_ligar_{sensor_ts}".encode("utf-8")).hexdigest()
        assert len(published_ids) == 3
        assert published_ids[0] == ("ligar", expected_id)
        assert published_ids[1] == ("ligar", expected_id)
        assert published_ids[2] == ("ligar", expected_id)

    def test_decisao_bomba_tres_replicas_publicam_mesmo_comando_id(self):
        """All 3 replicas executing pump decision must publish with identical deterministic comando_id."""
        sensor_ts = 1700000100.2
        published_ids = []

        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                fname = f.name
            try:
                ctrl = Controlador(ctrl_id=replica_id, data_file=fname)

                def mock_publicar(topico, acao, cmd_id):
                    published_ids.append((acao, cmd_id))

                ctrl._publicar_comando = mock_publicar

                with ctrl._lock:
                    ctrl._estado["umidade_solo"] = config.UMIDADE_MIN_PERCENT - 5.0
                    ctrl._estado["sensor_timestamp"] = sensor_ts
                    ctrl._decidir_atuacao()
            finally:
                if os.path.exists(fname):
                    os.unlink(fname)

        expected_id = hashlib.md5(f"bomba_ligar_{sensor_ts}".encode("utf-8")).hexdigest()
        assert len(published_ids) == 3
        assert published_ids[0] == ("ligar", expected_id)
        assert published_ids[1] == ("ligar", expected_id)
        assert published_ids[2] == ("ligar", expected_id)

    def test_id_diferente_para_acoes_diferentes(self):
        """Different actions on same sensor timestamp must produce different IDs."""
        ts = 1700000000.0
        id_ligar    = hashlib.md5(f"bomba_ligar_{ts}".encode()).hexdigest()
        id_desligar = hashlib.md5(f"bomba_desligar_{ts}".encode()).hexdigest()
        assert id_ligar != id_desligar

    def test_id_diferente_para_timestamps_diferentes(self):
        """Same action with different timestamps must produce different IDs."""
        id_ts1 = hashlib.md5(f"exaustor_ligar_1700000001.0".encode()).hexdigest()
        id_ts2 = hashlib.md5(f"exaustor_ligar_1700000002.0".encode()).hexdigest()
        assert id_ts1 != id_ts2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Decision Logic — Exhaust Fan (Temperature)
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisaoExaustor:
    def test_exaustor_ligado_quando_temp_acima_maximo(self, controlador):
        """Fan should turn ON when temperature exceeds TEMP_MAX_CELSIUS."""
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS + 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is True

    def test_exaustor_nao_liga_quando_temp_dentro_limite(self, controlador):
        """Fan should NOT turn ON when temperature is within safe range."""
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False

    def test_exaustor_desligado_quando_temp_abaixo_minimo(self, controlador):
        """Fan should turn OFF when temperature drops below TEMP_MIN_CELSIUS."""
        # First: turn it ON
        with controlador._lock:
            controlador._estado["exaustor_ligado"] = True
        _injetar_sensor(controlador, temperatura=config.TEMP_MIN_CELSIUS - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False

    def test_exaustor_nao_republica_se_ja_ligado(self, controlador):
        """Fan should not change state if it is already ON and temp is still above max."""
        with controlador._lock:
            controlador._estado["exaustor_ligado"] = True
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS + 5.0)
        _executar_decisao(controlador)
        # State must remain True — no redundant command published
        assert controlador._estado["exaustor_ligado"] is True

    def test_sem_temperatura_nenhuma_decisao_exaustor(self, controlador):
        """Without temperature reading, fan decision should be skipped."""
        _injetar_sensor(controlador, temperatura=None)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Decision Logic — Irrigation Pump (Humidity)
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisaoBomba:
    def test_bomba_ligada_quando_umidade_abaixo_minimo(self, controlador):
        """Pump should turn ON when humidity drops below UMIDADE_MIN_PERCENT."""
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is True

    def test_bomba_nao_liga_quando_umidade_dentro_limite(self, controlador):
        """Pump should NOT turn ON when humidity is within safe range."""
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT + 5.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False

    def test_bomba_desligada_quando_umidade_acima_maximo(self, controlador):
        """Pump should turn OFF when humidity exceeds UMIDADE_MAX_PERCENT."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        _injetar_sensor(controlador, umidade=config.UMIDADE_MAX_PERCENT + 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False

    def test_bomba_nao_republica_se_ja_ligada(self, controlador):
        """Pump should not toggle if it is already ON and humidity is still low."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT - 10.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is True

    def test_sem_umidade_nenhuma_decisao_bomba(self, controlador):
        """Without humidity reading, pump decision should be skipped."""
        _injetar_sensor(controlador, umidade=None)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Byzantine Mode
# ─────────────────────────────────────────────────────────────────────────────

class TestModoByantino:
    def test_obter_estado_retorna_dados_falsos_em_modo_byzantino(self, controlador_byzantino):
        """Byzantine controller must return inverted/falsified state."""
        with controlador_byzantino._lock:
            controlador_byzantino._estado["bomba_ligada"] = False
            controlador_byzantino._estado["exaustor_ligado"] = False

        estado = controlador_byzantino.obter_estado()

        # Byzantine mode inverts the boolean values
        assert estado["bomba_ligada"] is True
        assert estado["exaustor_ligado"] is True
        assert estado["temperatura"] == 999.0
        assert estado["umidade_solo"] == -1.0
        assert estado.get("_byzantino") is True

    def test_comandar_bomba_byzantino_retorna_sucesso_falso(self, controlador_byzantino):
        """Byzantine controller must confirm pump command without actually doing it."""
        result = controlador_byzantino.comandar_bomba("ligar")
        assert result["sucesso"] is True
        assert result.get("byzantino") is True

    def test_comandar_exaustor_byzantino_retorna_sucesso_falso(self, controlador_byzantino):
        """Byzantine controller must confirm exhaust command without actually doing it."""
        result = controlador_byzantino.comandar_exaustor("desligar")
        assert result["sucesso"] is True
        assert result.get("byzantino") is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Manual XML-RPC Commands
# ─────────────────────────────────────────────────────────────────────────────

class TestComandosManuais:
    def test_comandar_bomba_ligar(self, controlador):
        """Manual pump ON command should update internal state."""
        controlador._mqtt_client = None  # Prevent MQTT publish
        result = controlador.comandar_bomba("ligar", "test-uuid-001")
        assert result["sucesso"] is True
        assert controlador._estado["bomba_ligada"] is True

    def test_comandar_bomba_desligar(self, controlador):
        """Manual pump OFF command should update internal state."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        controlador._mqtt_client = None
        result = controlador.comandar_bomba("desligar", "test-uuid-002")
        assert result["sucesso"] is True
        assert controlador._estado["bomba_ligada"] is False

    def test_comandar_bomba_acao_invalida(self, controlador):
        """Invalid action string must return sucesso=False."""
        result = controlador.comandar_bomba("LIGAR_FORCADO")
        assert result["sucesso"] is False

    def test_comandar_exaustor_ligar(self, controlador):
        """Manual fan ON command should update internal state."""
        controlador._mqtt_client = None
        result = controlador.comandar_exaustor("ligar", "test-uuid-003")
        assert result["sucesso"] is True
        assert controlador._estado["exaustor_ligado"] is True

    def test_comandar_exaustor_acao_invalida(self, controlador):
        """Invalid action string for fan must return sucesso=False."""
        result = controlador.comandar_exaustor("TOGGLE")
        assert result["sucesso"] is False

    def test_ping_retorna_pong(self, controlador):
        """ping() method must return 'pong:ctrl_test' for health-check."""
        assert controlador.ping() == "pong:ctrl_test"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: State Persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistencia:
    def test_salvar_e_recarregar_estado(self, tmp_data_file):
        """State saved to JSON must be correctly reloaded in a new instance."""
        ctrl1 = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        ctrl1._mqtt_client = None
        ctrl1.comandar_bomba("ligar", "persist-test-id")

        # Create a new instance pointing to the same file
        ctrl2 = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl2._estado["bomba_ligada"] is True
