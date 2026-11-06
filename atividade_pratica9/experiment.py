import json
import math
import socket
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from server import StructuredLogger, start_background_server

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "logs" / "telemetry.jsonl"
METRICS_FILE = BASE_DIR / "results" / "metrics.json"

REQUESTS_PER_SCENARIO = 100
CONCURRENCY_WORKERS = 10
CLIENT_TIMEOUT_S = 0.200
SCENARIOS = ["nominal", "latency_spike", "intermittent_error"]


def percentile(sorted_values: List[float], p: float) -> float:
    """Calculates percentile (0..100) using linear interpolation."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    rank = (p / 100.0) * (len(sorted_values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return round(sorted_values[lower], 2)
    weight = rank - lower
    val = sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    return round(val, 2)


def deterministic_correlation_id(scenario: str, seq: int) -> str:
    """Generates a deterministic UUIDv5 per (scenario, seq) for reproducible log correlation."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"ap9-{scenario}-req-{seq:04d}"))


def execute_single_request(
    base_url: str,
    scenario: str,
    seq: int,
    logger: StructuredLogger,
) -> Dict[str, Any]:
    correlation_id = deterministic_correlation_id(scenario, seq)
    device_id = f"sensor-{seq % 10:02d}"
    payload = {
        "device_id": device_id,
        "seq": seq,
        "temperature_c": round(21.0 + (seq % 15) * 0.4, 2),
        "humidity_pct": round(45.0 + (seq % 20) * 1.1, 2),
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=f"{base_url}/api/v1/telemetry",
        data=data_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
            "X-Fault-Mode": scenario,
            "X-Request-Seq": str(seq),
        },
    )

    start_perf = time.perf_counter()
    http_status = None
    outcome = "UNKNOWN"
    error_detail = None

    try:
        with urllib.request.urlopen(req, timeout=CLIENT_TIMEOUT_S) as resp:
            _ = resp.read()
            http_status = resp.status
            outcome = "SUCCESS" if http_status == 200 else "HTTP_ERROR"
    except urllib.error.HTTPError as e:
        try:
            _ = e.read()
        except Exception:
            pass
        http_status = e.code
        outcome = "HTTP_ERROR"
        error_detail = f"HTTPError {e.code}"
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(e).lower():
            outcome = "TIMEOUT"
            error_detail = f"ClientTimeout > {int(CLIENT_TIMEOUT_S * 1000)}ms"
        else:
            outcome = "NETWORK_ERROR"
            error_detail = str(reason)

    duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)

    record = {
        "component": "client",
        "scenario": scenario,
        "correlation_id": correlation_id,
        "request_seq": seq,
        "device_id": device_id,
        "operation": "POST /api/v1/telemetry",
        "duration_ms": duration_ms,
        "http_status": http_status,
        "outcome": outcome,
        "error_detail": error_detail,
    }
    logger.log(record)
    return record


def run_scenario(base_url: str, scenario: str, logger: StructuredLogger) -> Dict[str, Any]:
    start_wall = time.perf_counter()
    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY_WORKERS) as executor:
        futures = [
            executor.submit(execute_single_request, base_url, scenario, seq, logger)
            for seq in range(REQUESTS_PER_SCENARIO)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    wall_time_s = time.perf_counter() - start_wall
    # Allow any in-flight timed-out server handlers to finish logging before next scenario
    time.sleep(0.40)

    results.sort(key=lambda r: r["request_seq"])
    all_latencies = sorted(r["duration_ms"] for r in results)
    success_latencies = sorted(r["duration_ms"] for r in results if r["outcome"] == "SUCCESS")

    success_count = sum(1 for r in results if r["outcome"] == "SUCCESS")
    http_error_count = sum(1 for r in results if r["outcome"] == "HTTP_ERROR")
    timeout_count = sum(1 for r in results if r["outcome"] == "TIMEOUT")
    other_error_count = len(results) - success_count - http_error_count - timeout_count
    total_errors = http_error_count + timeout_count + other_error_count

    mean_ms = round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0

    return {
        "scenario": scenario,
        "total_requests": len(results),
        "concurrency": CONCURRENCY_WORKERS,
        "client_timeout_ms": int(CLIENT_TIMEOUT_S * 1000),
        "wall_time_s": round(wall_time_s, 3),
        "throughput_rps": round(len(results) / wall_time_s, 2) if wall_time_s > 0 else 0.0,
        "success_count": success_count,
        "error_count": total_errors,
        "http_503_count": http_error_count,
        "timeout_count": timeout_count,
        "error_rate_pct": round((total_errors / len(results)) * 100.0, 2),
        "latency_all_ms": {
            "min": round(all_latencies[0], 2) if all_latencies else 0.0,
            "mean": mean_ms,
            "p50": percentile(all_latencies, 50),
            "p95": percentile(all_latencies, 95),
            "p99": percentile(all_latencies, 99),
            "max": round(all_latencies[-1], 2) if all_latencies else 0.0,
        },
        "latency_success_only_ms": {
            "mean": round(sum(success_latencies) / len(success_latencies), 2) if success_latencies else 0.0,
            "p50": percentile(success_latencies, 50),
            "p95": percentile(success_latencies, 95),
            "p99": percentile(success_latencies, 99),
        },
    }


def print_markdown_summary(summary_list: List[Dict[str, Any]]) -> None:
    print("\n### Tabela Comparativa de Resultados Experimentais\n")
    print(
        "| Cenário | Req | Sucesso | HTTP 503 | Timeouts | Taxa de Erro (%) | Throughput (req/s) | Média (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) |"
    )
    print(
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    )
    for item in summary_list:
        lat = item["latency_all_ms"]
        print(
            f"| `{item['scenario']}` | {item['total_requests']} | {item['success_count']} | "
            f"{item['http_503_count']} | {item['timeout_count']} | {item['error_rate_pct']:.1f}% | "
            f"{item['throughput_rps']:.2f} | {lat['mean']:.2f} | {lat['p50']:.2f} | "
            f"{lat['p95']:.2f} | {lat['p99']:.2f} | {lat['max']:.2f} |"
        )
    print()


def main() -> None:
    logger = StructuredLogger(LOG_FILE)
    logger.reset()

    server, port = start_background_server(logger)
    base_url = f"http://127.0.0.1:{port}"
    print(f"[INFO] Servidor de telemetria iniciado em {base_url}")

    # Warm-up server socket
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2.0) as resp:
            pass
    except Exception as e:
        print(f"[WARN] Warm-up warning: {e}")

    scenario_summaries: List[Dict[str, Any]] = []
    try:
        for scenario in SCENARIOS:
            print(f"[INFO] Executando cenário '{scenario}' ({REQUESTS_PER_SCENARIO} requisições, {CONCURRENCY_WORKERS} workers)...")
            summary = run_scenario(base_url, scenario, logger)
            scenario_summaries.append(summary)
    finally:
        server.shutdown()
        server.server_close()

    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    output_payload = {
        "experiment": "AP9 - Observability, Metrics & Fault Injection",
        "parameters": {
            "requests_per_scenario": REQUESTS_PER_SCENARIO,
            "concurrency_workers": CONCURRENCY_WORKERS,
            "client_timeout_ms": int(CLIENT_TIMEOUT_S * 1000),
            "deterministic_seed_base": 42000,
        },
        "scenarios": scenario_summaries,
    }
    METRICS_FILE.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print_markdown_summary(scenario_summaries)
    print(f"[INFO] Logs estruturados gravados em: {LOG_FILE}")
    print(f"[INFO] Métricas consolidadas gravadas em: {METRICS_FILE}")


if __name__ == "__main__":
    main()
