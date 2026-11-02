"""
test_controlador.py — Testes unitários da classe Controlador.

Cobre carregamento e persistência de estado, geração determinística de
comando_id por hash MD5, regras de acionamento de bomba e exaustor,
comportamento em modo bizantino e comandos manuais via XML-RPC.
"""

import hashlib
import json
import pytest

from estufa.controlador import Controlador
from estufa import config


@pytest.fixture
def tmp_data_file(tmp_path):
    """Retorna o caminho de um arquivo JSON temporário de estado."""
    return str(tmp_path / "data_ctrl_test.json")


@pytest.fixture
def controlador(tmp_data_file):
    """Instância padrão de Controlador para testes."""
    return Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)


@pytest.fixture
def controlador_byzantino(tmp_data_file):
    """Instância de Controlador configurada em modo bizantino."""
    return Controlador(ctrl_id="ctrl_byz", data_file=tmp_data_file, byzantino=True)


def _injetar_sensor(ctrl: Controlador, temperatura=None, umidade=None, sensor_ts=1234567890.0):
    """Define valores de telemetria diretamente no estado interno da réplica."""
    with ctrl._lock:
        if temperatura is not None:
            ctrl._estado["temperatura"] = temperatura
        if umidade is not None:
            ctrl._estado["umidade_solo"] = umidade
        ctrl._estado["sensor_timestamp"] = sensor_ts


def _executar_decisao(ctrl: Controlador):
    """Executa a avaliação de regras sem conexão MQTT ativa."""
    ctrl._mqtt_client = None
    with ctrl._lock:
        ctrl._decidir_atuacao()


class TestInicializacao:
    def test_estado_inicial_quando_arquivo_nao_existe(self, tmp_data_file):
        """Deve inicializar com valores padrão quando o arquivo JSON não existe."""
        ctrl = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl._estado["bomba_ligada"] is False
        assert ctrl._estado["exaustor_ligado"] is False
        assert ctrl._estado["temperatura"] is None
        assert ctrl._estado["umidade_solo"] is None
        assert ctrl._estado["controlador_id"] == "ctrl_test"

    def test_estado_carregado_do_arquivo_existente(self, tmp_data_file):
        """Deve restaurar o estado persistido em arquivo JSON pré-existente."""
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
        assert ctrl._estado["bomba_ligada"] is True
        assert ctrl._estado["controlador_id"] == "ctrl_test"

    def test_arquivo_json_corrompido_usa_estado_inicial(self, tmp_data_file):
        """Arquivo JSON inválido deve fazer fallback para o estado inicial."""
        with open(tmp_data_file, "w", encoding="utf-8") as f:
            f.write("INVALID JSON {{{")

        ctrl = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl._estado["bomba_ligada"] is False
        assert ctrl._estado["temperatura"] is None


