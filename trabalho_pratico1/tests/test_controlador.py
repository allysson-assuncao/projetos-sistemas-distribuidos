"""
test_controlador.py — Testes unitários e de integração do Controlador distribuído.

Cobre:
- Inicialização, persistência JSON e validação de configuração/limites.
- Algoritmo Bully de eleição de líder e failover após queda do líder.
- Consenso dinâmico (3/3, 2/3 mascarando --byzantino, 2/2 e 1/1 degradado).
- Replicação síncrona via commit_estado mantendo data_ctrl_*.json idênticos.
- Publicação MQTT exclusiva do Líder e sincronização automática ao reconectar.
"""

import json
import socket
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from estufa import config
from estufa.controlador import Controlador, _avaliar_regras_atuacao
from estufa.middleware import ClusterMiddleware, ErroQuorum


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aguardar(condicao, timeout: float = 3.0) -> None:
    """Aguarda uma condição assíncrona em testes sem depender de sleeps fixos frágeis."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicao():
            return
        time.sleep(0.05)
    assert condicao()


def _criar_cluster(tmp_path, byzantinos: set[str] | None = None, heartbeat: float = 0.2):
    """Instancia configuração isolada para 3 controladores em portas livres e tmp_path."""
    byzantinos = byzantinos or set()
    pares = [
        {
            "id": "ctrl_1",
            "rank": 1,
            "host": "127.0.0.1",
            "port": _porta_livre(),
            "data_file": str(tmp_path / "data_ctrl_1.json"),
        },
        {
            "id": "ctrl_2",
            "rank": 2,
            "host": "127.0.0.1",
            "port": _porta_livre(),
            "data_file": str(tmp_path / "data_ctrl_2.json"),
        },
        {
            "id": "ctrl_3",
            "rank": 3,
            "host": "127.0.0.1",
            "port": _porta_livre(),
            "data_file": str(tmp_path / "data_ctrl_3.json"),
        },
    ]

    ctrls = {}
    for cfg in pares:
        ctrls[cfg["id"]] = Controlador(
            ctrl_id=cfg["id"],
            port=cfg["port"],
            data_file=cfg["data_file"],
            host=cfg["host"],
            byzantino=(cfg["id"] in byzantinos),
            pares=pares,
            timeout_rpc=0.35,
            heartbeat_interval=heartbeat,
        )
    return ctrls, pares


def _ler_json(caminho: str) -> dict:
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


class TestUnidadeControlador:
    def test_resolucao_config_simplificada(self):
        """Aceita números (1..3) ou IDs ('ctrl_1'..'ctrl_3') e rejeita inválidos."""
        assert config.obter_config_controlador(1)["port"] == 8001
        assert config.obter_config_controlador("2")["id"] == "ctrl_2"
        assert config.obter_config_controlador("ctrl_3")["data_file"] == "data_ctrl_3.json"

        with pytest.raises(ValueError):
            config.obter_config_controlador(0)
        with pytest.raises(ValueError):
            config.obter_config_controlador("ctrl_9")
        with pytest.raises(ValueError):
            config.obter_config_controlador(True)

    def test_inicializacao_e_fallback_json_corrompido(self, tmp_path):
        """Inicializa estado padrão se arquivo não existir ou estiver corrompido."""
        arq = str(tmp_path / "data_ctrl_1.json")
        ctrl_novo = Controlador(ctrl_id="ctrl_1", data_file=arq)
        assert ctrl_novo._estado["bomba_ligada"] is False
        assert ctrl_novo._estado["umidade"] is None

        with open(arq, "w", encoding="utf-8") as f:
            f.write("{corrompido")
        ctrl_corrompido = Controlador(ctrl_id="ctrl_1", data_file=arq)
        assert ctrl_corrompido._estado["temperatura"] is None

    def test_regras_histerese_bomba_e_exaustor(self):
        """Valida acionamento e desligamento dentro das bandas de histerese."""
        bomba, exaustor = _avaliar_regras_atuacao(36.5, 25.0, False, False)
        assert bomba is True and exaustor is True

        bomba, exaustor = _avaliar_regras_atuacao(22.0, 50.0, True, True)
        assert bomba is True and exaustor is True  # mantém na faixa morta

        bomba, exaustor = _avaliar_regras_atuacao(14.0, 72.0, True, True)
        assert bomba is False and exaustor is False

    def test_modo_byzantino_e_validacao_commit(self, tmp_path):
        """Modo bizantino retorna valores adulterados e commit_estado valida schema."""
        arq = str(tmp_path / "byz.json")
        ctrl = Controlador(ctrl_id="ctrl_2", data_file=arq, byzantino=True)

        voto = ctrl.coletar_voto_estado({"temperatura": 25.0, "umidade": 50.0})
        assert voto["temperatura"] == 999.9
        assert voto["umidade"] == -50.0
        assert voto["bomba_ligada"] is True

        with pytest.raises(ValueError):
            ctrl.commit_estado({"temperatura": 999.0, "bomba_ligada": True, "exaustor_ligado": False})
        with pytest.raises(ValueError):
            ctrl.commit_estado({"bomba_ligada": "sim", "exaustor_ligado": False})


class TestIntegracaoClusterDistribuido:
    """Testes reais com servidores XML-RPC locais para eleição, consenso e recuperação."""

    def test_tp01_eleicao_bully_elege_maior_rank(self, tmp_path):
        """TP-01: Ao iniciar os 3 controladores, ctrl_3 é eleito líder pelo algoritmo Bully."""
        ctrls, _ = _criar_cluster(tmp_path)
        try:
            ctrls["ctrl_1"].iniciar_servidor_rpc()
            assert ctrls["ctrl_1"].eh_lider() is True

            ctrls["ctrl_2"].iniciar_servidor_rpc()
            assert ctrls["ctrl_2"].eh_lider() is True
            assert ctrls["ctrl_1"].lider_id == "ctrl_2"

            ctrls["ctrl_3"].iniciar_servidor_rpc()
            assert ctrls["ctrl_3"].eh_lider() is True
            assert ctrls["ctrl_1"].lider_id == "ctrl_3"
            assert ctrls["ctrl_2"].lider_id == "ctrl_3"
        finally:
            for c in ctrls.values():
                c.parar()

    def test_tp02_consenso_commit_mantem_bancos_json_identicos(self, tmp_path):
        """TP-02: Consenso coordenado pelo líder grava dados idênticos nos 3 arquivos JSON."""
        ctrls, pares = _criar_cluster(tmp_path)
        try:
            for cid in ("ctrl_1", "ctrl_2", "ctrl_3"):
                ctrls[cid].iniciar_servidor_rpc()

            mw = ClusterMiddleware(controladores=pares, timeout=1.0)
            resp = mw.comandar_bomba(True)
            assert resp["bomba_ligada"] is True
            assert resp["lider_id"] == "ctrl_3"

            d1 = _ler_json(ctrls["ctrl_1"].data_file)
            d2 = _ler_json(ctrls["ctrl_2"].data_file)
            d3 = _ler_json(ctrls["ctrl_3"].data_file)

            assert d1 == d2 == d3
            assert d1["bomba_ligada"] is True
            assert d1["lider_id"] == "ctrl_3"
        finally:
            for c in ctrls.values():
                c.parar()

    def test_tp04_apenas_lider_publica_comando_mqtt(self, tmp_path):
        """TP-04: Mesmo recebendo a mesma leitura MQTT, somente o líder publica atuação."""
        ctrls, _ = _criar_cluster(tmp_path)
        try:
            for cid in ("ctrl_1", "ctrl_2", "ctrl_3"):
                ctrls[cid].iniciar_servidor_rpc()
                ctrls[cid]._mqtt_client = MagicMock()

            msg_temp = SimpleNamespace(
                topic=config.TOPIC_TEMPERATURA,
                payload=b'{"valor": 38.5}',
            )
            # Os 3 recebem a leitura MQTT
            for cid in ("ctrl_1", "ctrl_2", "ctrl_3"):
                ctrls[cid]._on_message(None, None, msg_temp)

            assert ctrls["ctrl_1"]._mqtt_client.publish.call_count == 0
            assert ctrls["ctrl_2"]._mqtt_client.publish.call_count == 0
            assert ctrls["ctrl_3"]._mqtt_client.publish.call_count == 1

            topico_pub = ctrls["ctrl_3"]._mqtt_client.publish.call_args[0][0]
            assert topico_pub == config.TOPIC_ATUADOR_EXAUSTOR
            assert _ler_json(ctrls["ctrl_1"].data_file)["exaustor_ligado"] is True
            assert _ler_json(ctrls["ctrl_2"].data_file)["exaustor_ligado"] is True
            assert _ler_json(ctrls["ctrl_3"].data_file)["exaustor_ligado"] is True
        finally:
            for c in ctrls.values():
                c.parar()

    def test_te01_e_te03_failover_e_degradacao_sequencial_ate_1_ativo(self, tmp_path):
        """TE-01 & TE-03: Queda de ctrl_3 elege ctrl_2; queda de ctrl_2 mantém ctrl_1 em 1/1."""
        ctrls, pares = _criar_cluster(tmp_path, heartbeat=0.15)
        try:
            for cid in ("ctrl_1", "ctrl_2", "ctrl_3"):
                ctrls[cid].iniciar_servidor_rpc()

            mw = ClusterMiddleware(controladores=pares, timeout=2.0)

            # Derruba o líder ctrl_3 (restam 2 ativos -> 2/2)
            ctrls["ctrl_3"].parar()
            _aguardar(lambda: ctrls["ctrl_2"].eh_lider() and ctrls["ctrl_1"].lider_id == "ctrl_2")

            resp2 = mw.comandar_exaustor(True)
            assert resp2["exaustor_ligado"] is True
            assert resp2["lider_id"] == "ctrl_2"
            assert _ler_json(ctrls["ctrl_1"].data_file) == _ler_json(ctrls["ctrl_2"].data_file)

            # Derruba ctrl_2 (resta 1 ativo -> modo degradado 1/1)
            ctrls["ctrl_2"].parar()
            _aguardar(lambda: ctrls["ctrl_1"].eh_lider())

            resp1 = mw.comandar_bomba(True)
            assert resp1["bomba_ligada"] is True
            assert resp1["lider_id"] == "ctrl_1"
            assert _ler_json(ctrls["ctrl_1"].data_file)["bomba_ligada"] is True
        finally:
            for c in ctrls.values():
                c.parar()

    def test_te02_byzantino_rejeitado_por_consenso_antes_da_persistencia(self, tmp_path):
        """TE-02: 1 nó --byzantino entre 3 ativos não corrompe os bancos JSON honestos."""
        ctrls, pares = _criar_cluster(tmp_path, byzantinos={"ctrl_2"})
        try:
            for cid in ("ctrl_1", "ctrl_2", "ctrl_3"):
                ctrls[cid].iniciar_servidor_rpc()

            msg_umid = SimpleNamespace(
                topic=config.TOPIC_UMIDADE_SOLO,
                payload=b'{"valor": 20.0}',
            )
            ctrls["ctrl_3"]._on_message(None, None, msg_umid)

            d1 = _ler_json(ctrls["ctrl_1"].data_file)
            d3 = _ler_json(ctrls["ctrl_3"].data_file)
            assert d1["umidade"] == 20.0
            assert d3["umidade"] == 20.0
            assert d1["bomba_ligada"] is True
            assert d3["bomba_ligada"] is True

            # Consulta via ClusterMiddleware também mascara ctrl_2 bizantino
            mw = ClusterMiddleware(controladores=pares, timeout=0.8)
            estado = mw.obter_estado()
            assert estado["umidade"] == 20.0
            assert estado["bomba_ligada"] is True
        finally:
            for c in ctrls.values():
                c.parar()

    def test_te05_reconexao_replica_sincroniza_banco_json_automaticamente(self, tmp_path):
        """TE-05: Controlador que caiu e reiniciou sincroniza data_ctrl_X.json com o cluster."""
        ctrls, pares = _criar_cluster(tmp_path, heartbeat=0.15)
        try:
            ctrls["ctrl_1"].iniciar_servidor_rpc()
            ctrls["ctrl_2"].iniciar_servidor_rpc()

            # Cluster avança enquanto ctrl_3 está fora do ar
            mw = ClusterMiddleware(controladores=pares, timeout=2.0)
            mw.comandar_bomba(True)
            msg_temp = SimpleNamespace(topic=config.TOPIC_TEMPERATURA, payload=b'{"valor": 29.5}')
            ctrls["ctrl_2"]._on_message(None, None, msg_temp)

            # ctrl_3 inicia depois com disco desatualizado/inexistente
            ctrls["ctrl_3"].iniciar_servidor_rpc()
            _aguardar(
                lambda: ctrls["ctrl_3"].eh_lider()
                and ctrls["ctrl_1"].lider_id == "ctrl_3"
                and ctrls["ctrl_2"].lider_id == "ctrl_3"
            )

            d1 = _ler_json(ctrls["ctrl_1"].data_file)
            d2 = _ler_json(ctrls["ctrl_2"].data_file)
            d3 = _ler_json(ctrls["ctrl_3"].data_file)

            assert d3["bomba_ligada"] is True
            assert d3["temperatura"] == 29.5
            assert d1["bomba_ligada"] == d2["bomba_ligada"] == d3["bomba_ligada"] is True
            assert d1["temperatura"] == d2["temperatura"] == d3["temperatura"] == 29.5
            assert ctrls["ctrl_3"].eh_lider() is True
        finally:
            for c in ctrls.values():
                c.parar()
