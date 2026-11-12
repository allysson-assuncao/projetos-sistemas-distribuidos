"""Validação End-to-End (Smoke Test Pré-Apresentação) do Trabalho Prático 1.

Sobe todos os serviços reais em subprocessos (Broker MQTT Local, Middleware XML-RPC,
3 Réplicas de Controlador e Atuador), executa automaticamente os cenários das
Etapas 2 a 7 do `roteiro_apresentacao.md` e limpa os arquivos `data_ctrl_*.json`
ao final para deixar o ambiente pronto para a demonstração ao vivo.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import List
import xmlrpc.client

import paho.mqtt.client as mqtt

RAIZ_TP1 = Path(__file__).resolve().parent.parent
if str(RAIZ_TP1) not in sys.path:
    sys.path.insert(0, str(RAIZ_TP1))

from estufa import config


class ProcessoMonitorado:
    """Subprocesso com captura assíncrona de stdout/stderr em memória."""

    def __init__(self, nome: str, args: List[str]):
        self.nome = nome
        self.linhas: List[str] = []
        self._lock = threading.Lock()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        self.proc = subprocess.Popen(
            [sys.executable, "-u"] + args,
            cwd=str(RAIZ_TP1),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._thread = threading.Thread(target=self._ler_saida, daemon=True)
        self._thread.start()

    def _ler_saida(self) -> None:
        assert self.proc.stdout is not None
        for linha in self.proc.stdout:
            texto = linha.rstrip("\r\n")
            with self._lock:
                self.linhas.append(texto)

    def obter_logs(self) -> str:
        with self._lock:
            return "\n".join(self.linhas)

    def aguardar_log(self, trecho: str, timeout: float = 5.0) -> bool:
        limite = time.time() + timeout
        while time.time() < limite:
            if trecho in self.obter_logs():
                return True
            time.sleep(0.1)
        return trecho in self.obter_logs()

    def parar(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _aguardar_porta(host: str, port: int, timeout: float = 5.0) -> bool:
    limite = time.time() + timeout
    while time.time() < limite:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def _limpar_arquivos_estado() -> None:
    for i in (1, 2, 3):
        arq = RAIZ_TP1 / f"data_ctrl_{i}.json"
        if arq.exists():
            try:
                arq.unlink()
            except OSError:
                pass


def executar_smoke_test_e2e() -> int:
    print("=" * 68)
    print(" VALIDAÇÃO END-TO-END (PRÉ-APRESENTAÇÃO) — ESTUFA DISTRIBUÍDA TP1")
    print("=" * 68)

    _limpar_arquivos_estado()
    processos: List[ProcessoMonitorado] = []

    def iniciar(nome: str, args: List[str]) -> ProcessoMonitorado:
        p = ProcessoMonitorado(nome, args)
        processos.append(p)
        return p

    try:
        # 1. Subir Broker, Middleware, 3 Controladores e Atuador
        print("\n[ETAPA 2] Iniciando Broker MQTT, Middleware, 3 Réplicas e Atuador...")
        iniciar("broker", ["-m", "estufa.broker_local", "--python-only"])
        assert _aguardar_porta("127.0.0.1", config.MQTT_PORT, 5.0), "Broker MQTT não abriu porta 1883"

        iniciar("middleware", ["-m", "estufa.middleware_server"])
        assert _aguardar_porta("127.0.0.1", config.MIDDLEWARE_PORT, 5.0), "Middleware não abriu porta 9000"

        ctrl_1 = iniciar(
            "ctrl_1",
            ["-m", "estufa.controlador", "--id", "ctrl_1", "--port", "8001", "--data", "data_ctrl_1.json", "--skip-sync"],
        )
        ctrl_2 = iniciar(
            "ctrl_2",
            ["-m", "estufa.controlador", "--id", "ctrl_2", "--port", "8002", "--data", "data_ctrl_2.json", "--skip-sync"],
        )
        ctrl_3 = iniciar(
            "ctrl_3",
            ["-m", "estufa.controlador", "--id", "ctrl_3", "--port", "8003", "--data", "data_ctrl_3.json", "--skip-sync"],
        )
        atuador = iniciar("atuador", ["-m", "estufa.atuador"])

        for porta in (8001, 8002, 8003):
            assert _aguardar_porta("127.0.0.1", porta, 5.0), f"Controlador na porta {porta} não iniciou"

        assert ctrl_1.aguardar_log("Assinando tópicos de sensores", 5.0), "ctrl_1 não assinou MQTT"
        assert ctrl_2.aguardar_log("Assinando tópicos de sensores", 5.0), "ctrl_2 não assinou MQTT"
        assert ctrl_3.aguardar_log("Assinando tópicos de sensores", 5.0), "ctrl_3 não assinou MQTT"
        assert atuador.aguardar_log("Assinando: estufa/atuadores/exaustor", 5.0), "atuador não assinou MQTT"
        time.sleep(0.3)

        mw = xmlrpc.client.ServerProxy(f"http://localhost:{config.MIDDLEWARE_PORT}", allow_none=True)
        saude = mw.verificar_saude()
        assert saude == {"ctrl_1": "ok", "ctrl_2": "ok", "ctrl_3": "ok"}, f"Saúde inesperada: {saude}"
        print("  -> [OK] Cluster 3/3 online e saudável via Middleware XML-RPC (:9000)")

        # 2. Etapa 3 — Acionamento Autônomo via MQTT + Deduplicação LRU
        print("\n[ETAPA 3] Testando acionamento autônomo MQTT (Umidade=18.5% < 30%) + Deduplicação LRU...")
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor_e2e")
        pub.connect("127.0.0.1", config.MQTT_PORT, 60)
        pub.loop_start()
        ts_evento = round(time.time(), 3)
        res = pub.publish(
            config.TOPIC_UMIDADE_SOLO,
            json.dumps({"valor": 18.5, "unidade": "%", "timestamp": ts_evento}),
            qos=1,
        )
        res.wait_for_publish(timeout=3.0)
        pub.loop_stop()
        pub.disconnect()

        assert atuador.aguardar_log("Bomba de irrigação -> LIGADA", 4.0), "Atuador não ligou a bomba"
        # Aguarda os 2 descartes das réplicas redundantes
        limite_dedup = time.time() + 4.0
        while time.time() < limite_dedup:
            if atuador.obter_logs().count("Comando duplicado descartado:") >= 2:
                break
            time.sleep(0.1)

        logs_atuador = atuador.obter_logs()
        qtd_ligada = logs_atuador.count("Bomba de irrigação -> LIGADA")
        qtd_descartada = logs_atuador.count("Comando duplicado descartado:")
        assert qtd_ligada == 1, f"Esperado 1 acionamento físico, ocorreu {qtd_ligada}"
        assert qtd_descartada == 2, f"Esperado 2 descartes LRU, ocorreu {qtd_descartada}"

        estado = mw.obter_estado()
        assert estado["bomba_ligada"] is True and estado["umidade_solo"] == 18.5
        print("  -> [OK] 3 réplicas detectaram umidade baixa, geraram mesmo MD5 e Atuador descartou 2 duplicatas!")

        # 3. Etapa 4 — Tolerância a Falha por Parada (Crash) — Quórum 2/3
        print("\n[ETAPA 4] Testando Tolerância a Falha por Parada (derrubando ctrl_3)...")
        ctrl_3.parar()
        time.sleep(0.3)
        saude_crash = mw.verificar_saude()
        assert saude_crash["ctrl_1"] == "ok" and saude_crash["ctrl_2"] == "ok"
        assert "OFFLINE" in saude_crash["ctrl_3"]

        resp_exaustor = mw.comandar_exaustor("ligar")
        assert resp_exaustor["sucesso"] is True and resp_exaustor["mensagem"] == "Exaustor ligado com sucesso"
        assert mw.obter_estado()["exaustor_ligado"] is True
        print("  -> [OK] Quórum 2/3 mantido com ctrl_3 OFFLINE; exaustor ligado via Middleware!")

        # 4. Etapa 5 — Recuperação de Falha (State Transfer via Middleware no Boot)
        print("\n[ETAPA 5] Testando Recuperação de Falha (reiniciando ctrl_3 sem estado local)...")
        arq_ctrl3 = RAIZ_TP1 / "data_ctrl_3.json"
        if arq_ctrl3.exists():
            arq_ctrl3.unlink()

        ctrl_3 = iniciar(
            "ctrl_3_rec",
            ["-m", "estufa.controlador", "--id", "ctrl_3", "--port", "8003", "--data", "data_ctrl_3.json"],
        )
        assert ctrl_3.aguardar_log("Estado sincronizado na tentativa", 5.0), "ctrl_3 não sincronizou via Middleware"
        proxy_c3 = xmlrpc.client.ServerProxy("http://localhost:8003", allow_none=True)
        estado_c3 = proxy_c3.obter_estado()
        assert estado_c3["bomba_ligada"] is True and estado_c3["exaustor_ligado"] is True
        print("  -> [OK] ctrl_3 sincronizou estado automaticamente no boot via Middleware (Bomba=ON, Exaustor=ON)!")

        # 5. Etapa 6 — Tolerância a Falha Bizantina (Votação Majoritária 2 x 1)
        print("\n[ETAPA 6] Testando Tolerância a Falha Bizantina (ctrl_2 com --byzantino)...")
        ctrl_2.parar()
        time.sleep(0.3)
        ctrl_2 = iniciar(
            "ctrl_2_byz",
            [
                "-m",
                "estufa.controlador",
                "--id",
                "ctrl_2",
                "--port",
                "8002",
                "--data",
                "data_ctrl_2.json",
                "--byzantino",
                "--skip-sync",
            ],
        )
        assert _aguardar_porta("127.0.0.1", 8002, 5.0), "ctrl_2 bizantino não subiu na porta 8002"
        proxy_c2 = xmlrpc.client.ServerProxy("http://localhost:8002", allow_none=True)
        estado_byz = proxy_c2.obter_estado()
        assert estado_byz["temperatura"] == 999.0 and estado_byz["umidade_solo"] == -1.0

        estado_consenso = mw.obter_estado()
        assert estado_consenso["umidade_solo"] == 18.5 and estado_consenso["bomba_ligada"] is True
        resp_bomba = mw.comandar_bomba("desligar")
        assert resp_bomba["sucesso"] is True and resp_bomba["mensagem"] == "Bomba desligada com sucesso"
        assert mw.obter_estado()["bomba_ligada"] is False
        print("  -> [OK] Voto bizantino de ctrl_2 (temp=999.0) mascarado pelo quórum honesto (ctrl_1 + ctrl_3)!")

        # 6. Etapa 7 — Perda de Quórum (2 Falhas Simultâneas: ctrl_2 Bizantino + ctrl_3 Parado)
        print("\n[ETAPA 7] Testando Perda de Quórum (f=2 falhas: ctrl_2 bizantino + ctrl_3 parado)...")
        ctrl_3.parar()
        time.sleep(0.3)
        quorum_falhou = False
        try:
            mw.obter_estado()
        except xmlrpc.client.Fault as fault:
            if "ERRO_QUORUM" in fault.faultString:
                quorum_falhou = True
        assert quorum_falhou, "Middleware deveria ter lançado ERRO_QUORUM com apenas 1 réplica honesta!"
        print("  -> [OK] Middleware recusou operação com segurança (ERRO_QUORUM) quando f=2!")

    except Exception:
        print("\n[DIAGNÓSTICO DE FALHA — LOGS DOS PROCESSOS]")
        for p in processos:
            print(f"--- Logs de {p.nome} ---")
            print(p.obter_logs() or "(vazio)")
        raise
    finally:
        print("\n[LIMPEZA] Encerrando processos de teste e limpando data_ctrl_*.json...")
        for p in reversed(processos):
            p.parar()
        time.sleep(0.3)
        _limpar_arquivos_estado()

    print("\n" + "=" * 68)
    print(" [SUCESSO TOTAL] Todos os cenários da apresentação foram validados!")
    print(" Ambiente limpo e pronto para abrir os terminais de demonstração.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(executar_smoke_test_e2e())
