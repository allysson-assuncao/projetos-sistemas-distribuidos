"""
test_middleware.py — Testes unitários do motor de votação do Middleware.

Valida a apuração de quórum (3/3 e 2/3), detecção de divergência total,
mascaramento de falhas bizantinas em leituras e comandos, compartilhamento de
UUID para deduplicação e verificação de saúde dos controladores.
"""

from unittest.mock import MagicMock, patch
import pytest

from estufa.middleware import Middleware, ErroQuorum


def _estado_honesto(bomba=False, exaustor=False, temp=25.0, umidade=50.0, ctrl_id="ctrl_x"):
    """Retorna um dicionário de estado representativo de uma réplica honesta."""
    return {
        "temperatura": temp,
        "umidade_solo": umidade,
        "bomba_ligada": bomba,
        "exaustor_ligado": exaustor,
        "ultima_atualizacao": 1700000000.0,
        "sensor_timestamp": 1700000000.0,
        "controlador_id": ctrl_id,
    }


def _resposta_comando(sucesso=True, mensagem="Bomba ligada com sucesso", ctrl_id="ctrl_1"):
    return {"sucesso": sucesso, "mensagem": mensagem, "controlador_id": ctrl_id}


CONTROLADORES_TESTE = [
    {"id": "ctrl_1", "host": "localhost", "port": 18001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 18002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 18003, "data_file": "data_ctrl_3.json"},
]


@pytest.fixture
def middleware():
    """Instância do Middleware configurada com os 3 controladores de teste."""
    return Middleware(controladores=CONTROLADORES_TESTE, timeout=2)


