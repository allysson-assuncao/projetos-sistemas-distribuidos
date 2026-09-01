"""
run_experiment.py — Orquestrador automatizado de todos os experimentos da AP3.

Executa cada cenário como subprocesso, aguarda a conclusão e consolida os logs.

Uso:
    python run_experiment.py
    python run_experiment.py --count 60 --interval 0.5
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Caminhos
SCRIPT_DIR = Path(__file__).parent
SRC_DIR    = SCRIPT_DIR.parent / "src"
RESULTS    = SCRIPT_DIR / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

PYTHON = sys.executable


def banner(msg: str):
    linha = "═" * 60
    print(f"\n{linha}")
    print(f"  {msg}")
    print(f"{linha}\n")


def run_scenario(scenario_name: str, pub_cmd: list, sub_cmds: list, duration: int):
    """
    Inicia os subscribers, aguarda 1s, inicia os publishers,
    aguarda o publisher terminar, e depois encerra os subscribers.
    """
    banner(f"CENÁRIO: {scenario_name}")
    procs = []

    # 1. Iniciar subscribers primeiro (para não perder mensagens iniciais)
    for cmd in sub_cmds:
        print(f"  [ORQ] Iniciando subscriber: {' '.join(cmd)}")
        p = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        procs.append(p)

    time.sleep(2)  # aguarda subscribers se conectarem

    # 2. Iniciar publisher
    print(f"  [ORQ] Iniciando publisher: {' '.join(pub_cmd)}")
    pub = subprocess.Popen(pub_cmd, stdout=sys.stdout, stderr=sys.stderr)

    # 3. Aguardar publisher terminar
    pub.wait()
    time.sleep(2)  # aguarda subscribers processarem as últimas mensagens

    # 4. Encerrar subscribers
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()

    print(f"  [ORQ] Cenário '{scenario_name}' concluído.\n")
    time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description="Orquestrador de Experimentos MQTT")
    parser.add_argument("--count",    type=int, default=60,
                        help="Número de mensagens por experimento (default: 60)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Intervalo entre publicações em segundos (default: 1.0)")
    args = parser.parse_args()

    count    = str(args.count)
    interval = str(args.interval)

    banner("INICIANDO BATERIA DE EXPERIMENTOS — AP3 MQTT Casa Inteligente")
    print(f"  Mensagens por cenário : {count}")
    print(f"  Intervalo             : {interval}s")
    print(f"  Resultados em         : {RESULTS}\n")

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 1: QoS 0 — Fire and Forget
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 0 (Fire and Forget)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "0", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "0",
             "--output", "sub_alarme_qos0.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "0", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 2: QoS 1 — At Least Once
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 1 (At Least Once)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "1", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "1",
             "--output", "sub_alarme_qos1.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "1", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 3: QoS 2 — Exactly Once
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Baseline QoS 2 (Exactly Once)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_temperatura.py"),
            "--qos", "2", "--count", count, "--interval", interval
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "2",
             "--output", "sub_alarme_qos2.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "2", "--timeout", "300"],
        ],
        duration = int(args.count * args.interval) + 15
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 4: Falha Controlada — LWT + Retained
    # ─────────────────────────────────────────────────────────────────────────
    run_scenario(
        scenario_name = "Falha Controlada: LWT + Retained (QoS 1)",
        pub_cmd = [
            PYTHON, str(SRC_DIR / "pub_porta.py"),
            "--qos", "1", "--count", count, "--interval", interval,
            "--simulate-crash"   # mata o processo na metade → LWT disparado
        ],
        sub_cmds = [
            [PYTHON, str(SRC_DIR / "sub_alarme.py"),    "--qos", "1",
             "--output", "sub_alarme_lwt.csv", "--timeout", "300"],
            [PYTHON, str(SRC_DIR / "sub_dashboard.py"), "--qos", "1",
             "--timeout", "300"],
        ],
        duration = int((args.count // 2) * args.interval) + 20
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CENÁRIO 5: Retained — Subscriber Tardio
    # (Demonstra que subscriber que conecta depois recebe o último estado)
    # ─────────────────────────────────────────────────────────────────────────
    banner("CENÁRIO: Retained — Subscriber Tardio (QoS 1)")
    print("  [ORQ] Publisher publicando estado retido da porta...")
    pub = subprocess.Popen([
        PYTHON, str(SRC_DIR / "pub_porta.py"),
        "--qos", "1", "--count", "5", "--interval", "0.5"
    ], stdout=sys.stdout, stderr=sys.stderr)
    pub.wait()

    print("  [ORQ] Aguardando 3s antes de conectar o subscriber tardio...")
    time.sleep(3)

    print("  [ORQ] Subscriber tardio conectando — deve receber estado retido imediatamente:")
    tardio = subprocess.Popen([
        PYTHON, str(SRC_DIR / "sub_dashboard.py"),
        "--qos", "1", "--timeout", "5"
    ], stdout=sys.stdout, stderr=sys.stderr)
    tardio.wait()
    print("  [ORQ] Cenário 'Retained' concluído.\n")

    banner("✅ TODOS OS EXPERIMENTOS CONCLUÍDOS")
    print(f"  CSVs disponíveis em: {RESULTS}")
    print(f"  Execute a análise  : python analysis/analyze.py\n")


if __name__ == "__main__":
    main()
