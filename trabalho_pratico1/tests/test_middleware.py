"""
test_middleware.py — Testes unitários da camada lógica ClusterMiddleware.

Valida comunicação direta Cliente <-> Controladores (sem porta :9000),
descoberta e cache de líder, failover automático e quórum dinâmico
(3/3, 2/3 bizantino, 2/2 concordante, 1/1 degradado e ErroQuorum).
"""

import socket
from unittest.mock import MagicMock, patch
import xmlrpc.client
import pytest

from estufa.middleware import ClusterMiddleware, ErroQuorum


def _estado(temp=25.0, umidade=50.0, bomba=False, exaustor=False, lider="ctrl_3"):
    return {
        "temperatura": temp,
        "umidade": umidade,
        "bomba_ligada": bomba,
        "exaustor_ligado": exaustor,
        "ultima_atualizacao": "2026-11-17T12:00:00+00:00",
        "lider_id": lider,
    }


CONTROLADORES_TESTE = [
    ("localhost", 18001),
    ("localhost", 18002),
    ("localhost", 18003),
]


@pytest.fixture
def mw():
    return ClusterMiddleware(controladores=CONTROLADORES_TESTE, timeout=0.5)


class TestComunicacaoDiretaEFailover:
    """TP-03 & TE-01: Chamadas diretas aos controladores e failover transparente."""

    def test_tp03_obter_estado_direto_sem_intermediario(self, mw):
        """Consulta diretamente os 3 controladores e consolida estado oficial."""
        def proxy_factory(ctrl):
            m = MagicMock()
            m.obter_estado.return_value = _estado(temp=26.5, umidade=48.0, bomba=True)
            return m

        with patch.object(mw, "_criar_proxy", side_effect=proxy_factory):
            estado = mw.obter_estado()

        assert estado["temperatura"] == 26.5
        assert estado["umidade"] == 48.0
        assert estado["bomba_ligada"] is True
        assert estado["lider_id"] == "ctrl_3"

    def test_tp03_comandar_bomba_e_exaustor_validacao_booleana(self, mw):
        """Comandos diretos validam argumento booleano e retornam estado atualizado."""
        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.return_value = {
            **_estado(bomba=True, lider="ctrl_3"),
            "sucesso": True,
            "mensagem": "Bomba ligada com sucesso",
        }
        mock_proxy.comandar_exaustor.return_value = {
            **_estado(exaustor=False, lider="ctrl_3"),
            "sucesso": True,
            "mensagem": "Exaustor desligado com sucesso",
        }

        with patch.object(mw, "_criar_proxy", return_value=mock_proxy):
            resp_bomba = mw.comandar_bomba(True)
            resp_exaustor = mw.comandar_exaustor(False)

        assert resp_bomba["bomba_ligada"] is True
        assert resp_exaustor["exaustor_ligado"] is False

        with pytest.raises(ValueError):
            mw.comandar_bomba("ligar")
        with pytest.raises(ValueError):
            mw.comandar_exaustor(1)

    def test_te01_failover_automatico_quando_lider_cai_ou_da_timeout(self, mw):
        """Quando ctrl_3 (rank maior) recusa conexão ou dá timeout, migra para ctrl_2."""
        chamadas = []

        def proxy_factory(ctrl):
            chamadas.append(ctrl["id"])
            m = MagicMock()
            if ctrl["id"] == "ctrl_3":
                m.comandar_bomba.side_effect = ConnectionRefusedError("ctrl_3 fechado")
            elif ctrl["id"] == "ctrl_2":
                m.comandar_bomba.return_value = {
                    **_estado(bomba=True, lider="ctrl_2"),
                    "sucesso": True,
                    "mensagem": "Bomba ligada com sucesso",
                }
            return m

        with patch.object(mw, "_criar_proxy", side_effect=proxy_factory):
            resp = mw.comandar_bomba(True)

        assert chamadas[:2] == ["ctrl_3", "ctrl_2"]
        assert resp["lider_id"] == "ctrl_2"
        assert mw._lider_atual["id"] == "ctrl_2"

    def test_te01_failover_em_socket_timeout(self, mw):
        """Timeout de socket em ctrl_3 também dispara failover transparente para ctrl_2."""
        def proxy_factory(ctrl):
            m = MagicMock()
            if ctrl["id"] == "ctrl_3":
                m.comandar_exaustor.side_effect = socket.timeout("timeout")
            else:
                m.comandar_exaustor.return_value = {
                    **_estado(exaustor=True, lider="ctrl_2"),
                    "sucesso": True,
                    "mensagem": "Exaustor ligado com sucesso",
                }
            return m

        with patch.object(mw, "_criar_proxy", side_effect=proxy_factory):
            resp = mw.comandar_exaustor(True)

        assert resp["exaustor_ligado"] is True
        assert resp["lider_id"] == "ctrl_2"

    def test_verificar_saude_identifica_lider_e_offline(self, mw):
        """verificar_saude reporta quantidade de ativos, líder eleito e detalhes por nó."""
        def proxy_factory(ctrl):
            m = MagicMock()
            if ctrl["id"] == "ctrl_3":
                m.ping.side_effect = ConnectionRefusedError("offline")
            else:
                m.ping.return_value = {
                    "status": "ok",
                    "id": ctrl["id"],
                    "rank": ctrl["rank"],
                    "lider_id": "ctrl_2",
                }
            return m

        with patch.object(mw, "_criar_proxy", side_effect=proxy_factory):
            saude = mw.verificar_saude()

        assert saude["ativos"] == 2
        assert saude["total"] == 3
        assert saude["lider_id"] == "ctrl_2"
        assert saude["detalhes"]["ctrl_2"] == "ok (LÍDER)"
        assert saude["detalhes"]["ctrl_1"] == "ok (seguidor)"
        assert saude["detalhes"]["ctrl_3"].startswith("OFFLINE")