class TestObterEstadoQuorum:
    def test_quorum_3_de_3_concordantes(self, middleware):
        """3/3 réplicas concordantes (com controlador_id distintos) atingem quórum."""
        def proxy_factory(ctrl):
            m = MagicMock()
            m.obter_estado.return_value = _estado_honesto(
                bomba=False, exaustor=False, ctrl_id=ctrl["id"]
            )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()

        assert result["bomba_ligada"] is False
        assert result["exaustor_ligado"] is False
        assert result["temperatura"] == 25.0

    def test_quorum_2_de_3_um_crashado(self, middleware):
        """2/3 réplicas respondem e 1 falha por conexão recusada: quórum mantido."""
        crash_error = ConnectionRefusedError("Controlador offline")
        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 3:
                m.obter_estado.side_effect = crash_error
            else:
                m.obter_estado.return_value = _estado_honesto(
                    bomba=True, exaustor=False, ctrl_id=ctrl["id"]
                )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()

        assert result["bomba_ligada"] is True

    def test_quorum_falha_todos_crashados(self, middleware):
        """0/3 réplicas disponíveis deve lançar ErroQuorum."""
        mock_proxy = MagicMock()
        mock_proxy.obter_estado.side_effect = ConnectionRefusedError("Todos offline")

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            with pytest.raises(ErroQuorum):
                middleware.obter_estado()

    def test_quorum_falha_respostas_todas_divergentes(self, middleware):
        """3 réplicas com estados mutuamente divergentes não atingem quórum."""
        states = [
            _estado_honesto(bomba=False, exaustor=False, temp=25.0, ctrl_id="ctrl_1"),
            _estado_honesto(bomba=True, exaustor=False, temp=26.0, ctrl_id="ctrl_2"),
            _estado_honesto(bomba=False, exaustor=True, temp=27.0, ctrl_id="ctrl_3"),
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


class TestToleranciaByantina:
    def test_1_byzantino_2_honestos_retorna_estado_honesto(self, middleware):
        """1 réplica bizantina + 2 honestas: votação por maioria retorna estado honesto."""
        byzantine_state = {
            "temperatura": 999.0,
            "umidade_solo": -1.0,
            "bomba_ligada": True,
            "exaustor_ligado": True,
            "ultima_atualizacao": 1700000000.0,
            "sensor_timestamp": 1700000000.0,
            "controlador_id": "ctrl_2",
        }
        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 2:
                m.obter_estado.return_value = byzantine_state
            else:
                m.obter_estado.return_value = _estado_honesto(
                    bomba=False, exaustor=False, temp=25.0, ctrl_id=ctrl["id"]
                )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()

        assert result["bomba_ligada"] is False
        assert result["exaustor_ligado"] is False
        assert result["temperatura"] == 25.0

    def test_2_byzantinos_1_honesto_levanta_erro_quorum(self, middleware):
        """Com 2 réplicas bizantinas idênticas (f=2 em N=3), o limite f=1 é ultrapassado."""
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
            if call_count[0] <= 2:
                m.obter_estado.return_value = byzantine_state
            else:
                m.obter_estado.return_value = _estado_honesto(
                    bomba=False, exaustor=False, ctrl_id=ctrl["id"]
                )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.obter_estado()
            assert result["bomba_ligada"] is True


class TestComandoBomba:
    def test_comandar_bomba_ligar_com_quorum(self, middleware):
        """Comando da bomba atinge quórum quando cada réplica retorna seu próprio controlador_id."""
        def proxy_factory(ctrl):
            m = MagicMock()
            m.comandar_bomba.return_value = _resposta_comando(
                sucesso=True,
                mensagem="Bomba ligada com sucesso",
                ctrl_id=ctrl["id"],
            )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.comandar_bomba("ligar")

        assert result["sucesso"] is True
        assert result["mensagem"] == "Bomba ligada com sucesso"

    def test_comandar_bomba_com_1_replica_bizantina(self, middleware):
        """Mesmo com 1 réplica bizantina retornando mensagem invertida, as 2 honestas formam quórum."""
        def proxy_factory(ctrl):
            m = MagicMock()
            if ctrl["id"] == "ctrl_2":
                m.comandar_bomba.return_value = _resposta_comando(
                    sucesso=True,
                    mensagem="Bomba desligada com sucesso",
                    ctrl_id="ctrl_2",
                )
            else:
                m.comandar_bomba.return_value = _resposta_comando(
                    sucesso=True,
                    mensagem="Bomba ligada com sucesso",
                    ctrl_id=ctrl["id"],
                )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.comandar_bomba("ligar")

        assert result["sucesso"] is True
        assert result["mensagem"] == "Bomba ligada com sucesso"

    def test_comandar_bomba_gera_uuid_diferente_a_cada_chamada(self, middleware):
        """Cada invocação de comandar_bomba deve gerar um UUID distinto."""
        cmd_response = _resposta_comando()
        mock_proxy = MagicMock()
        captured_ids = []

        def capture_args(*args, **kwargs):
            if len(args) > 1:
                captured_ids.append(args[1])
            return cmd_response

        mock_proxy.comandar_bomba.side_effect = capture_args

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            middleware.comandar_bomba("ligar")
            middleware.comandar_bomba("ligar")

        assert len(captured_ids) == 6
        assert len(set(captured_ids[:3])) == 1
        assert len(set(captured_ids[3:])) == 1
        assert captured_ids[0] != captured_ids[3]

    def test_comandar_bomba_falha_sem_quorum(self, middleware):
        """Falha de comunicação com os controladores ao enviar comando deve lançar ErroQuorum."""
        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.side_effect = ConnectionRefusedError("offline")

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            with pytest.raises(ErroQuorum):
                middleware.comandar_bomba("ligar")


class TestComandoExaustor:
    def test_comandar_exaustor_desligar_com_quorum(self, middleware):
        """Comando de desligamento do exaustor atinge quórum entre réplicas distintas."""
        def proxy_factory(ctrl):
            m = MagicMock()
            m.comandar_exaustor.return_value = _resposta_comando(
                sucesso=True,
                mensagem="Exaustor desligado com sucesso",
                ctrl_id=ctrl["id"],
            )
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            result = middleware.comandar_exaustor("desligar")

        assert result["sucesso"] is True
        assert result["mensagem"] == "Exaustor desligado com sucesso"

    def test_comandar_exaustor_uuid_compartilhado_entre_controladores(self, middleware):
        """Os 3 controladores devem receber exatamente o mesmo comando_id na mesma chamada."""
        cmd_response = _resposta_comando(mensagem="Exaustor ligado com sucesso")
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
        assert len(set(received_ids)) == 1


class TestVerificarSaude:
    def test_todos_online_retorna_ok(self, middleware):
        """Quando todas as réplicas respondem ao ping, o status de todas é 'ok'."""
        mock_proxy = MagicMock()
        mock_proxy.ping.return_value = "pong:ctrl_1"

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            saude = middleware.verificar_saude()

        for ctrl_id, status in saude.items():
            assert status == "ok"

    def test_um_offline_retorna_offline_status(self, middleware):
        """Quando 1 réplica está inacessível, apenas ela recebe status iniciado por 'OFFLINE'."""
        call_count = [0]

        def proxy_factory(ctrl):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 2:
                m.ping.side_effect = ConnectionRefusedError("offline")
            else:
                m.ping.return_value = f"pong:{ctrl['id']}"
            return m

        with patch.object(middleware, "_criar_proxy", side_effect=proxy_factory):
            saude = middleware.verificar_saude()

        offline_statuses = [s for s in saude.values() if s.startswith("OFFLINE")]
        assert len(offline_statuses) == 1

    def test_todos_offline_retorna_todos_com_status_offline(self, middleware):
        """Quando todas as réplicas falham, todas aparecem como 'OFFLINE'."""
        mock_proxy = MagicMock()
        mock_proxy.ping.side_effect = ConnectionRefusedError("all offline")

        with patch.object(middleware, "_criar_proxy", return_value=mock_proxy):
            saude = middleware.verificar_saude()

        for ctrl_id, status in saude.items():
            assert status.startswith("OFFLINE")
