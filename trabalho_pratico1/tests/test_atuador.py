"""
test_atuador.py — Testes unitários do processo Atuador simplificado (sem cache LRU).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from estufa import atuador, config


@pytest.fixture(autouse=True)
def resetar_estados():
    """Restaura os estados internos de bomba e exaustor antes e após cada teste."""
    atuador._estado_bomba["ligado"] = False
    atuador._estado_exaustor["ligado"] = False
    yield
    atuador._estado_bomba["ligado"] = False
    atuador._estado_exaustor["ligado"] = False


class TestAtuadorSimplificado:
    """TP-03 & TE-02: Acionamento unificado, publicação de status QoS 1 e resiliência."""

    def test_tp03_on_connect_assina_topicos_de_atuadores(self):
        """Assina comandos da bomba e do exaustor com QoS 1 ao conectar."""
        cli = MagicMock()
        atuador._on_connect(cli, None, None, 0, None)
        cli.subscribe.assert_any_call(config.TOPIC_ATUADOR_BOMBA, qos=1)
        cli.subscribe.assert_any_call(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)

    def test_tp03_comandar_bomba_e_exaustor_publica_status_qos1(self):
        """Comandos 'ligar' e 'desligar' atualizam estado e publicam status QoS 1."""
        cli = MagicMock()

        atuador._on_message(cli, None, SimpleNamespace(
            topic=config.TOPIC_ATUADOR_BOMBA,
            payload=json.dumps({"acao": "ligar", "origem": "ctrl_3"}).encode("utf-8"),
        ))
        assert atuador._estado_bomba["ligado"] is True
        topico_pub, payload_raw = cli.publish.call_args[0]
        assert topico_pub == config.TOPIC_STATUS_BOMBA
        assert json.loads(payload_raw)["ligado"] is True
        assert cli.publish.call_args[1]["qos"] == 1

        atuador._on_message(cli, None, SimpleNamespace(
            topic=config.TOPIC_ATUADOR_EXAUSTOR,
            payload=json.dumps({"acao": "ligar", "origem": "ctrl_3"}).encode("utf-8"),
        ))
        assert atuador._estado_exaustor["ligado"] is True
        assert cli.publish.call_args[0][0] == config.TOPIC_STATUS_EXAUSTOR

        atuador._on_message(cli, None, SimpleNamespace(
            topic=config.TOPIC_ATUADOR_BOMBA,
            payload=json.dumps({"acao": "desligar", "origem": "ctrl_3"}).encode("utf-8"),
        ))
        assert atuador._estado_bomba["ligado"] is False

    def test_te02_ignora_payload_malformado_e_acao_invalida(self):
        """JSON inválido ou ação desconhecida não altera estado nem publica feedback."""
        cli = MagicMock()

        atuador._on_message(cli, None, SimpleNamespace(
            topic=config.TOPIC_ATUADOR_BOMBA,
            payload=b"{corrompido",
        ))
        atuador._on_message(cli, None, SimpleNamespace(
            topic=config.TOPIC_ATUADOR_EXAUSTOR,
            payload=json.dumps({"acao": "invalido"}).encode("utf-8"),
        ))

        assert atuador._estado_bomba["ligado"] is False
        assert atuador._estado_exaustor["ligado"] is False
        cli.publish.assert_not_called()
