"""
test_sensor.py — Testes unitários e de integração do sensor com malha fechada.
"""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt

from estufa import config
from estufa.broker_local import BrokerMQTTLocal
from estufa.sensor import (
    PERFIS,
    SimuladorAmbiente,
    _configurar_callbacks_feedback,
    executar_sensor,
)


class TestSimuladorAmbiente:
    def test_perfis_iniciais_dentro_das_faixas(self):
        """A primeira leitura de cada perfil deve respeitar sua faixa inicial."""
        for nome, faixa in PERFIS.items():
            sim = SimuladorAmbiente(perfil=nome)
            temp, umidade = sim.proxima_leitura()
            assert faixa["temp"][0] <= temp <= faixa["temp"][1]
            assert faixa["umidade"][0] <= umidade <= faixa["umidade"][1]

    def test_bomba_ligada_aumenta_umidade_ate_limite(self):
        """Com bomba ligada, a umidade sobe gradualmente e respeita teto de 100%."""
        sim = SimuladorAmbiente(perfil="seco")
        _, umidade_inicial = sim.proxima_leitura()
        sim.atualizar_atuador("bomba", True)

        anterior = umidade_inicial
        for _ in range(5):
            _, atual = sim.proxima_leitura()
            assert atual > anterior
            anterior = atual

        for _ in range(30):
            _, atual = sim.proxima_leitura()
        assert atual == 100.0

    def test_bomba_desligada_no_modo_seco_reduz_umidade(self):
        """Com bomba desligada no modo seco, a umidade cai até o piso de 0%."""
        sim = SimuladorAmbiente(perfil="seco")
        _, umidade_inicial = sim.proxima_leitura()
        sim.atualizar_atuador("bomba", False)

        _, seguinte = sim.proxima_leitura()
        assert seguinte < umidade_inicial

        for _ in range(30):
            _, atual = sim.proxima_leitura()
        assert atual == 0.0

    def test_exaustor_ligado_reduz_temperatura(self):
        """Com exaustor ligado, a temperatura cai gradualmente até o piso de 0°C."""
        sim = SimuladorAmbiente(perfil="quente")
        temp_inicial, _ = sim.proxima_leitura()
        sim.atualizar_atuador("exaustor", True)

        anterior = temp_inicial
        for _ in range(5):
            atual, _ = sim.proxima_leitura()
            assert atual < anterior
            anterior = atual

        for _ in range(30):
            atual, _ = sim.proxima_leitura()
        assert atual == 0.0

    def test_exaustor_desligado_no_modo_quente_aumenta_temperatura(self):
        """Com exaustor desligado no modo quente, a temperatura sobe até o teto de 55°C."""
        sim = SimuladorAmbiente(perfil="quente")
        temp_inicial, _ = sim.proxima_leitura()
        sim.atualizar_atuador("exaustor", False)

        seguinte, _ = sim.proxima_leitura()
        assert seguinte > temp_inicial

        for _ in range(30):
            atual, _ = sim.proxima_leitura()
        assert atual == 55.0

    def test_atualizar_atuador_ignora_nome_desconhecido(self):
        """Atuadores inválidos não devem alterar o estado da bomba ou do exaustor."""
        sim = SimuladorAmbiente(perfil="normal")
        sim.atualizar_atuador("aquecedor", True)
        assert sim.bomba_ligada is False
        assert sim.exaustor_ligado is False


