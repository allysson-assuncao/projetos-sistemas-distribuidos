"""
analyze.py — Análise dos resultados dos experimentos MQTT.

Lê os CSVs gerados pelo run_experiment.py e produz:
    1. tabela_resultados.md — tabela comparativa em Markdown
    2. grafico_perdas.png   — gráfico de barras de mensagens recebidas vs enviadas
    3. grafico_taxa.png     — gráfico de linha de taxa de entrega

Uso:
    python analyze.py
    python analyze.py --results ../experiments/results --output ./output
"""

import argparse
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # backend sem GUI para Windows
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

# Configuração
SCENARIO_MAP = {
    "sub_alarme_qos0.csv": {"qos": 0, "semantica": "Fire and Forget",  "topico": "temperatura"},
    "sub_alarme_qos1.csv": {"qos": 1, "semantica": "At Least Once",    "topico": "temperatura"},
    "sub_alarme_qos2.csv": {"qos": 2, "semantica": "Exactly Once",     "topico": "temperatura"},
    "sub_alarme_lwt.csv":  {"qos": 1, "semantica": "Falha c/ LWT",     "topico": "porta"},
}


# Funções auxiliares
def load_csv(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path)
        return df
    except FileNotFoundError:
        print(f"  [ANALISE] ⚠️  Arquivo não encontrado: {path}")
        return None
    except pd.errors.EmptyDataError:
        print(f"  [ANALISE] ⚠️  Arquivo CSV está vazio: {path}")
        return None
    except Exception as e:
        print(f"  [ANALISE] Erro ao ler {path}: {e}")
        return None


def analisa_cenario(df: pd.DataFrame, qos: int, enviadas: int = 60) -> dict:
    """Calcula métricas de um cenário a partir do DataFrame do subscriber."""
    if df is None or df.empty:
        return {}

    recebidas  = len(df)
    duplicatas = recebidas - df["seq"].nunique() if "seq" in df.columns else 0
    lwt_events = len(df[df["observacao"] == "LWT_RECEBIDO"]) if "observacao" in df.columns else 0

    # Perdas estimadas via sequência
    if "seq" in df.columns:
        seqs_validos = df[df["seq"] >= 0]["seq"]
        if not seqs_validos.empty:
            seq_max = seqs_validos.max()
            perdas  = max(0, seq_max + 1 - len(seqs_validos.unique()))
        else:
            perdas = 0
    else:
        perdas = 0

    taxa_entrega = round((recebidas / max(enviadas, 1)) * 100, 1)

    return {
        "qos":          qos,
        "enviadas":     enviadas,
        "recebidas":    recebidas,
        "perdas":       perdas,
        "duplicatas":   duplicatas,
        "lwt_events":   lwt_events,
        "taxa_entrega": taxa_entrega,
    }


def gera_tabela_md(resultados: list[dict], output_path: Path):
    """Gera a tabela comparativa em Markdown."""
    linhas = [
        "# Tabela de Resultados — Experimentos MQTT Casa Inteligente\n",
        "| QoS | Semântica | Enviadas | Recebidas | Perdas | Duplicatas | Eventos LWT | Taxa de Entrega |",
        "|-----|-----------|----------|-----------|--------|------------|-------------|-----------------|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r.get('qos', '?')} "
            f"| {r.get('semantica', '?')} "
            f"| {r.get('enviadas', '?')} "
            f"| {r.get('recebidas', '?')} "
            f"| {r.get('perdas', '?')} "
            f"| {r.get('duplicatas', '?')} "
            f"| {r.get('lwt_events', '?')} "
            f"| {r.get('taxa_entrega', '?')}% |"
        )
    content = "\n".join(linhas) + "\n"
    output_path.write_text(content, encoding="utf-8")
    print(f"  [ANALISE] ✅ Tabela gerada: {output_path}")


def gera_grafico_perdas(resultados: list[dict], output_path: Path):
    """Gráfico de barras agrupado: Enviadas vs Recebidas por cenário."""
    labels    = [f"QoS {r['qos']}\n({r.get('semantica', '')})" for r in resultados]
    enviadas  = [r.get("enviadas", 0)  for r in resultados]
    recebidas = [r.get("recebidas", 0) for r in resultados]

    x     = range(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar([i - width/2 for i in x], enviadas,  width, label="Enviadas",  color="#4A90D9")
    bars2 = ax.bar([i + width/2 for i in x], recebidas, width, label="Recebidas", color="#5CB85C")

    ax.set_xlabel("Cenário", fontsize=12)
    ax.set_ylabel("Número de Mensagens", fontsize=12)
    ax.set_title("Comparação: Mensagens Enviadas vs Recebidas por Nível de QoS", fontsize=14)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend()
    ax.bar_label(bars1, padding=3)
    ax.bar_label(bars2, padding=3)
    ax.set_ylim(0, max(enviadas + recebidas) * 1.2 if enviadas else 10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  [ANALISE] ✅ Gráfico de perdas gerado: {output_path}")


def gera_grafico_taxa(resultados: list[dict], output_path: Path):
    """Gráfico de linha: Taxa de entrega (%) por nível de QoS."""
    labels = [f"QoS {r['qos']}" for r in resultados]
    taxas  = [r.get("taxa_entrega", 0) for r in resultados]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(labels, taxas, marker="o", linewidth=2, color="#E67E22", markersize=8)
    ax.fill_between(range(len(labels)), taxas, alpha=0.15, color="#E67E22")

    for i, (label, taxa) in enumerate(zip(labels, taxas)):
        ax.annotate(f"{taxa}%", (i, taxa), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=11, fontweight="bold")

    ax.set_ylim(0, 110)
    ax.set_xlabel("Nível de QoS", fontsize=12)
    ax.set_ylabel("Taxa de Entrega (%)", fontsize=12)
    ax.set_title("Taxa de Entrega de Mensagens por Nível de QoS", fontsize=14)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  [ANALISE] ✅ Gráfico de taxa gerado: {output_path}")


# Função principal
def main():
    parser = argparse.ArgumentParser(description="Análise dos resultados MQTT")
    parser.add_argument("--results", type=str,
                        default=str(Path(__file__).parent.parent / "experiments" / "results"))
    parser.add_argument("--output",  type=str,
                        default=str(Path(__file__).parent / "output"))
    parser.add_argument("--enviadas", type=int, default=60,
                        help="Número de mensagens enviadas por cenário (default: 60)")
    args = parser.parse_args()

    results_dir = Path(args.results)
    output_dir  = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n[ANALISE] Lendo resultados dos experimentos...")

    resultados = []
    for filename, meta in SCENARIO_MAP.items():
        csv_path = results_dir / filename
        df       = load_csv(csv_path)
        metricas = analisa_cenario(df, qos=meta["qos"], enviadas=args.enviadas)
        if metricas:
            metricas["semantica"] = meta["semantica"]
            metricas["topico"]    = meta["topico"]
            resultados.append(metricas)
            print(f"  [ANALISE] {filename}: {metricas['recebidas']} recebidas, "
                  f"{metricas['perdas']} perdas, {metricas['taxa_entrega']}% entregues")

    if not resultados:
        print("[ANALISE] ⚠️  Nenhum resultado encontrado. Execute run_experiment.py primeiro.")
        return

    # Gerar outputs
    gera_tabela_md(resultados, output_dir / "tabela_resultados.md")
    gera_grafico_perdas(resultados, output_dir / "grafico_perdas.png")
    gera_grafico_taxa(resultados,   output_dir / "grafico_taxa.png")

    print(f"\n[ANALISE] ✅ Análise completa. Outputs em: {output_dir}")


if __name__ == "__main__":
    main()