class TestConsensoEQuorumDinamico:
    """TE-02, TE-03 & TE-04: Quórum dinâmico, mascaramento bizantino e ErroQuorum."""

    def test_te02_1_byzantino_entre_3_ativos_mascarado(self, mw):
        """Com 3 réplicas ativas e 1 bizantina, maioria 2/3 vence e descarta fraude."""
        def proxy_factory(ctrl):
            m = MagicMock()
            if ctrl["id"] == "ctrl_2":
                m.obter_estado.return_value = _estado(
                    temp=999.9, umidade=-50.0, bomba=True, exaustor=True, lider="ctrl_3"
                )
            else:
                m.obter_estado.return_value = _estado(
                    temp=24.0, umidade=55.0, bomba=False, exaustor=False, lider="ctrl_3"
                )
            return m

        with patch.object(mw, "_criar_proxy", side_effect=proxy_factory):
            oficial = mw.obter_estado()

        assert oficial["temperatura"] == 24.0
        assert oficial["umidade"] == 55.0
        assert oficial["bomba_ligada"] is False

    def test_te03_quorum_2_ativos_concordantes_e_1_degradado(self, mw):
        """Funciona com 2/2 concordantes e em modo degradado 1/1 quando 2 caem."""
        dois_ativos = [
            _estado(temp=22.0, umidade=60.0, bomba=False, lider="ctrl_2"),
            _estado(temp=22.0, umidade=60.0, bomba=False, lider="ctrl_2"),
        ]
        res_2 = ClusterMiddleware.calcular_consenso(dois_ativos)
        assert res_2["temperatura"] == 22.0

        um_ativo = [_estado(temp=31.0, umidade=35.0, exaustor=True, lider="ctrl_1")]
        res_1 = ClusterMiddleware.calcular_consenso(um_ativo)
        assert res_1["temperatura"] == 31.0
        assert res_1["exaustor_ligado"] is True

    def test_te03_quorum_mantido_quando_uma_replica_trava_timeout(self):
        """Se 1 réplica dá timeout, as 2 restantes ainda fecham consenso."""
        mw_rapido = ClusterMiddleware(controladores=CONTROLADORES_TESTE, timeout=0.2)

        def proxy_factory(ctrl):
            m = MagicMock()
            if ctrl["id"] == "ctrl_3":
                m.obter_estado.side_effect = socket.timeout("timeout")
            else:
                m.obter_estado.return_value = _estado(temp=27.0, umidade=45.0, lider="ctrl_2")
            return m

        with patch.object(mw_rapido, "_criar_proxy", side_effect=proxy_factory):
            estado = mw_rapido.obter_estado()

        assert estado["temperatura"] == 27.0

    def test_te04_erro_quorum_em_empate_2_ativos_divergentes(self):
        """Com 2 ativos em conflito (ex: 1 honesto vs 1 bizantino), levanta ErroQuorum."""
        conflito = [
            _estado(temp=25.0, umidade=50.0, bomba=False),
            _estado(temp=999.9, umidade=-50.0, bomba=True),
        ]
        with pytest.raises(ErroQuorum):
            ClusterMiddleware.calcular_consenso(conflito)

    def test_te04_erro_quorum_em_3_divergentes_ou_0_ativos(self, mw):
        """3 respostas totalmente distintas ou 0 ativos devem levantar ErroQuorum."""
        tres_distintos = [
            _estado(temp=20.0),
            _estado(temp=25.0),
            _estado(temp=30.0),
        ]
        with pytest.raises(ErroQuorum):
            ClusterMiddleware.calcular_consenso(tres_distintos)

        with pytest.raises(ErroQuorum):
            ClusterMiddleware.calcular_consenso([])

        def offline_factory(ctrl):
            m = MagicMock()
            m.obter_estado.side_effect = ConnectionRefusedError("offline")
            m.comandar_bomba.side_effect = ConnectionRefusedError("offline")
            return m

        with patch.object(mw, "_criar_proxy", side_effect=offline_factory):
            with pytest.raises(ErroQuorum):
                mw.obter_estado()
            with pytest.raises(ErroQuorum):
                mw.comandar_bomba(True)

    def test_fault_xmlrpc_de_quorum_propagada_como_erro_quorum(self, mw):
        """Fault remota contendo ERRO_QUORUM deve ser convertida imediatamente para ErroQuorum."""
        mock_proxy = MagicMock()
        mock_proxy.comandar_bomba.side_effect = xmlrpc.client.Fault(1, "ERRO_QUORUM: conflito")

        with patch.object(mw, "_criar_proxy", return_value=mock_proxy):
            with pytest.raises(ErroQuorum):
                mw.comandar_bomba(True)
