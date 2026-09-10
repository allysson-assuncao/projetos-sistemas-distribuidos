# Walkthrough: Setup e Contrato gRPC (Prompt 1)

This walkthrough summarizes the actions taken to implement Phase 1 and Phase 2 of the final implementation plan for the `Atividade Prática 4`.

## 1. Directory Structure Setup

Created the foundational directories in the repository root:
- `carteira/`
- `tests/`
- `scripts/`
- `relatorio/`

## 2. Dependencies

Created the `requirements.txt` file with the required libraries:
- `grpcio==1.66.1`
- `grpcio-tools==1.66.1`
- `pytest==8.3.3`

Successfully ran `pip install -r requirements.txt` to install these dependencies into the local environment.

## 3. gRPC Contract

Created the Protocol Buffers definition file at [`carteira/carteira.proto`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/carteira/carteira.proto). This file contains the complete gRPC contract, defining the `CarteiraService` and the following 5 RPCs:
1. `CriarConta`
2. `ConsultarSaldo`
3. `Depositar`
4. `Sacar`
5. `Transferir`

## 4. Stub Generation Scripts

Created utility scripts for cross-platform stub generation:
- [`gerar_stubs.ps1`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/gerar_stubs.ps1) (Windows PowerShell)
- [`gerar_stubs.sh`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/gerar_stubs.sh) (Linux/Mac)

## 5. Executing Stub Generation

Ran the Windows stub generation script using `powershell -ExecutionPolicy Bypass -File .\gerar_stubs.ps1` (to bypass local execution policy restrictions).

The script successfully generated the Python stubs:
- [`carteira/carteira_pb2.py`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/carteira/carteira_pb2.py)
- [`carteira/carteira_pb2_grpc.py`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/carteira/carteira_pb2_grpc.py)

## 6. Package Resolution Fix

Created the [`carteira/__init__.py`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/carteira/__init__.py) file which injects the `carteira` directory into `sys.path`. This ensures that Python can correctly resolve the absolute imports generated inside the `grpc_tools.protoc` stubs when importing the package from outside.

Also created an empty [`tests/__init__.py`](file:///c:/Users/anybo/Documents/Projects/projetos-sistemas-distribuidos/atividade_pratica4/tests/__init__.py) to mark the `tests/` directory as a python package.

## 7. Core State Management (Store)

Created `carteira/store.py` which implements the `AccountStore` class. This file introduces a granular per-account locking strategy to prevent race conditions without introducing a global bottleneck:
- `_registry_lock`: A short-lived lock used only for dict key reads/writes.
- `account["lock"]`: A per-account mutex guaranteeing thread-safe operations on an individual account's balance (`saldo`).
- Transfers are executed in canonical order (sorting by `conta_id`) to inherently prevent deadlocks when transferring back and forth between two accounts simultaneously.

## 8. gRPC Server

Created `carteira/server.py` containing the `CarteiraServicer` which maps to the gRPC protocol definition.
- Exposes all 5 methods (`CriarConta`, `ConsultarSaldo`, `Depositar`, `Sacar`, `Transferir`).
- Validates inputs and returns explicit gRPC Status Codes (`INVALID_ARGUMENT`, `NOT_FOUND`, `ALREADY_EXISTS`, `FAILED_PRECONDITION`).
- Supports an artificial latency feature (`--delay`) to aid in deadline experiments.
- Boots a `ThreadPoolExecutor` allowing multiple concurrent client connections.

## 9. gRPC Client

Created `carteira/client.py` providing helper functions to interact with the service.
- Introduces configurable timeouts (deadlines) via a `timeout` parameter for all methods (defaulting to 5.0s).
- Implements error-handling blocks to cleanly capture and log `grpc.RpcError` exceptions.
- Includes a standalone interactive demo block when run directly as a script, executing both success and error cases.

## 10. Automated Tests

Created `tests/test_carteira.py` with 18 unit tests using `pytest` and `unittest.TestCase`.
- **Isolation**: Each test class instantiates a fresh `AccountStore` and gRPC server in its `setUpClass`, guaranteeing deterministic test isolation without shared state.
- **Ephemeral Ports**: Tests bind to `port=0`, letting the OS dynamically allocate ports. This eliminates port collisions, making the test suite parallelization-friendly.
- **Execution**: Ran `python -m pytest tests/test_carteira.py -v`. We encountered a slight issue on Windows with timer granularity on the deadline test, which was promptly fixed by explicitly injecting a `delay_seconds=0.5` in the test server. All 18 tests passed successfully!

## 11. Infrastructure & Experiments Setup

Created the helper scripts for Phase 6 experiments:
- `scripts/run_server.ps1`: A PowerShell wrapper to launch the server with specific arguments (`--port`, `--workers`, `--delay`).
- `scripts/run_experiments.py`: A comprehensive test runner that automates the 4 scenarios (Unavailability, Deadline, Concurrency, and Contract Evolution) and generates a formatted results table.

## 12. Experiments & Findings

Ran the automated experiment scripts via `run_experiments.py` directly measuring latency and observing gRPC behavior:
- **Experiment 1 (Unavailability)**: Confirmed the system emits `UNAVAILABLE` cleanly when the server is down, instead of hanging indefinitely. (Latency: 2300.4ms)
- **Experiment 2 (Deadline)**: Tested against a server with an artificial 3-second delay. Successfully validated that a 1s timeout properly triggers `DEADLINE_EXCEEDED` (at 1030.4ms), while a 5s timeout succeeds (`OK` at 3004.2ms).
- **Experiment 3 (Concurrency)**: Spawned 20 simultaneous deposit requests using a thread pool. Validated the granular locking mechanism, resulting in a perfect 20/20 `OK` success rate across all threads in 17.8ms total execution time (6.6ms avg latency).
- **Experiment 4 (Contract Evolution)**: Added a new `moeda` string field to `carteira.proto`, regenerated the stubs, and executed a transaction using the new client against the original server logic. Proved that protobufs are backward-compatible by ignoring unrecognized fields (`OK`, 4.7ms).

## 13. Final Report

Created the final comprehensive analysis in `relatorio/analise.md`, summarizing the measured values and discussing:
- The paradigm differences between gRPC, REST, and MQTT.
- Network volatility fallacies and why local calls != remote calls.
- `UNAVAILABLE` network errors vs. Application logic errors (`FAILED_PRECONDITION`).
- Mitigating the risks of duplicate transactions via *Idempotency Keys*.
- Schema coupling limits and non-backward-compatible Protobuf changes.

## Next Steps

All phases of the final implementation plan are now complete. The repository features a resilient gRPC Digital Wallet application, complete with granular concurrency controls, deterministic tests, latency experiments, and a thorough theoretical analysis.