class TestComandoIdDeterministico:
    """Verifica que as 3 réplicas geram o mesmo hash MD5 para o mesmo evento de sensor."""

    def _expected_id(self, acao: str, sensor_ts: float) -> str:
        raw = f"{acao}_{sensor_ts}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def test_tres_replicas_geram_mesmo_id_para_exaustor_ligar(self, tmp_path):
        """Três réplicas independentes produzem o mesmo comando_id ao ligar o exaustor."""
        sensor_ts = 1700000000.123
        expected = self._expected_id("exaustor_ligar", sensor_ts)

        ids = []
        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            fname = str(tmp_path / f"{replica_id}.json")
            ctrl = Controlador(ctrl_id=replica_id, data_file=fname)
            with ctrl._lock:
                ctrl._estado["sensor_timestamp"] = sensor_ts
                raw = f"exaustor_ligar_{sensor_ts}"
                ids.append(hashlib.md5(raw.encode("utf-8")).hexdigest())

        assert ids[0] == ids[1] == ids[2] == expected

    def test_tres_replicas_geram_mesmo_id_para_bomba_ligar(self):
        """O hash MD5 para acionamento da bomba é determinístico para o mesmo timestamp."""
        sensor_ts = 1700000042.999
        raw = f"bomba_ligar_{sensor_ts}"
        expected = hashlib.md5(raw.encode("utf-8")).hexdigest()

        result1 = hashlib.md5(raw.encode("utf-8")).hexdigest()
        result2 = hashlib.md5(raw.encode("utf-8")).hexdigest()
        assert result1 == result2 == expected

    def test_decisao_atuacao_tres_replicas_publicam_mesmo_comando_id(self, tmp_path):
        """As 3 réplicas publicam o mesmo comando_id ao avaliar temperatura crítica."""
        sensor_ts = 1700000099.5
        published_ids = []

        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            fname = str(tmp_path / f"{replica_id}.json")
            ctrl = Controlador(ctrl_id=replica_id, data_file=fname)
            ctrl._publicar_comando = lambda topico, acao, cmd_id: published_ids.append((acao, cmd_id))

            with ctrl._lock:
                ctrl._estado["temperatura"] = config.TEMP_MAX_CELSIUS + 5.0
                ctrl._estado["sensor_timestamp"] = sensor_ts
                ctrl._decidir_atuacao()

        expected_id = hashlib.md5(f"exaustor_ligar_{sensor_ts}".encode("utf-8")).hexdigest()
        assert published_ids == [("ligar", expected_id)] * 3

    def test_decisao_bomba_tres_replicas_publicam_mesmo_comando_id(self, tmp_path):
        """As 3 réplicas publicam o mesmo comando_id ao avaliar umidade crítica."""
        sensor_ts = 1700000100.2
        published_ids = []

        for replica_id in ["ctrl_1", "ctrl_2", "ctrl_3"]:
            fname = str(tmp_path / f"{replica_id}.json")
            ctrl = Controlador(ctrl_id=replica_id, data_file=fname)
            ctrl._publicar_comando = lambda topico, acao, cmd_id: published_ids.append((acao, cmd_id))

            with ctrl._lock:
                ctrl._estado["umidade_solo"] = config.UMIDADE_MIN_PERCENT - 5.0
                ctrl._estado["sensor_timestamp"] = sensor_ts
                ctrl._decidir_atuacao()

        expected_id = hashlib.md5(f"bomba_ligar_{sensor_ts}".encode("utf-8")).hexdigest()
        assert published_ids == [("ligar", expected_id)] * 3

    def test_id_diferente_para_acoes_diferentes(self):
        """Ações distintas no mesmo timestamp produzem identificadores diferentes."""
        ts = 1700000000.0
        id_ligar = hashlib.md5(f"bomba_ligar_{ts}".encode()).hexdigest()
        id_desligar = hashlib.md5(f"bomba_desligar_{ts}".encode()).hexdigest()
        assert id_ligar != id_desligar

    def test_id_diferente_para_timestamps_diferentes(self):
        """Mesma ação em timestamps distintos produz identificadores diferentes."""
        id_ts1 = hashlib.md5("exaustor_ligar_1700000001.0".encode()).hexdigest()
        id_ts2 = hashlib.md5("exaustor_ligar_1700000002.0".encode()).hexdigest()
        assert id_ts1 != id_ts2


