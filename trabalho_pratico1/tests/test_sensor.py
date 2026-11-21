"""
test_sensor.py — Testes unitários e de integração do sensor contínuo em malha fechada.
"""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest

from estufa import config
from estufa.broker_local import BrokerMQTTLocal
from estufa.sensor import (
    SimuladorAmbiente,
    _on_connect,
    _on_message,
    executar_sensor,
)


class TestSimuladorAmbiente:
    """TP-01 & TE-01: Deriva contínua em malha fechada e validação de limites."""

    def test_tp01_deriva_natural_e_reversao_com_atuadores(self):
        """Com atuadores OFF, temp sobe +2.0°C e umidade cai -3.0%; com atuadores ON, inverte."""
        sim = SimuladorAmbiente(temp_inicial=30.0, umidade_inicial=40.0)

        # Atuadores desligados -> temperatura sobe (+2.0) e umidade cai (-3.0)
        temp1, umid1 = sim.proxima_leitura()
        assert temp1 == 32.0
        assert umid1 == 37.0

        # Liga bomba e exaustor -> temperatura cai (-2.5) e umidade sobe (+6.0)
        sim.atualizar_atuador("bomba", True)
        sim.atualizar_atuador("exaustor", True)
        temp2, umid2 = sim.proxima_leitura()
        assert temp2 == 29.5
        assert umid2 == 43.0

    def test_tp01_limites_fisicos_clamping(self):
        """Temperatura fica limitada a [0, 55]°C e umidade a [0, 100]%."""
        sim_quente = SimuladorAmbiente(temp_inicial=54.0, umidade_inicial=99.0)
        sim_quente.atualizar_atuador("bomba", True)
        for _ in range(5):
            t, u = sim_quente.proxima_leitura()
        assert t == 55.0
        assert u == 100.0

        sim_frio = SimuladorAmbiente(temp_inicial=1.0, umidade_inicial=1.0)
        sim_frio.atualizar_atuador("exaustor", True)
        for _ in range(5):
            t, u = sim_frio.proxima_leitura()
        assert t == 0.0
        assert u == 0.0

    def test_te01_parametros_iniciais_e_intervalo_invalidos(self):
        """Rejeita valores fora dos limites físicos, booleanos e intervalo <= 0.05s."""
        with pytest.raises(ValueError):
            SimuladorAmbiente(temp_inicial=150.0)
        with pytest.raises(ValueError):
            SimuladorAmbiente(temp_inicial=True)
        with pytest.raises(ValueError):
            SimuladorAmbiente(umidade_inicial=-5.0)
        with pytest.raises(ValueError):
            SimuladorAmbiente(umidade_inicial=105.0)
        with pytest.raises(ValueError):
            executar_sensor(intervalo=0.05)
        with pytest.raises(ValueError):
            executar_sensor(intervalo=-1.0)


class TestCallbacksFeedbackMQTT:
    """TP-02 & TE-02: Inscrição QoS 1 e tratamento seguro de payloads de feedback."""

    def test_tp02_on_connect_assina_topicos_de_status(self):
        """Ao conectar com sucesso, assina status da bomba e do exaustor com QoS 1."""
        mock_client = MagicMock()
        _on_connect(mock_client, None, None, 0, None)

        mock_client.subscribe.assert_any_call(config.TOPIC_STATUS_BOMBA, qos=1)
        mock_client.subscribe.assert_any_call(config.TOPIC_STATUS_EXAUSTOR, qos=1)
        assert mock_client.subscribe.call_count == 2

    def test_tp02_e_te02_on_message_atualiza_e_ignora_invalidos(self):
        """Payloads válidos atualizam o simulador; inválidos/desconhecidos são ignorados."""
        sim = SimuladorAmbiente()

        _on_message(None, sim, SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=json.dumps({"atuador": "bomba", "ligado": True}).encode("utf-8"),
        ))
        _on_message(None, sim, SimpleNamespace(
            topic=config.TOPIC_STATUS_EXAUSTOR,
            payload=json.dumps({"atuador": "exaustor", "ligado": True}).encode("utf-8"),
        ))
        _on_message(None, sim, SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=b"{json-quebrado",
        ))
        _on_message(None, sim, SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=json.dumps({"atuador": "aquecedor", "ligado": True}).encode("utf-8"),
        ))

        assert sim.bomba_ligada is True
        assert sim.exaustor_ligado is True

    def test_tp02_integracao_malha_fechada_com_broker(self, monkeypatch):
        """De ponta a ponta, sensor recebe status=True da bomba via MQTT e eleva umidade."""
        broker = BrokerMQTTLocal(host="127.0.0.1", port=0, silencioso=True)
        porta = broker.iniciar_em_background()
        monkeypatch.setattr(config, "MQTT_HOST", "127.0.0.1")
        monkeypatch.setattr(config, "MQTT_PORT", porta)

        umidades = []
        evento_primeira = threading.Event()
        observador = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="obs_sensor")

        def obs_connect(cli, userdata, flags, rc, props):
            if rc == 0:
                cli.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)

        def obs_msg(cli, userdata, msg):
            umidades.append(json.loads(msg.payload.decode("utf-8"))["valor"])
            if len(umidades) == 1:
                evento_primeira.set()

        observador.on_connect = obs_connect
        observador.on_message = obs_msg
        observador.connect("127.0.0.1", porta, 60)
        observador.loop_start()
        time.sleep(0.15)

        try:
            t_sensor = threading.Thread(
                target=executar_sensor,
                kwargs={"temp_inicial": 26.0, "umidade_inicial": 25.0, "intervalo": 0.2, "max_iteracoes": 4},
                daemon=True,
            )
            t_sensor.start()
            assert evento_primeira.wait(timeout=3.0)

            pub = observador.publish(
                config.TOPIC_STATUS_BOMBA,
                json.dumps({"atuador": "bomba", "ligado": True, "timestamp": time.time()}),
                qos=1,
            )
            pub.wait_for_publish(timeout=2.0)

            t_sensor.join(timeout=5.0)
            assert not t_sensor.is_alive()
            time.sleep(0.1)

            assert len(umidades) == 4
            assert umidades[-1] > umidades[0]
        finally:
            observador.loop_stop()
            observador.disconnect()
            broker.parar()