class TestCallbacksFeedbackMQTT:
    def test_on_connect_assina_topicos_de_status(self):
        """Ao conectar com sucesso, o sensor assina status da bomba e do exaustor."""
        sim = SimuladorAmbiente()
        evento = threading.Event()
        mock_client = MagicMock()
        _configurar_callbacks_feedback(mock_client, sim, evento)

        mock_client.on_connect(mock_client, None, None, 0, None)

        mock_client.subscribe.assert_any_call(config.TOPIC_STATUS_BOMBA, qos=1)
        mock_client.subscribe.assert_any_call(config.TOPIC_STATUS_EXAUSTOR, qos=1)
        assert mock_client.subscribe.call_count == 2

    def test_on_subscribe_sinaliza_apos_duas_confirmacoes(self):
        """O evento de subscrição só é sinalizado após confirmar os dois tópicos."""
        sim = SimuladorAmbiente()
        evento = threading.Event()
        mock_client = MagicMock()
        _configurar_callbacks_feedback(mock_client, sim, evento)

        mock_client.on_subscribe(mock_client, None, 1, [], None)
        assert not evento.is_set()
        mock_client.on_subscribe(mock_client, None, 2, [], None)
        assert evento.is_set()

    def test_on_message_atualiza_estados_e_ignora_payload_invalido(self):
        """Mensagens válidas em estufa/status/* atualizam o simulador; inválidas são ignoradas."""
        sim = SimuladorAmbiente()
        evento = threading.Event()
        mock_client = MagicMock()
        _configurar_callbacks_feedback(mock_client, sim, evento)

        msg_bomba = SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=json.dumps({"atuador": "bomba", "ligado": True}).encode("utf-8"),
        )
        msg_exaustor = SimpleNamespace(
            topic=config.TOPIC_STATUS_EXAUSTOR,
            payload=json.dumps({"atuador": "exaustor", "ligado": True}).encode("utf-8"),
        )
        msg_invalida = SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=b"{json-quebrado",
        )

        mock_client.on_message(mock_client, None, msg_bomba)
        mock_client.on_message(mock_client, None, msg_exaustor)
        mock_client.on_message(mock_client, None, msg_invalida)

        assert sim.bomba_ligada is True
        assert sim.exaustor_ligado is True

        msg_desliga = SimpleNamespace(
            topic=config.TOPIC_STATUS_BOMBA,
            payload=json.dumps({"atuador": "bomba", "ligado": False}).encode("utf-8"),
        )
        mock_client.on_message(mock_client, None, msg_desliga)
        assert sim.bomba_ligada is False
        assert sim.exaustor_ligado is True


class TestIntegracaoMalhaFechadaBroker:
    def test_sensor_recebe_status_bomba_via_mqtt_e_eleva_umidade(self, monkeypatch):
        """Verifica de ponta a ponta o sensor recebendo status=True e invertendo a curva de umidade."""
        broker = BrokerMQTTLocal(host="127.0.0.1", port=0, silencioso=True)
        porta = broker.iniciar_em_background()

        monkeypatch.setattr(config, "MQTT_HOST", "127.0.0.1")
        monkeypatch.setattr(config, "MQTT_PORT", porta)

        umidades_recebidas = []
        evento_primeira_leitura = threading.Event()

        observador = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="obs_sensor_test")

        def obs_on_connect(cli, userdata, flags, reason_code, properties):
            if reason_code == 0:
                cli.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)

        def obs_on_message(cli, userdata, msg):
            dado = json.loads(msg.payload.decode("utf-8"))
            umidades_recebidas.append(dado["valor"])
            if len(umidades_recebidas) == 1:
                evento_primeira_leitura.set()

        observador.on_connect = obs_on_connect
        observador.on_message = obs_on_message
        observador.connect("127.0.0.1", porta, 60)
        observador.loop_start()
        time.sleep(0.15)

        try:
            thread_sensor = threading.Thread(
                target=executar_sensor,
                kwargs={"intervalo": 0.2, "perfil": "seco", "max_iteracoes": 4},
                daemon=True,
            )
            thread_sensor.start()

            assert evento_primeira_leitura.wait(timeout=3.0), "Sensor não publicou a 1ª leitura"

            # Simula o atuador confirmando que a bomba foi ligada
            pub_status = observador.publish(
                config.TOPIC_STATUS_BOMBA,
                json.dumps({"atuador": "bomba", "ligado": True, "timestamp": time.time()}),
                qos=1,
            )
            pub_status.wait_for_publish(timeout=2.0)

            thread_sensor.join(timeout=5.0)
            assert not thread_sensor.is_alive()
            time.sleep(0.15)

            assert len(umidades_recebidas) == 4
            # Como a bomba ligou logo após a 1ª leitura, as leituras finais devem ser maiores que a inicial
            assert umidades_recebidas[-1] > umidades_recebidas[0]
        finally:
            observador.loop_stop()
            observador.disconnect()
            broker.parar()