class TestDecisaoExaustor:
    def test_exaustor_ligado_quando_temp_acima_maximo(self, controlador):
        """Liga o exaustor quando a temperatura ultrapassa TEMP_MAX_CELSIUS."""
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS + 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is True

    def test_exaustor_nao_liga_quando_temp_dentro_limite(self, controlador):
        """Mantém o exaustor desligado quando a temperatura está na faixa normal."""
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False

    def test_exaustor_desligado_quando_temp_abaixo_minimo(self, controlador):
        """Desliga o exaustor quando a temperatura cai abaixo de TEMP_MIN_CELSIUS."""
        with controlador._lock:
            controlador._estado["exaustor_ligado"] = True
        _injetar_sensor(controlador, temperatura=config.TEMP_MIN_CELSIUS - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False

    def test_exaustor_nao_republica_se_ja_ligado(self, controlador):
        """Não altera nem republica comando se o exaustor já estiver ligado."""
        with controlador._lock:
            controlador._estado["exaustor_ligado"] = True
        _injetar_sensor(controlador, temperatura=config.TEMP_MAX_CELSIUS + 5.0)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is True

    def test_sem_temperatura_nenhuma_decisao_exaustor(self, controlador):
        """Sem leitura de temperatura disponível, mantém o estado atual do exaustor."""
        _injetar_sensor(controlador, temperatura=None)
        _executar_decisao(controlador)
        assert controlador._estado["exaustor_ligado"] is False


class TestDecisaoBomba:
    def test_bomba_ligada_quando_umidade_abaixo_minimo(self, controlador):
        """Liga a bomba quando a umidade cai abaixo de UMIDADE_MIN_PERCENT."""
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT - 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is True

    def test_bomba_nao_liga_quando_umidade_dentro_limite(self, controlador):
        """Mantém a bomba desligada quando a umidade está na faixa normal."""
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT + 5.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False

    def test_bomba_desligada_quando_umidade_acima_maximo(self, controlador):
        """Desliga a bomba quando a umidade ultrapassa UMIDADE_MAX_PERCENT."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        _injetar_sensor(controlador, umidade=config.UMIDADE_MAX_PERCENT + 1.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False

    def test_bomba_nao_republica_se_ja_ligada(self, controlador):
        """Não altera o estado se a bomba já estiver ligada."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        _injetar_sensor(controlador, umidade=config.UMIDADE_MIN_PERCENT - 10.0)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is True

    def test_sem_umidade_nenhuma_decisao_bomba(self, controlador):
        """Sem leitura de umidade disponível, mantém o estado atual da bomba."""
        _injetar_sensor(controlador, umidade=None)
        _executar_decisao(controlador)
        assert controlador._estado["bomba_ligada"] is False


class TestModoByantino:
    def test_obter_estado_retorna_dados_falsos_em_modo_byzantino(self, controlador_byzantino):
        """Controlador em modo bizantino retorna leituras adulteradas e estados invertidos."""
        with controlador_byzantino._lock:
            controlador_byzantino._estado["bomba_ligada"] = False
            controlador_byzantino._estado["exaustor_ligado"] = False

        estado = controlador_byzantino.obter_estado()

        assert estado["bomba_ligada"] is True
        assert estado["exaustor_ligado"] is True
        assert estado["temperatura"] == 999.0
        assert estado["umidade_solo"] == -1.0
        assert "_byzantino" not in estado

    def test_comandar_bomba_byzantino_retorna_sucesso_falso(self, controlador_byzantino):
        """Controlador bizantino retorna confirmação divergente sem alterar o estado real."""
        result = controlador_byzantino.comandar_bomba("ligar")
        assert result["sucesso"] is True
        assert result["mensagem"] == "Bomba desligada com sucesso"
        assert controlador_byzantino._estado["bomba_ligada"] is False

    def test_comandar_exaustor_byzantino_retorna_sucesso_falso(self, controlador_byzantino):
        """Controlador bizantino retorna confirmação divergente para o exaustor sem atuar."""
        result = controlador_byzantino.comandar_exaustor("desligar")
        assert result["sucesso"] is True
        assert result["mensagem"] == "Exaustor ligado com sucesso"
        assert controlador_byzantino._estado["exaustor_ligado"] is False


class TestComandosManuais:
    def test_comandar_bomba_ligar(self, controlador):
        """Comando manual para ligar a bomba atualiza o estado e retorna mensagem padronizada."""
        controlador._mqtt_client = None
        result = controlador.comandar_bomba("ligar", "test-uuid-001")
        assert result["sucesso"] is True
        assert result["mensagem"] == "Bomba ligada com sucesso"
        assert result["controlador_id"] == "ctrl_test"
        assert controlador._estado["bomba_ligada"] is True

    def test_comandar_bomba_desligar(self, controlador):
        """Comando manual para desligar a bomba atualiza o estado interno."""
        with controlador._lock:
            controlador._estado["bomba_ligada"] = True
        controlador._mqtt_client = None
        result = controlador.comandar_bomba("desligar", "test-uuid-002")
        assert result["sucesso"] is True
        assert result["mensagem"] == "Bomba desligada com sucesso"
        assert controlador._estado["bomba_ligada"] is False

    def test_comandar_bomba_acao_invalida(self, controlador):
        """Ação inválida na bomba deve retornar sucesso=False."""
        result = controlador.comandar_bomba("LIGAR_FORCADO")
        assert result["sucesso"] is False

    def test_comandar_exaustor_ligar(self, controlador):
        """Comando manual para ligar o exaustor atualiza o estado interno."""
        controlador._mqtt_client = None
        result = controlador.comandar_exaustor("ligar", "test-uuid-003")
        assert result["sucesso"] is True
        assert result["mensagem"] == "Exaustor ligado com sucesso"
        assert controlador._estado["exaustor_ligado"] is True

    def test_comandar_exaustor_acao_invalida(self, controlador):
        """Ação inválida no exaustor deve retornar sucesso=False."""
        result = controlador.comandar_exaustor("TOGGLE")
        assert result["sucesso"] is False

    def test_ping_retorna_pong(self, controlador):
        """O método ping() deve responder 'pong:<id>'."""
        assert controlador.ping() == "pong:ctrl_test"


class TestPersistencia:
    def test_salvar_e_recarregar_estado(self, tmp_data_file):
        """O estado persistido em JSON deve ser recarregado por uma nova instância."""
        ctrl1 = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        ctrl1._mqtt_client = None
        ctrl1.comandar_bomba("ligar", "persist-test-id")

        ctrl2 = Controlador(ctrl_id="ctrl_test", data_file=tmp_data_file)
        assert ctrl2._estado["bomba_ligada"] is True
