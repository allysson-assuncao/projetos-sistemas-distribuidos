"""
validate_e2e.py — Smoke Test End-to-End real da arquitetura distribuída (7 processos).

Valida em subprocessos reais sobre localhost:
  1. Cluster 3/3 ativo e eleição Bully inicial (ctrl_3 como líder).
  2. Malha fechada MQTT, consenso dinâmico e persistência idêntica em data_ctrl_1..3.json.
  3. Queda do líder ctrl_3 -> failover automático para ctrl_2 (2/2).
  4. Queda de ctrl_2 -> modo degradado 1/1 em ctrl_1.
  5. Reconexão de ctrl_2 e ctrl_3 -> sincronização automática dos bancos JSON e reeleição Bully.
  6. Mascaramento bizantino 2/3 (ctrl_2 --byzantino) e ErroQuorum em empate 1 honesto + 1 bizantino.
"""

import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import paho.mqtt.client as mqtt

ROOT_TP1 = Path(__file__).resolve().parent.parent
if str(ROOT_TP1) not in sys.path:
    sys.path.insert(0, str(ROOT_TP1))

from estufa import config
from estufa.middleware import ClusterMiddleware, ErroQuorum


def _porta_aberta(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def _aguardar(condicao, timeout: float = 10.0, descricao: str = "condição"):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            res = condicao()
            if res:
                return res
        except Exception:
            pass
        time.sleep(0.15)
    raise AssertionError(f"Timeout ({timeout}s) aguardando: {descricao}")


def _ler_json(ctrl_num: int) -> dict:
    caminho = ROOT_TP1 / f"data_ctrl_{ctrl_num}.json"
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _limpar_arquivos_estado() -> None:
    for arq in ROOT_TP1.glob("data_ctrl_*.json*"):
        arq.unlink()


def _iniciar_processo(modulo: str, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-u", "-m", modulo, *args],
        cwd=str(ROOT_TP1),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _parar_processo(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)


def main() -> int:
    inicio = time.monotonic()
    for porta in (config.MQTT_PORT, 8001, 8002, 8003):
        if _porta_aberta("127.0.0.1", porta):
            print(f"[ERRO] Porta {porta} já está em uso. Execute scripts/reset_demo.ps1 antes.")
            return 1

    _limpar_arquivos_estado()
    procs: dict[str, subprocess.Popen] = {}
    mw = ClusterMiddleware(timeout=3.5)
    mw_sonda = ClusterMiddleware(timeout=1.0)

    try:
        # Etapa 1: Subir Broker, 3 Controladores e Atuador
        print("[ETAPA 1] Subindo Broker MQTT, ctrl_1..3 e Atuador...")
        procs["broker"] = _iniciar_processo("estufa.broker_local")
        _aguardar(lambda: _porta_aberta("127.0.0.1", config.MQTT_PORT), 6.0, "Broker MQTT :1883")

        for i in (1, 2, 3):
            procs[f"ctrl_{i}"] = _iniciar_processo("estufa.controlador", str(i))
            _aguardar(lambda p=8000 + i: _porta_aberta("127.0.0.1", p), 6.0, f"ctrl_{i}")

        procs["atuador"] = _iniciar_processo("estufa.atuador")

        def _cluster_3_pronto():
            s = mw_sonda.verificar_saude()
            return s if s["ativos"] == 3 and s["lider_id"] == "ctrl_3" else None

        saude = _aguardar(_cluster_3_pronto, 10.0, "3/3 controladores ativos com ctrl_3 líder")
        print(f"  [OK] Saúde inicial: {saude['ativos']}/3 ativos | Líder={saude['lider_id']}")
        # Aguarda clientes MQTT (ctrl_1..3 e atuador) concluírem handshake e SUBSCRIBE no broker
        time.sleep(2.5)

        # Etapa 2: Publicação MQTT em malha fechada + consenso + commit idêntico nos 3 JSONs
        print("[ETAPA 2] Testando telemetria MQTT, consenso e persistência replicada...")
        status_recebidos: dict[str, bool] = {}
        ev_status = threading.Event()
        ev_conectado = threading.Event()
        subs_ok = {"n": 0}
        ev_inscrito = threading.Event()
        cli_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e_probe")

        def on_connect(c, u, f, rc, props):
            if rc == 0:
                ev_conectado.set()
                c.subscribe(config.TOPIC_STATUS_BOMBA, qos=1)
                c.subscribe(config.TOPIC_STATUS_EXAUSTOR, qos=1)

        def on_subscribe(c, u, mid, rc_list, props):
            subs_ok["n"] += 1
            if subs_ok["n"] >= 2:
                ev_inscrito.set()

        def on_msg(c, u, msg):
            dado = json.loads(msg.payload.decode("utf-8"))
            status_recebidos[dado["atuador"]] = dado["ligado"]
            if len(status_recebidos) >= 2:
                ev_status.set()

        cli_mqtt.on_connect = on_connect
        cli_mqtt.on_subscribe = on_subscribe
        cli_mqtt.on_message = on_msg
        cli_mqtt.connect("127.0.0.1", config.MQTT_PORT, 60)
        cli_mqtt.loop_start()
        assert ev_conectado.wait(timeout=4.0), "Probe MQTT não conectou ao broker"
        assert ev_inscrito.wait(timeout=4.0), "Probe MQTT não confirmou inscrições"

        try:
            cli_mqtt.publish(
                config.TOPIC_UMIDADE_SOLO,
                json.dumps({"valor": 20.0, "unidade": "%", "timestamp": time.time()}),
                qos=1,
            ).wait_for_publish(timeout=3.0)
            cli_mqtt.publish(
                config.TOPIC_TEMPERATURA,
                json.dumps({"valor": 38.0, "unidade": "°C", "timestamp": time.time()}),
                qos=1,
            ).wait_for_publish(timeout=3.0)
            assert ev_status.wait(timeout=10.0), "Atuador não publicou status da bomba/exaustor"
        finally:
            cli_mqtt.loop_stop()
            cli_mqtt.disconnect()

        def _estado_atuadores_ligados():
            e = mw.obter_estado()
            return e if e.get("bomba_ligada") and e.get("exaustor_ligado") else None

        estado = _aguardar(_estado_atuadores_ligados, 6.0, "estado consolidado com bomba e exaustor ligados")
        d1, d2, d3 = _ler_json(1), _ler_json(2), _ler_json(3)
        assert d1 == d2 == d3, f"Divergência entre bancos locais: {d1} vs {d2} vs {d3}"
        assert d1["lider_id"] == "ctrl_3"
        print(f"  [OK] Consenso + DBs idênticos (temp={estado['temperatura']}, umid={estado['umidade']})")

        # Etapa 3: Queda de ctrl_3 -> failover para ctrl_2 (2/2)
        print("[ETAPA 3] Encerrando líder ctrl_3 -> failover automático para ctrl_2...")
        _parar_processo(procs.pop("ctrl_3"))
        _aguardar(
            lambda: mw_sonda.verificar_saude()["lider_id"] == "ctrl_2",
            12.0,
            "ctrl_2 assumir liderança após queda de ctrl_3",
        )
        resp2 = mw.comandar_bomba(False)
        assert resp2["bomba_ligada"] is False
        assert _ler_json(1) == _ler_json(2)
        print("  [OK] Failover para ctrl_2 (2/2) e commit consistente em ctrl_1 e ctrl_2")

        # Etapa 4: Queda de ctrl_2 -> modo degradado 1/1 em ctrl_1
        print("[ETAPA 4] Encerrando ctrl_2 -> modo degradado 1/1 em ctrl_1...")
        _parar_processo(procs.pop("ctrl_2"))
        _aguardar(
            lambda: mw_sonda.verificar_saude()["lider_id"] == "ctrl_1",
            12.0,
            "ctrl_1 assumir liderança isolada (1/1)",
        )
        resp1 = mw.comandar_exaustor(False)
        assert resp1["exaustor_ligado"] is False
        assert _ler_json(1)["exaustor_ligado"] is False
        print("  [OK] Modo degradado 1/1 operacional em ctrl_1")

        # Etapa 5: Reconexão de ctrl_2 e ctrl_3 -> ressincronização automática dos bancos
        print("[ETAPA 5] Reiniciando ctrl_2 e ctrl_3 -> sincronização automática de réplicas...")
        procs["ctrl_2"] = _iniciar_processo("estufa.controlador", "2")
        _aguardar(lambda: _porta_aberta("127.0.0.1", 8002), 6.0, "ctrl_2 reconectar")
        procs["ctrl_3"] = _iniciar_processo("estufa.controlador", "3")
        _aguardar(lambda: _porta_aberta("127.0.0.1", 8003), 6.0, "ctrl_3 reconectar")

        _aguardar(_cluster_3_pronto, 10.0, "ctrl_3 reassumir liderança Bully após reconexão")
        _aguardar(lambda: _ler_json(1) == _ler_json(2) == _ler_json(3), 4.0, "réplicas convergirem JSON")
        d3 = _ler_json(3)
        assert d3["bomba_ligada"] is False and d3["exaustor_ligado"] is False
        print("  [OK] Réplicas ressincronizadas e liderança devolvida a ctrl_3")

        # Etapa 6: Mascaramento bizantino (2/3) e ErroQuorum em conflito 1 honesto vs 1 bizantino
        print("[ETAPA 6] Reiniciando ctrl_2 em --byzantino e validando tolerância a falhas...")
        _parar_processo(procs.pop("ctrl_2"))
        procs["ctrl_2"] = _iniciar_processo("estufa.controlador", "2", "--byzantino")
        _aguardar(
            lambda: mw_sonda.verificar_saude()["ativos"] == 3,
            10.0,
            "ctrl_2 --byzantino subir",
        )

        mw.verificar_saude()
        resp_byz = mw.comandar_bomba(True)
        assert resp_byz["bomba_ligada"] is True
        est_byz = mw.obter_estado()
        assert est_byz["bomba_ligada"] is True and est_byz["temperatura"] == 38.0
        _aguardar(lambda: _ler_json(1) == _ler_json(3), 4.0, "convergência JSON honestos")
        print("  [OK] Nó bizantino mascarado pela maioria 2/3 sem corromper bancos honestos")

        _parar_processo(procs.pop("ctrl_1"))
        _aguardar(lambda: mw_sonda.verificar_saude()["ativos"] == 2, 10.0, "ctrl_1 parar")
        try:
            mw.obter_estado()
            raise AssertionError("Esperado ErroQuorum com 1 honesto e 1 bizantino ativos")
        except ErroQuorum:
            print("  [OK] ErroQuorum detectado com segurança no empate 1 honesto vs 1 bizantino")

        duracao = time.monotonic() - inicio
        print(f"\n[SUCESSO TOTAL] Todas as 6 etapas E2E passaram em {duracao:.2f}s!")
        return 0

    finally:
        for p in procs.values():
            _parar_processo(p)
        _limpar_arquivos_estado()


if __name__ == "__main__":
    sys.exit(main())
