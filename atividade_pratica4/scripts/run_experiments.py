"""
run_experiments.py — gRPC Experiment Runner
Atividade Prática 4 — Distributed Systems

Runs the 4 required experiments and prints a results table.
The server must be running separately (see run_server.ps1).

Experiments:
  1. Unavailability  — server is stopped
  2. Deadline        — server has artificial delay
  3. Concurrency     — multiple simultaneous clients
  4. Contract Evolution — new field added to .proto
"""

import sys
import os
import time
import threading
import grpc

# Importing the carteira package triggers __init__.py → sys.path fix (Fix 1)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import carteira  # noqa: F401

import carteira_pb2
import carteira_pb2_grpc
from carteira.client import get_stub, consultar_saldo, depositar, sacar

HOST = "localhost"
PORT = 50051

# Utilities
results = []  # list of dicts for the final table


def register(experiment: str, method: str, status: str, latency_ms: float, details: str = ""):
    """Append a result row to the results list."""
    results.append({
        "experiment": experiment,
        "method":     method,
        "status":     status,
        "latency_ms": latency_ms,
        "details":    details,
    })


def measure_call(method_fn, *args, **kwargs):
    """Execute an RPC call and measure its latency. Returns (status_code, latency_ms)."""
    start = time.perf_counter()
    try:
        method_fn(*args, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        return "OK", latency_ms
    except grpc.RpcError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return exc.code().name, latency_ms


# Experiment 1 — Unavailability
def experiment_unavailability():
    """
    Connect to the server when it is NOT running and observe the error.

    MANUAL EXECUTION STEPS:
      1. Ensure NO server is running on port 50051.
      2. Run: python scripts/run_experiments.py --exp 1
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 1: Unavailability")
    print("=" * 60)
    print("Ensure the server is NOT running. Attempting to connect...\n")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        status, lat = measure_call(stub.ConsultarSaldo, carteira_pb2.ContaRequest(conta_id="001"), timeout=3.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("1-Unavailability", "ConsultarSaldo", status, round(lat, 1),
                 "Server stopped — expected UNAVAILABLE")

    print("\nExpected result: UNAVAILABLE")


# Experiment 2 — Deadline
def experiment_deadline():
    """
    Test deadline behavior against a slow server.

    MANUAL EXECUTION STEPS:
      1. Start server with 3-second delay:
         python carteira/server.py --delay 3
      2. Run: python scripts/run_experiments.py --exp 2
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 2: Deadline")
    print("=" * 60)
    print("Server must be running with --delay 3")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        print("\n[2a] Deposit with timeout=1s (server delay=3s):")
        status, lat = measure_call(stub.Depositar, carteira_pb2.TransacaoRequest(conta_id="001", valor=10.0), timeout=1.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("2-Deadline", "Depositar (timeout=1s)", status, round(lat, 1),
                 "Server delay=3s | expected DEADLINE_EXCEEDED")

        print("\n[2b] Deposit with timeout=5s (server delay=3s):")
        status, lat = measure_call(stub.Depositar, carteira_pb2.TransacaoRequest(conta_id="001", valor=10.0), timeout=5.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("2-Deadline", "Depositar (timeout=5s)", status, round(lat, 1),
                 "Server delay=3s | expected OK")


# Experiment 3 — Concurrency
def _concurrent_client_worker(client_id: int, thread_results: list):
    """Function executed by each concurrent client thread."""
    stub, channel = get_stub(HOST, PORT)
    with channel:
        start = time.perf_counter()
        try:
            req = carteira_pb2.TransacaoRequest(
                conta_id="001", valor=1.0, descricao=f"client-{client_id}"
            )
            stub.Depositar(req, timeout=5.0)
            lat = (time.perf_counter() - start) * 1000
            thread_results.append({"client": client_id, "status": "OK", "latency_ms": round(lat, 1)})
        except grpc.RpcError as exc:
            lat = (time.perf_counter() - start) * 1000
            thread_results.append({"client": client_id, "status": exc.code().name, "latency_ms": round(lat, 1)})


def experiment_concurrency(num_clients: int = 20):
    """
    Launch multiple simultaneous clients and verify that the server processes
    all requests correctly using per-account locking.

    MANUAL EXECUTION STEPS:
      1. Start server with increased workers:
         python carteira/server.py --workers 20
      2. Run: python scripts/run_experiments.py --exp 3
    """
    print("\n" + "=" * 60)
    print(f"EXPERIMENT 3: Concurrency ({num_clients} simultaneous clients)")
    print("=" * 60)

    thread_results = []
    threads = [
        threading.Thread(target=_concurrent_client_worker, args=(i + 1, thread_results))
        for i in range(num_clients)
    ]

    start_total = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total_time_ms = (time.perf_counter() - start_total) * 1000

    successes   = sum(1 for r in thread_results if r["status"] == "OK")
    failures    = num_clients - successes
    avg_latency = sum(r["latency_ms"] for r in thread_results) / len(thread_results)

    print(f"\n  Clients: {num_clients} | Successes: {successes} | Failures: {failures}")
    print(f"  Average latency: {avg_latency:.1f}ms | Total time: {total_time_ms:.1f}ms")

    for r in thread_results:
        print(f"    Client {r['client']:02d}: {r['status']} ({r['latency_ms']}ms)")

    register("3-Concurrency", f"Depositar x{num_clients}",
             f"{successes}/{num_clients} OK", round(avg_latency, 1),
             f"Total time: {total_time_ms:.1f}ms")


# Experiment 4 — Contract Evolution
def experiment_contract_evolution():
    """
    Demonstrate that adding a NEW field to .proto is backward-compatible.

    MANUAL EXECUTION STEPS:
      1. Add field 'moeda' to TransacaoRequest in carteira.proto:
         message TransacaoRequest {
           string conta_id  = 1;
           double valor     = 2;
           string descricao = 3;
           string moeda     = 4;  // NEW — contract evolution
         }
      2. Regenerate stubs: .\\gerar_stubs.ps1
      3. Run: python scripts/run_experiments.py --exp 4
    
    Expected: the old server (compiled without 'moeda') ignores the new field
    and continues operating normally — demonstrating Protobuf backward compatibility.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 4: Contract Evolution")
    print("=" * 60)
    print("Ensure 'moeda' field was added to .proto and stubs were regenerated.")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        try:
            req = carteira_pb2.TransacaoRequest(
                conta_id="001",
                valor=10.0,
                descricao="Evolution experiment",
                moeda="BRL",  # NEW FIELD
            )
            start = time.perf_counter()
            resp  = stub.Depositar(req, timeout=5.0)
            lat   = (time.perf_counter() - start) * 1000
            print(f"  Status: OK | Latency: {lat:.1f}ms")
            print(f"  Response: {resp.mensagem}")
            register("4-ContractEvolution", "Depositar (moeda field)", "OK",
                     round(lat, 1), "Field 'moeda' added — backward-compatible")
        except grpc.RpcError as exc:
            print(f"  ERROR [{exc.code().name}]: {exc.details()}")
        except TypeError as exc:
            print(f"  TYPE ERROR (field 'moeda' not yet in stubs): {exc}")
            print("  → Run gerar_stubs.ps1 after adding the field to .proto")


# Results table
def print_results_table():
    """Print the results table formatted for inclusion in the report."""
    print("\n" + "=" * 80)
    print("RESULTS TABLE — AP4 Digital Wallet gRPC")
    print("=" * 80)
    print(f"{'Experiment':<25} {'Method':<30} {'Status':<25} {'Lat.(ms)':<12} {'Details'}")
    print("-" * 130)
    for r in results:
        print(f"{r['experiment']:<25} {r['method']:<30} {r['status']:<25} {r['latency_ms']:<12} {r['details']}")
    print("=" * 130)


# Entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Experiments — Digital Wallet")
    parser.add_argument("--exp",     type=int, choices=[1, 2, 3, 4],
                        help="Experiment number (1-4). Omit to run all.")
    parser.add_argument("--clients", type=int, default=20,
                        help="Number of simultaneous clients for experiment 3 (default: 20)")
    args = parser.parse_args()

    if args.exp == 1 or args.exp is None:
        experiment_unavailability()
    if args.exp == 2 or args.exp is None:
        experiment_deadline()
    if args.exp == 3 or args.exp is None:
        experiment_concurrency(args.clients)
    if args.exp == 4 or args.exp is None:
        experiment_contract_evolution()

    if results:
        print_results_table()
