# AP4 — Final Implementation Plan: gRPC Digital Wallet Service
> **Language:** English (for agent consumption)  
> **Project root:** `c:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4\`  
> **Assignment:** Atividade Prática 4 — Sistemas Distribuídos

---

## Part 0 — Architectural Improvements (Pre-execution Analysis)

Before generating any file, three structural flaws from the previous plan were identified and resolved. Every code block in this document already incorporates the fixes.

---

### Fix 1 — Package Resolution Problem

**Root cause:** `grpc_tools.protoc` generates stub files (`carteira_pb2.py`, `carteira_pb2_grpc.py`) with *absolute* module imports (`import carteira_pb2`). When `server.py` or `client.py` lives inside the `carteira/` package and is imported from outside that directory (e.g., by `tests/` or `scripts/`), Python's module resolver cannot find `carteira_pb2` unless the `carteira/` directory itself is on `sys.path`.

**Solution adopted:** Inject the package's own directory into `sys.path` at the *top* of `carteira/__init__.py`, so that the fix applies automatically whenever the package is imported—regardless of the caller's working directory. `server.py` and `client.py` simply do `from carteira import ...`, which triggers `__init__.py` and resolves the stubs correctly.

```
# Resolution flow:
#   tests/test_carteira.py  →  import carteira  →  carteira/__init__.py injects sys.path
#   → `import carteira_pb2` now resolves from carteira/ directory
```

This avoids scattering `sys.path.insert(...)` hacks in every consumer file.

---

### Fix 2 — Concurrency Bottleneck (Global Lock)

**Root cause:** The previous plan used a single `contas_lock = threading.Lock()` that serialises access to the *entire* account dictionary. Under the `ThreadPoolExecutor` with 10+ workers, every concurrent RPC—even ones touching completely independent accounts—blocks at this one lock, negating the benefit of a thread pool.

**Solution adopted:** A two-level locking strategy:

1. **Registry lock (`_registry_lock`):** A short-lived `threading.Lock` that guards only the dictionary itself (reads/writes of keys). Held only for the instant needed to look up or insert an account entry.
2. **Per-account lock (`account["lock"]`):** A `threading.Lock` stored *inside* each account entry. Guards the account's mutable state (`saldo`). Two threads operating on different accounts never contend.

For `Transferir`, locks are always acquired in a **deterministic canonical order** (sorted by `conta_id`) to prevent deadlock when two threads swap the same pair of accounts simultaneously.

---

### Fix 3 — Test Determinism

**Root cause:** The previous test strategy had three compounding problems:
1. `time.sleep(0.3)` is a fragile heuristic—it can still race on a loaded CI machine.
2. A single hardcoded `PORT = 50099` caused collision when multiple test classes each called `setUpClass` before any called `tearDownClass`.
3. Shared mutable global state (`contas` dict) between test classes meant one class's tests silently affected another's.

**Solution adopted:**
1. **OS-assigned port:** Each test class binds to `port=0` and retrieves the actual ephemeral port assigned by the OS via `server.add_insecure_port("[::]:0")` → `server.port`. This guarantees no port collision even under parallel test runners.
2. **gRPC channel readiness check:** Replace `time.sleep` with `grpc.channel_ready_future(channel).result(timeout=5)`, a deterministic readiness barrier.
3. **Isolated in-memory state per class:** Each `setUpClass` instantiates a *new, independent* `AccountStore` object passed to the servicer, so test classes never share state.

---

## Part 1 — File Layout

```
atividade_pratica4/
├── Atividade Prática 4 - SD.pdf        (existing — do not modify)
├── requirements.txt                    (PHASE 1)
├── gerar_stubs.ps1                     (PHASE 2 — Windows)
├── gerar_stubs.sh                      (PHASE 2 — Linux/Mac)
├── carteira/
│   ├── __init__.py                     (PHASE 2 — sys.path fix lives here)
│   ├── carteira.proto                  (PHASE 1 — gRPC contract)
│   ├── carteira_pb2.py                 (PHASE 2 — auto-generated, do not edit)
│   ├── carteira_pb2_grpc.py            (PHASE 2 — auto-generated, do not edit)
│   ├── store.py                        (PHASE 3 — AccountStore with granular locks)
│   ├── server.py                       (PHASE 3 — gRPC servicer + server bootstrap)
│   └── client.py                       (PHASE 4 — gRPC client functions)
├── tests/
│   ├── __init__.py                     (empty)
│   └── test_carteira.py                (PHASE 5 — deterministic pytest suite)
├── scripts/
│   ├── run_server.ps1                  (PHASE 6)
│   └── run_experiments.py              (PHASE 6 — 4 experiments)
└── relatorio/
    └── analise.md                      (PHASE 7 — report with answers)
```

---

## Phase 1 — Dependencies & Proto Contract

### Step 1.1 — `requirements.txt`

**File:** `atividade_pratica4/requirements.txt`

```
grpcio==1.66.1
grpcio-tools==1.66.1
pytest==8.3.3
```

> **Install command:**
> ```powershell
> cd c:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4
> pip install -r requirements.txt
> ```

### Step 1.2 — Create directory structure

```powershell
New-Item -ItemType Directory -Force -Path carteira, tests, scripts, relatorio
```

### Step 1.3 — `carteira/carteira.proto`

**File:** `atividade_pratica4/carteira/carteira.proto`

```proto
syntax = "proto3";

package carteira;

// ─────────────────────────────────────────────
// Request Messages
// ─────────────────────────────────────────────

// Used to identify an account (balance query)
message ContaRequest {
  string conta_id = 1;
}

// Used for deposit and withdrawal operations
message TransacaoRequest {
  string conta_id  = 1;
  double valor     = 2;
  string descricao = 3;  // optional descriptive field
}

// Used to create a new account
message CriarContaRequest {
  string conta_id      = 1;
  string nome_titular  = 2;
  double saldo_inicial = 3;
}

// Used for account-to-account transfers
message TransferirRequest {
  string conta_origem  = 1;
  string conta_destino = 2;
  double valor         = 3;
}

// ─────────────────────────────────────────────
// Response Messages
// ─────────────────────────────────────────────

// Standard response for transaction and account-creation operations
message TransacaoResponse {
  string conta_id    = 1;
  double saldo_atual = 2;
  string mensagem    = 3;
}

// Response for balance queries
message SaldoResponse {
  string conta_id     = 1;
  string nome_titular = 2;
  double saldo_atual  = 3;
}

// ─────────────────────────────────────────────
// Service Definition
// ─────────────────────────────────────────────

service CarteiraService {
  // Creates a new account with an initial balance
  rpc CriarConta   (CriarContaRequest) returns (TransacaoResponse);

  // Queries the balance and data of an existing account
  rpc ConsultarSaldo (ContaRequest)    returns (SaldoResponse);

  // Deposits a value into an account
  rpc Depositar    (TransacaoRequest)  returns (TransacaoResponse);

  // Withdraws a value from an account
  rpc Sacar        (TransacaoRequest)  returns (TransacaoResponse);

  // Transfers a value between two accounts
  rpc Transferir   (TransferirRequest) returns (TransacaoResponse);
}
```

> **Summary:** 5 RPC methods, 6 message types — exceeds the minimum of 3 for each.

---

## Phase 2 — Stub Generation

### Step 2.1 — `gerar_stubs.ps1` (Windows PowerShell)

**File:** `atividade_pratica4/gerar_stubs.ps1`

```powershell
# Generates gRPC stubs from carteira.proto
# Run from the atividade_pratica4/ directory
# Pre-requisite: pip install -r requirements.txt

Write-Host "Generating gRPC stubs for carteira.proto..." -ForegroundColor Cyan

python -m grpc_tools.protoc `
  --proto_path=carteira `
  --python_out=carteira `
  --grpc_python_out=carteira `
  carteira/carteira.proto

if ($LASTEXITCODE -eq 0) {
    Write-Host "Stubs generated successfully in carteira/!" -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2.py"      -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2_grpc.py" -ForegroundColor Green
} else {
    Write-Host "Error generating stubs. Check .proto and dependencies." -ForegroundColor Red
}
```

### Step 2.2 — `gerar_stubs.sh` (Linux/Mac)

**File:** `atividade_pratica4/gerar_stubs.sh`

```bash
#!/bin/bash
# Run from the atividade_pratica4/ directory

echo "Generating gRPC stubs for carteira.proto..."

python -m grpc_tools.protoc \
  --proto_path=carteira \
  --python_out=carteira \
  --grpc_python_out=carteira \
  carteira/carteira.proto

echo "Stubs generated in carteira/"
```

### Step 2.3 — Run stub generation

```powershell
# From atividade_pratica4/
.\gerar_stubs.ps1
```

> **IMPORTANT:** `carteira_pb2.py` and `carteira_pb2_grpc.py` are auto-generated. **Do not edit them manually.** Verify they exist in `carteira/` after running the script.

### Step 2.4 — `carteira/__init__.py`  ← FIX 1 LIVES HERE

**File:** `atividade_pratica4/carteira/__init__.py`

```python
"""
carteira package — gRPC Digital Wallet
Atividade Prática 4 — Distributed Systems

IMPORTANT — Package Resolution Fix:
  grpc_tools.protoc generates stub files (carteira_pb2.py, carteira_pb2_grpc.py)
  with absolute-style imports (`import carteira_pb2`). Those imports only resolve
  if the carteira/ directory itself is on sys.path.

  By injecting it here, in __init__.py, the fix applies automatically whenever
  anyone does `import carteira` or `from carteira import ...`, regardless of the
  caller's working directory (tests/, scripts/, or direct invocation).
"""

import sys
import os

# Ensure this package directory is on sys.path so protoc-generated stubs resolve
_package_dir = os.path.dirname(os.path.abspath(__file__))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)
```

### Step 2.5 — `tests/__init__.py`

**File:** `atividade_pratica4/tests/__init__.py`

```python
# Empty — marks tests/ as a Python package
```

---

## Phase 3 — Server Implementation

### Step 3.1 — `carteira/store.py` ← FIX 2 LIVES HERE

**File:** `atividade_pratica4/carteira/store.py`

This module encapsulates all account state and implements the granular per-account locking strategy, completely decoupled from the gRPC layer.

```python
"""
store.py — In-memory Account Store with Granular Locking
Atividade Prática 4 — Distributed Systems

Locking strategy (Fix 2):
  _registry_lock  : Short-lived lock — guards dict key reads/writes only.
                    Held for microseconds; never held during balance mutation.
  account["lock"] : Per-account lock — guards mutable state (saldo) of one
                    specific account. Two threads on different accounts never
                    contend. Two threads on the same account are serialised.

  Transferir deadlock prevention:
    Locks are always acquired in sorted(conta_id) canonical order, so a pair
    (A→B) and its reverse (B→A) both lock A first, then B — eliminating the
    classic dining philosophers cycle.
"""

import threading
from typing import Dict, Optional, Any


class AccountStore:
    """
    Thread-safe in-memory store for digital wallet accounts.

    Each account entry structure:
        {
            "nome_titular": str,
            "saldo": float,
            "lock": threading.Lock   # per-account mutex
        }
    """

    SEED_ACCOUNTS = [
        {"conta_id": "001", "nome_titular": "Alice Silva",  "saldo": 1000.00},
        {"conta_id": "002", "nome_titular": "Bruno Costa",  "saldo":  500.00},
        {"conta_id": "003", "nome_titular": "Carla Mendes", "saldo":  250.00},
    ]

    def __init__(self, seed: bool = True):
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._registry_lock = threading.Lock()
        if seed:
            self._seed()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _seed(self):
        """Populate the store with initial accounts."""
        for entry in self.SEED_ACCOUNTS:
            self._registry[entry["conta_id"]] = {
                "nome_titular": entry["nome_titular"],
                "saldo": entry["saldo"],
                "lock": threading.Lock(),
            }

    def _get_account(self, conta_id: str) -> Optional[Dict[str, Any]]:
        """Thread-safe read of an account entry. Returns None if not found."""
        with self._registry_lock:
            return self._registry.get(conta_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, conta_id: str, nome_titular: str, saldo_inicial: float) -> float:
        """
        Create a new account.

        Returns the initial balance on success.
        Raises KeyError if conta_id already exists.
        """
        with self._registry_lock:
            if conta_id in self._registry:
                raise KeyError(f"Account '{conta_id}' already exists.")
            self._registry[conta_id] = {
                "nome_titular": nome_titular,
                "saldo": saldo_inicial,
                "lock": threading.Lock(),
            }
            return saldo_inicial

    def query(self, conta_id: str) -> Dict[str, Any]:
        """
        Return a snapshot of account data.

        Returns dict with keys: conta_id, nome_titular, saldo_atual.
        Raises LookupError if conta_id not found.
        """
        account = self._get_account(conta_id)
        if account is None:
            raise LookupError(f"Account '{conta_id}' not found.")
        with account["lock"]:
            return {
                "conta_id": conta_id,
                "nome_titular": account["nome_titular"],
                "saldo_atual": account["saldo"],
            }

    def deposit(self, conta_id: str, valor: float) -> float:
        """
        Add valor to account balance.

        Returns new balance.
        Raises LookupError if conta_id not found.
        Raises ValueError if valor <= 0.
        """
        if valor <= 0:
            raise ValueError(f"Deposit amount must be positive. Got: {valor}")
        account = self._get_account(conta_id)
        if account is None:
            raise LookupError(f"Account '{conta_id}' not found.")
        with account["lock"]:
            account["saldo"] += valor
            return account["saldo"]

    def withdraw(self, conta_id: str, valor: float) -> float:
        """
        Subtract valor from account balance.

        Returns new balance.
        Raises LookupError if conta_id not found.
        Raises ValueError if valor <= 0.
        Raises ArithmeticError if insufficient funds.
        """
        if valor <= 0:
            raise ValueError(f"Withdrawal amount must be positive. Got: {valor}")
        account = self._get_account(conta_id)
        if account is None:
            raise LookupError(f"Account '{conta_id}' not found.")
        with account["lock"]:
            if account["saldo"] < valor:
                raise ArithmeticError(
                    f"Insufficient funds in '{conta_id}'. "
                    f"Balance: {account['saldo']:.2f}, requested: {valor:.2f}"
                )
            account["saldo"] -= valor
            return account["saldo"]

    def transfer(self, conta_origem: str, conta_destino: str, valor: float) -> float:
        """
        Atomically move valor from conta_origem to conta_destino.

        Returns new balance of conta_origem.
        Raises LookupError if either account not found.
        Raises ValueError if valor <= 0 or accounts are identical.
        Raises ArithmeticError if insufficient funds in conta_origem.

        Deadlock prevention: locks are acquired in sorted(conta_id) order.
        """
        if valor <= 0:
            raise ValueError(f"Transfer amount must be positive. Got: {valor}")
        if conta_origem == conta_destino:
            raise ValueError("Source and destination accounts must differ.")

        # Registry lookups — short critical section
        with self._registry_lock:
            origin = self._registry.get(conta_origem)
            dest   = self._registry.get(conta_destino)

        if origin is None:
            raise LookupError(f"Source account '{conta_origem}' not found.")
        if dest is None:
            raise LookupError(f"Destination account '{conta_destino}' not found.")

        # Acquire per-account locks in canonical order (deadlock-free)
        first_id, second_id = sorted([conta_origem, conta_destino])
        first  = origin if first_id == conta_origem else dest
        second = dest   if first_id == conta_origem else origin

        with first["lock"], second["lock"]:
            if origin["saldo"] < valor:
                raise ArithmeticError(
                    f"Insufficient funds in '{conta_origem}'. "
                    f"Balance: {origin['saldo']:.2f}, requested: {valor:.2f}"
                )
            origin["saldo"] -= valor
            dest["saldo"]   += valor
            return origin["saldo"]

    def known_accounts(self):
        """Return a list of known account IDs (for diagnostics/logging)."""
        with self._registry_lock:
            return list(self._registry.keys())
```

### Step 3.2 — `carteira/server.py`

**File:** `atividade_pratica4/carteira/server.py`

```python
"""
server.py — gRPC Server: Digital Wallet Service
Atividade Prática 4 — Distributed Systems

Features:
  - In-memory storage via AccountStore (granular per-account locking)
  - Synchronous style with ThreadPoolExecutor
  - Validation using at least 4 distinct gRPC status codes:
      INVALID_ARGUMENT, NOT_FOUND, ALREADY_EXISTS, FAILED_PRECONDITION
  - Optional artificial delay for deadline experiments (--delay flag)
"""

import time
import grpc
from concurrent import futures

# Fix 1 — importing from the carteira package triggers __init__.py,
# which injects carteira/ into sys.path, making protoc stubs resolvable.
import carteira_pb2
import carteira_pb2_grpc
from store import AccountStore


# ─────────────────────────────────────────────────────────────────────────────
# Servicer Implementation
# ─────────────────────────────────────────────────────────────────────────────

class CarteiraServicer(carteira_pb2_grpc.CarteiraServiceServicer):
    """
    Implements all RPC methods defined in carteira.proto.

    gRPC status codes used:
      INVALID_ARGUMENT    → negative/zero values, empty required fields
      NOT_FOUND           → account does not exist
      ALREADY_EXISTS      → duplicate account creation
      FAILED_PRECONDITION → insufficient funds
    """

    def __init__(self, store: AccountStore, delay_seconds: float = 0.0):
        self._store = store
        self._delay_seconds = delay_seconds

    def _apply_delay(self):
        """Inject artificial latency for deadline experiments."""
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

    # ------------------------------------------------------------------
    # CriarConta
    # ------------------------------------------------------------------
    def CriarConta(self, request, context):
        conta_id      = request.conta_id.strip()
        nome_titular  = request.nome_titular.strip()
        saldo_inicial = request.saldo_inicial

        if not conta_id or not nome_titular:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_id and nome_titular are required and cannot be empty.",
            )

        if saldo_inicial < 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"saldo_inicial cannot be negative. Received: {saldo_inicial}",
            )

        try:
            saldo = self._store.create(conta_id, nome_titular, saldo_inicial)
        except KeyError as exc:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(exc))

        print(f"[CriarConta] conta={conta_id}, titular={nome_titular}, saldo_inicial={saldo_inicial:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=saldo,
            mensagem=f"Account '{conta_id}' successfully created for {nome_titular}.",
        )

    # ------------------------------------------------------------------
    # ConsultarSaldo
    # ------------------------------------------------------------------
    def ConsultarSaldo(self, request, context):
        conta_id = request.conta_id.strip()

        if not conta_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "conta_id is required.")

        try:
            data = self._store.query(conta_id)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        print(f"[ConsultarSaldo] conta={conta_id}, saldo={data['saldo_atual']:.2f}")
        return carteira_pb2.SaldoResponse(
            conta_id=data["conta_id"],
            nome_titular=data["nome_titular"],
            saldo_atual=data["saldo_atual"],
        )

    # ------------------------------------------------------------------
    # Depositar
    # ------------------------------------------------------------------
    def Depositar(self, request, context):
        self._apply_delay()

        conta_id = request.conta_id.strip()
        valor    = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Deposit amount must be positive. Received: {valor}",
            )

        try:
            novo_saldo = self._store.deposit(conta_id, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        print(f"[Depositar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Deposit of R$ {valor:.2f} completed successfully.",
        )

    # ------------------------------------------------------------------
    # Sacar
    # ------------------------------------------------------------------
    def Sacar(self, request, context):
        self._apply_delay()

        conta_id = request.conta_id.strip()
        valor    = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Withdrawal amount must be positive. Received: {valor}",
            )

        try:
            novo_saldo = self._store.withdraw(conta_id, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except ArithmeticError as exc:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))

        print(f"[Sacar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Withdrawal of R$ {valor:.2f} completed successfully.",
        )

    # ------------------------------------------------------------------
    # Transferir
    # ------------------------------------------------------------------
    def Transferir(self, request, context):
        self._apply_delay()

        origem  = request.conta_origem.strip()
        destino = request.conta_destino.strip()
        valor   = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Transfer amount must be positive. Received: {valor}",
            )

        if origem == destino:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_origem and conta_destino cannot be the same.",
            )

        try:
            novo_saldo_origem = self._store.transfer(origem, destino, valor)
        except LookupError as exc:
            context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except ArithmeticError as exc:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))

        print(f"[Transferir] {origem} -> {destino}, valor={valor:.2f}, novo_saldo_origem={novo_saldo_origem:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=origem,
            saldo_atual=novo_saldo_origem,
            mensagem=f"Transfer of R$ {valor:.2f} from '{origem}' to '{destino}' completed.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Server Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def serve(port: int = 50051, max_workers: int = 10, delay_seconds: float = 0.0):
    """
    Start the gRPC server.

    Args:
        port         : TCP port to listen on (default 50051).
        max_workers  : Thread pool size (concurrency experiment variable).
        delay_seconds: Artificial per-request delay (deadline experiment variable).
    """
    store = AccountStore(seed=True)
    servicer = CarteiraServicer(store=store, delay_seconds=delay_seconds)

    if delay_seconds > 0:
        print(f"[WARNING] Delay mode active: {delay_seconds}s per request on Depositar/Sacar/Transferir")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()

    print(f"[SERVER] Digital Wallet started on port {port} with {max_workers} worker(s).")
    print(f"[SERVER] Seeded accounts: {store.known_accounts()}")
    print("[SERVER] Press Ctrl+C to stop.")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down gracefully...")
        server.stop(grace=5)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Server — Digital Wallet")
    parser.add_argument("--port",    type=int,   default=50051, help="TCP port (default: 50051)")
    parser.add_argument("--workers", type=int,   default=10,    help="Thread pool size (default: 10)")
    parser.add_argument("--delay",   type=float, default=0.0,   help="Artificial delay per request in seconds (default: 0)")
    args = parser.parse_args()

    serve(port=args.port, max_workers=args.workers, delay_seconds=args.delay)
```

> **Execution note:** `server.py` lives inside `carteira/`. Run it from `atividade_pratica4/` as:
> ```powershell
> python -m carteira.server
> # or equivalently:
> python carteira/server.py
> ```

---

## Phase 4 — Client Implementation

**File:** `atividade_pratica4/carteira/client.py`

```python
"""
client.py — gRPC Client: Digital Wallet Service
Atividade Prática 4 — Distributed Systems

Features:
  - All calls use configurable deadlines (timeout parameter)
  - gRPC errors are caught and displayed with status code
  - Functions are importable by run_experiments.py

Import note: this file is inside the carteira/ package. When imported externally,
__init__.py ensures sys.path is set correctly for carteira_pb2 stubs.
"""

import grpc
import carteira_pb2
import carteira_pb2_grpc

DEFAULT_HOST    = "localhost"
DEFAULT_PORT    = 50051
DEFAULT_TIMEOUT = 5.0  # seconds — default deadline


def get_stub(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Create and return a CarteiraService stub and its underlying channel."""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub    = carteira_pb2_grpc.CarteiraServiceStub(channel)
    return stub, channel


def criar_conta(
    stub,
    conta_id: str,
    nome_titular: str,
    saldo_inicial: float,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the CriarConta RPC with deadline."""
    try:
        req  = carteira_pb2.CriarContaRequest(
            conta_id=conta_id,
            nome_titular=nome_titular,
            saldo_inicial=saldo_inicial,
        )
        resp = stub.CriarConta(req, timeout=timeout)
        print(f"[CriarConta] ✓ {resp.mensagem} | Balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[CriarConta] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def consultar_saldo(
    stub,
    conta_id: str,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the ConsultarSaldo RPC with deadline."""
    try:
        req  = carteira_pb2.ContaRequest(conta_id=conta_id)
        resp = stub.ConsultarSaldo(req, timeout=timeout)
        print(f"[ConsultarSaldo] ✓ Account: {resp.conta_id} | Holder: {resp.nome_titular} | Balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[ConsultarSaldo] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def depositar(
    stub,
    conta_id: str,
    valor: float,
    descricao: str = "",
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Depositar RPC with deadline."""
    try:
        req  = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Depositar(req, timeout=timeout)
        print(f"[Depositar] ✓ {resp.mensagem} | New balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Depositar] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def sacar(
    stub,
    conta_id: str,
    valor: float,
    descricao: str = "",
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Sacar RPC with deadline."""
    try:
        req  = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Sacar(req, timeout=timeout)
        print(f"[Sacar] ✓ {resp.mensagem} | New balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Sacar] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


def transferir(
    stub,
    conta_origem: str,
    conta_destino: str,
    valor: float,
    timeout: float = DEFAULT_TIMEOUT,
):
    """Call the Transferir RPC with deadline."""
    try:
        req  = carteira_pb2.TransferirRequest(
            conta_origem=conta_origem,
            conta_destino=conta_destino,
            valor=valor,
        )
        resp = stub.Transferir(req, timeout=timeout)
        print(f"[Transferir] ✓ {resp.mensagem} | Source balance: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as exc:
        print(f"[Transferir] ✗ ERROR [{exc.code().name}]: {exc.details()}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Interactive demo — run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Client — Digital Wallet")
    parser.add_argument("--host",    type=str,   default=DEFAULT_HOST,    help="Server host")
    parser.add_argument("--port",    type=int,   default=DEFAULT_PORT,    help="Server port")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Deadline in seconds")
    args = parser.parse_args()

    print(f"\n=== Digital Wallet Client | {args.host}:{args.port} | timeout={args.timeout}s ===\n")

    stub, channel = get_stub(args.host, args.port)

    with channel:
        print("─── Creating new account ───")
        criar_conta(stub, "099", "Diego Teste", 100.0, timeout=args.timeout)

        print("\n─── Querying initial balances ───")
        consultar_saldo(stub, "001", timeout=args.timeout)
        consultar_saldo(stub, "002", timeout=args.timeout)

        print("\n─── Deposit ───")
        depositar(stub, "001", 250.0, "Salary", timeout=args.timeout)

        print("\n─── Withdrawal ───")
        sacar(stub, "001", 100.0, "Rent", timeout=args.timeout)

        print("\n─── Transfer ───")
        transferir(stub, "001", "002", 50.0, timeout=args.timeout)

        print("\n─── Expected error cases ───")

        print("\n[Test] Query non-existent account (NOT_FOUND):")
        consultar_saldo(stub, "999", timeout=args.timeout)

        print("\n[Test] Deposit with negative value (INVALID_ARGUMENT):")
        depositar(stub, "001", -50.0, timeout=args.timeout)

        print("\n[Test] Withdrawal with insufficient funds (FAILED_PRECONDITION):")
        sacar(stub, "003", 99999.0, timeout=args.timeout)

        print("\n[Test] Create duplicate account (ALREADY_EXISTS):")
        criar_conta(stub, "001", "Alice Duplicate", 0.0, timeout=args.timeout)

    print("\n=== End of Demo ===\n")
```

---

## Phase 5 — Automated Tests (pytest)

**File:** `atividade_pratica4/tests/test_carteira.py`

```python
"""
test_carteira.py — Automated Tests: Digital Wallet gRPC Service
Atividade Prática 4 — Distributed Systems

Testing strategy (Fix 3 — deterministic isolation):
  1. OS-assigned ports (port=0): each test class gets an ephemeral port
     chosen by the OS, guaranteeing no collision even under parallel runners.
  2. Channel readiness barrier: grpc.channel_ready_future().result(timeout=5)
     replaces the fragile time.sleep(0.3) heuristic.
  3. Isolated AccountStore per class: each setUpClass creates a fresh store,
     so test classes never share or corrupt each other's account state.
  4. Graceful teardown: server.stop(grace=0) + channel.close() in tearDownClass.
"""

import sys
import os
import unittest

import grpc
from concurrent import futures

# Importing the carteira package triggers __init__.py → sys.path fix (Fix 1)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import carteira  # noqa: F401  — triggers __init__.py sys.path injection

import carteira_pb2
import carteira_pb2_grpc
from carteira.store import AccountStore
from carteira.server import CarteiraServicer


# ─────────────────────────────────────────────────────────────────────────────
# Base Fixture
# ─────────────────────────────────────────────────────────────────────────────

class GrpcTestCase(unittest.TestCase):
    """
    Base class that spins up an isolated gRPC server for each test class.

    Key decisions:
      - port=0  → OS assigns an ephemeral port; no hardcoded values
      - channel_ready_future → deterministic readiness (no sleep)
      - fresh AccountStore   → no shared state between test classes
    """

    server  = None
    stub    = None
    channel = None
    port    = None

    @classmethod
    def setUpClass(cls):
        # Independent store per test class — Fix 3
        store    = AccountStore(seed=True)
        servicer = CarteiraServicer(store=store, delay_seconds=0.0)

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(servicer, cls.server)

        # OS-assigned port — Fix 3
        cls.port = cls.server.add_insecure_port("[::]:0")
        cls.server.start()

        cls.channel = grpc.insecure_channel(f"localhost:{cls.port}")
        cls.stub    = carteira_pb2_grpc.CarteiraServiceStub(cls.channel)

        # Deterministic readiness check — Fix 3
        grpc.channel_ready_future(cls.channel).result(timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop(grace=0)


# ─────────────────────────────────────────────────────────────────────────────
# CriarConta Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCriarConta(GrpcTestCase):

    def test_criar_conta_success(self):
        """Should create account with initial balance and return TransacaoResponse."""
        resp = self.stub.CriarConta(
            carteira_pb2.CriarContaRequest(conta_id="T01", nome_titular="Test One", saldo_inicial=500.0),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "T01")
        self.assertAlmostEqual(resp.saldo_atual, 500.0)
        self.assertIn("T01", resp.mensagem)

    def test_criar_conta_duplicate_returns_already_exists(self):
        """Should return ALREADY_EXISTS when creating account with existing ID."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="001", nome_titular="Alice Dup", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.ALREADY_EXISTS)

    def test_criar_conta_negative_balance_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when initial balance is negative."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T99", nome_titular="Invalid", saldo_inicial=-100.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_criar_conta_empty_name_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when nome_titular is empty."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T98", nome_titular="", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# ConsultarSaldo Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultarSaldo(GrpcTestCase):

    def test_consultar_saldo_existing_account(self):
        """Should return SaldoResponse with correct data for an existing account."""
        resp = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "001")
        self.assertEqual(resp.nome_titular, "Alice Silva")
        self.assertAlmostEqual(resp.saldo_atual, 1000.0, places=2)

    def test_consultar_saldo_nonexistent_returns_not_found(self):
        """Should return NOT_FOUND for a non-existent account."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id="999"),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)

    def test_consultar_saldo_empty_id_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when conta_id is empty."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id=""),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Depositar Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDepositar(GrpcTestCase):

    def test_depositar_success(self):
        """Balance should increase by deposited amount."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="002"), timeout=5
        ).saldo_atual

        resp = self.stub.Depositar(
            carteira_pb2.TransacaoRequest(conta_id="002", valor=100.0, descricao="Test"),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes + 100.0, places=2)

    def test_depositar_negative_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for negative deposit."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_zero_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for zero deposit."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=0.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_nonexistent_account_returns_not_found(self):
        """Should return NOT_FOUND when depositing to non-existent account."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="999", valor=50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# Sacar Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSacar(GrpcTestCase):

    def test_sacar_success(self):
        """Balance should decrease by withdrawn amount."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"), timeout=5
        ).saldo_atual

        resp = self.stub.Sacar(
            carteira_pb2.TransacaoRequest(conta_id="001", valor=50.0),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes - 50.0, places=2)

    def test_sacar_insufficient_funds_returns_failed_precondition(self):
        """Should return FAILED_PRECONDITION when withdrawing more than available balance."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="003", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)

    def test_sacar_negative_value_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT for negative withdrawal."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Transferir Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTransferir(GrpcTestCase):

    def test_transferir_success(self):
        """Should debit source and credit destination atomically."""
        saldo_001 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="001"), timeout=5).saldo_atual
        saldo_002 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="002"), timeout=5).saldo_atual

        self.stub.Transferir(
            carteira_pb2.TransferirRequest(conta_origem="001", conta_destino="002", valor=30.0),
            timeout=5,
        )

        novo_saldo_001 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="001"), timeout=5).saldo_atual
        novo_saldo_002 = self.stub.ConsultarSaldo(carteira_pb2.ContaRequest(conta_id="002"), timeout=5).saldo_atual

        self.assertAlmostEqual(novo_saldo_001, saldo_001 - 30.0, places=2)
        self.assertAlmostEqual(novo_saldo_002, saldo_002 + 30.0, places=2)

    def test_transferir_same_account_returns_invalid_argument(self):
        """Should return INVALID_ARGUMENT when source equals destination."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="001", conta_destino="001", valor=10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_transferir_insufficient_funds_returns_failed_precondition(self):
        """Should return FAILED_PRECONDITION when source balance is insufficient."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="003", conta_destino="001", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)


# ─────────────────────────────────────────────────────────────────────────────
# Deadline Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadline(GrpcTestCase):
    """
    Tests client-side deadline enforcement.
    Does not require server-side delay — uses a near-zero timeout
    that cannot be satisfied even on a fast local connection.
    """

    def test_deadline_exceeded_with_near_zero_timeout(self):
        """Should return DEADLINE_EXCEEDED with 0.0001s timeout (0.1ms — effectively zero)."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id="001"),
                timeout=0.0001,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.DEADLINE_EXCEEDED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

> **Run tests:**
> ```powershell
> cd c:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4
> python -m pytest tests/test_carteira.py -v
> ```

---

## Phase 6 — Experiment Scripts

### Step 6.1 — `scripts/run_server.ps1`

**File:** `atividade_pratica4/scripts/run_server.ps1`

```powershell
# Starts the Digital Wallet gRPC server with configurable parameters.
# Run from the atividade_pratica4/ directory.

param(
    [int]$port    = 50051,
    [int]$workers = 10,
    [float]$delay = 0.0
)

$rootDir = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Digital Wallet Server..." -ForegroundColor Cyan
Write-Host "  Port    : $port"      -ForegroundColor Gray
Write-Host "  Workers : $workers"   -ForegroundColor Gray
Write-Host "  Delay   : ${delay}s"  -ForegroundColor Gray

python "$rootDir\carteira\server.py" --port $port --workers $workers --delay $delay
```

### Step 6.2 — `scripts/run_experiments.py`

**File:** `atividade_pratica4/scripts/run_experiments.py`

```python
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

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

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


def measure_call(stub, method_fn, *args, **kwargs):
    """Execute an RPC call and measure its latency. Returns (status_code, latency_ms)."""
    start = time.perf_counter()
    try:
        method_fn(stub, *args, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        return "OK", latency_ms
    except grpc.RpcError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return exc.code().name, latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 1 — Unavailability
# ─────────────────────────────────────────────────────────────────────────────

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
        status, lat = measure_call(stub, consultar_saldo, "001", timeout=3.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("1-Unavailability", "ConsultarSaldo", status, round(lat, 1),
                 "Server stopped — expected UNAVAILABLE")

    print("\nExpected result: UNAVAILABLE")


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 2 — Deadline
# ─────────────────────────────────────────────────────────────────────────────

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
        status, lat = measure_call(stub, depositar, "001", 10.0, timeout=1.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("2-Deadline", "Depositar (timeout=1s)", status, round(lat, 1),
                 "Server delay=3s | expected DEADLINE_EXCEEDED")

        print("\n[2b] Deposit with timeout=5s (server delay=3s):")
        status, lat = measure_call(stub, depositar, "001", 10.0, timeout=5.0)
        print(f"  Status: {status} | Latency: {lat:.1f}ms")
        register("2-Deadline", "Depositar (timeout=5s)", status, round(lat, 1),
                 "Server delay=3s | expected OK")


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 3 — Concurrency
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 4 — Contract Evolution
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Results table
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

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
```

---

## Phase 7 — Final Report (`analise.md`)

**File:** `atividade_pratica4/relatorio/analise.md`

> **Instructions for the executing agent:**
> 1. Run all 4 experiments and replace the `[MEASURED_VALUE]` placeholders with actual observed values.
> 2. The theoretical answers below are already written — do not alter them.

````markdown
# Report — Atividade Prática 4: gRPC Digital Wallet Service
**Course:** Sistemas Distribuídos  
**Topic:** Digital Wallet  
**Technology:** gRPC + Protocol Buffers (Python)

---

## 1. Experiment Results Table

| # | Experiment             | RPC Method                   | Observed gRPC Status     | Latency (ms)   | Notes                                                      |
|---|------------------------|------------------------------|--------------------------|----------------|------------------------------------------------------------|
| 1 | Unavailability         | ConsultarSaldo               | `UNAVAILABLE`            | [MEASURED_VALUE] | Server stopped. Immediate error after connection timeout |
| 2a| Deadline (short)       | Depositar (timeout=1s)       | `DEADLINE_EXCEEDED`      | ~1000          | Server delay=3s. Client cancels after 1s                 |
| 2b| Deadline (sufficient)  | Depositar (timeout=5s)       | `OK`                     | ~3000          | Server delay=3s. Completed within timeout                |
| 3 | Concurrency (20 cli.)  | Depositar (×20 simultaneous) | 20/20 `OK`               | [MEASURED_VALUE] | Workers=20. All processed without errors                 |
| 4 | Contract Evolution     | Depositar (field `moeda`)    | `OK`                     | [MEASURED_VALUE] | New field ignored by old server — backward-compatible    |

---

## 2. Questões para Análise

### Q1. Por que uma chamada remota não deve ser tratada como função local?

Uma chamada remota (RPC) opera sobre uma rede, um meio **não confiável e não determinístico**, o que cria três classes de falhas fundamentalmente ausentes em chamadas locais:

1. **Falhas de rede:** pacotes podem ser perdidos, reordenados ou atrasados. Uma função local nunca "some no meio do caminho".
2. **Falhas parciais:** o servidor pode receber a requisição, processar o pedido e depois falhar *antes* de enviar a resposta. O cliente não sabe se a operação foi executada ou não. Esse estado de **incerteza** é impossível em chamadas locais, onde uma exceção não deixa dúvidas sobre se o código rodou.
3. **Latência variável e deadline:** chamadas locais têm latência de nanossegundos. Chamadas remotas podem levar centenas de milissegundos e precisam de **timeout** explícito — caso contrário, o cliente pode bloquear indefinidamente. O gRPC resolve isso com o mecanismo de **deadline propagado** via metadados HTTP/2.

A **transparência de acesso** (fazer RPCs parecerem funções locais) foi o objetivo dos primeiros sistemas RPC (DCE, CORBA), mas foi considerada uma **falácia** pelo manifesto das "8 Falácias da Computação Distribuída" (Deutsch, 1994). O gRPC adota a postura oposta: erros de rede são explicitamente modelados como `StatusCode` (UNAVAILABLE, DEADLINE_EXCEEDED), forçando o desenvolvedor a tratar cada cenário de falha individualmente.

---

### Q2. Qual diferença entre erro de aplicação e indisponibilidade do serviço?

São categorias **semanticamente distintas** com implicações de tratamento completamente diferentes:

| Dimensão           | Erro de Aplicação                               | Indisponibilidade do Serviço                    |
|--------------------|------------------------------------------------|-------------------------------------------------|
| **Status gRPC**    | `INVALID_ARGUMENT`, `NOT_FOUND`, `ALREADY_EXISTS`, `FAILED_PRECONDITION` | `UNAVAILABLE`, `DEADLINE_EXCEEDED`              |
| **Causa**          | Dados inválidos fornecidos pelo cliente; violação de regra de negócio | Servidor desligado, rede particionada, timeout  |
| **Servidor**       | Recebeu e processou a requisição                | Não recebeu, ou não conseguiu responder          |
| **Retry seguro?**  | **Não** (novo erro com os mesmos dados)         | **Possivelmente** (servidor pode ter voltado)   |
| **Ação correta**   | Corrigir os dados e tentar novamente            | Exponential backoff + circuit breaker           |
| **Exemplo neste AP4** | Saque com saldo insuficiente (`FAILED_PRECONDITION`) | Servidor parado (`UNAVAILABLE`) no Experimento 1 |

**Por que a distinção importa?** Se um depósito retorna `UNAVAILABLE`, o cliente pode tentar novamente — o dinheiro possivelmente ainda não foi creditado. Se retorna `ALREADY_EXISTS`, tentar novamente não mudará o resultado. Confundir as duas categorias leva a bugs graves: re-tentar um erro de aplicação desperdiça recursos; não re-tentar uma indisponibilidade causa perda de dados.

---

### Q3. O contrato forte aumenta qual tipo de acoplamento?

O uso de um contrato fortemente tipado com Protocol Buffers aumenta o **acoplamento de interface** (também chamado de *schema coupling* ou *representational coupling*). Este é o tipo de acoplamento que exige que cliente e servidor **concordem explicitamente sobre os tipos de dados, nomes de campos e estrutura das mensagens**.

**Por que isso é diferente de outros acoplamentos:**

- **Acoplamento temporal** (um componente precisa do outro disponível ao mesmo tempo): gRPC não agrava isso além do necessário para o paradigma request-response.
- **Acoplamento de implementação** (um componente conhece os internos de outro): gRPC reduz isso — o cliente só conhece a interface `.proto`, não a implementação do servidor.
- **Acoplamento de schema** (o que gRPC aumenta): o cliente *deve* conhecer a estrutura exata das mensagens. Qualquer renomeação de campo ou mudança de número de campo quebra os consumidores.

**Custo vs. Benefício:** O schema coupling introduzido pelo gRPC tem um custo real — exige que todos os consumidores regenerem seus stubs a cada mudança de contrato. O benefício é que esse custo se torna **explícito, gerenciável e verificável em tempo de compilação**, em vez de ser descoberto em runtime como ocorre com REST/JSON. O Protobuf minimiza o impacto com **backward compatibility por design** (campos novos têm IDs únicos; campos desconhecidos são ignorados), mas renomear ou remover campos *sempre* é uma mudança incompatível.

---

### Q4. Como você faria retry sem duplicar efeitos perigosos?

O risco central do retry é a **duplicação de efeitos não idempotentes**. Um `Depositar` reenviado duas vezes crédita o valor duas vezes; um `Sacar` reenviado duas vezes debita o dobro. A solução é **garantir idempotência no servidor**:

**Estratégia: Idempotency Key (chave de idempotência)**

1. O cliente gera um **UUID único** por tentativa de operação lógica (não por chamada de rede). Esse UUID é incluído nos metadados gRPC ou no corpo da mensagem (ex: `idempotency_key` como campo `string` no `TransacaoRequest`).
2. O servidor mantém um **registro de operações processadas** (cache com TTL, ex: Redis ou tabela de banco de dados) mapeando `idempotency_key → resultado`.
3. Ao receber uma requisição:
   - Se `idempotency_key` **não existe** no registro → processa normalmente, salva o resultado.
   - Se `idempotency_key` **já existe** no registro → retorna o resultado já salvo, sem processar novamente.
4. O cliente pode re-enviar com o **mesmo UUID** quantas vezes quiser após `UNAVAILABLE` ou `DEADLINE_EXCEEDED`. O servidor garante que o efeito real ocorrerá no máximo uma vez.

**No contexto deste AP4:** Os métodos `CriarConta` e `ConsultarSaldo` já são naturalmente idempotentes (`CriarConta` retorna `ALREADY_EXISTS` na segunda chamada). `Depositar`, `Sacar` e `Transferir` não são — e exigiriam a estratégia acima em um sistema de produção. Combinado com **exponential backoff** (esperar 1s, 2s, 4s... entre tentativas) e **circuit breaker** (parar de tentar após N falhas consecutivas), o retry se torna seguro e eficiente.

---

### Q5. Que mudança no .proto seria incompatível?

O Protocol Buffers garantem compatibilidade **apenas para certas operações**. As seguintes mudanças são **sempre incompatíveis** (quebram clientes ou servidores existentes):

| Mudança incompatível                        | Por quê quebra                                                                         |
|---------------------------------------------|----------------------------------------------------------------------------------------|
| **Renomear um campo**                       | O nome do campo é usado em JSON/texto; em binário, o *número* é usado — mas renomear força regeneração de stubs e quebra código gerado anterior |
| **Reutilizar um número de campo**           | Campo `saldo = 2` removido, novo campo `descricao = 2` → cliente antigo interpreta `descricao` como `saldo` (corrupção silenciosa de dados) |
| **Mudar o tipo de um campo**               | `double valor = 2` → `string valor = 2` → desserialização falha ou gera lixo binário  |
| **Remover um campo sem reservar o número** | Número pode ser reutilizado no futuro → mesma corrupção do caso acima                 |
| **Mudar a cardinalidade de forma incompatível** | `optional` → `repeated` (ou vice-versa) muda a semântica de serialização            |
| **Renomear o serviço ou um método RPC**    | Stubs gerados referenciam o nome do serviço/método; renomear quebra todos os stubs existentes |

**O que é sempre compatível (boas práticas Protobuf):**
- ✅ Adicionar um novo campo com número único (campo antigo → valor default se ausente)
- ✅ Adicionar um novo método RPC (clientes antigos simplesmente não chamam)
- ✅ Marcar campos como `reserved` antes de removê-los (previne reutilização acidental)

**No Experimento 4 deste AP4:** Adicionamos `string moeda = 4` — este é o caso seguro. Um cliente com stubs novos envia `moeda="BRL"`; um servidor com stubs antigos lê o campo 4, não o reconhece, e o **ignora silenciosamente** (comportamento definido pela especificação Protobuf). A operação prossegue normalmente.
````

---

## Phase 8 — Final Verification Checklist

Before considering the activity complete, the executing agent must verify:

- [ ] `requirements.txt` created and dependencies installed successfully
- [ ] `carteira/carteira.proto` created with 5 RPC methods and 6 message types
- [ ] Stubs generated: `carteira_pb2.py` and `carteira_pb2_grpc.py` exist in `carteira/`
- [ ] `carteira/__init__.py` contains the `sys.path` injection (Fix 1)
- [ ] `carteira/store.py` exists with `AccountStore` class (Fix 2 — per-account locks)
- [ ] `python -m carteira.server` starts without import errors
- [ ] `python -m carteira.client` executes the full demo without unexpected errors
- [ ] `python -m pytest tests/test_carteira.py -v` — all tests pass (green)
  - Each test class binds to port 0 (OS-assigned)
  - No `time.sleep` in test setup (channel_ready_future instead)
- [ ] Experiment 1 produces status `UNAVAILABLE`
- [ ] Experiment 2a produces `DEADLINE_EXCEEDED`; 2b produces `OK`
- [ ] Experiment 3 processes all clients successfully (per-account locking validates)
- [ ] Experiment 4 executes with new field after stub regeneration
- [ ] `relatorio/analise.md` filled with real measured values from experiments

---

## Quick-Start Command Sequence

```powershell
# 1. Navigate to project root
cd c:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create directories
New-Item -ItemType Directory -Force -Path carteira, tests, scripts, relatorio

# 4. [Create all files as specified above]

# 5. Generate stubs
.\gerar_stubs.ps1

# 6. Verify generated stubs
Get-Item carteira\carteira_pb2.py, carteira\carteira_pb2_grpc.py

# 7. Run automated tests (no server needed)
python -m pytest tests/test_carteira.py -v

# 8. Start server (separate terminal)
python -m carteira.server

# 9. Run client demo (separate terminal)
python carteira/client.py

# 10. Experiment 1 — ensure server is stopped first
python scripts\run_experiments.py --exp 1

# 11. Experiment 2 — start server with delay=3 first
#   Terminal 1: python carteira/server.py --delay 3
python scripts\run_experiments.py --exp 2

# 12. Experiment 3 — start server with workers=20 first
#   Terminal 1: python carteira/server.py --workers 20
python scripts\run_experiments.py --exp 3 --clients 20

# 13. Experiment 4 — add 'moeda' field to .proto, regenerate stubs, then:
#   .\gerar_stubs.ps1
python scripts\run_experiments.py --exp 4
```

---

## Agent Execution Notes

> [!IMPORTANT]
> - `server.py` and `client.py` must be run as **module** (`python -m carteira.server`) OR from within the `carteira/` directory (`python server.py`). Both approaches ensure the `carteira/__init__.py` sys.path fix triggers correctly.
> - `carteira_pb2.py` and `carteira_pb2_grpc.py` are **auto-generated** — never create or edit them manually.
> - `tests/test_carteira.py` uses **OS-assigned ports** — no port conflicts possible.
> - For the contract evolution experiment, add the `moeda` field to the **existing** `.proto` file (do not create a new one), then regenerate stubs.

> [!TIP]
> - To debug import errors: `python -c "import grpc; print(grpc.__version__)"`
> - To check if port 50051 is in use: `netstat -ano | findstr :50051`
> - To run a single test class: `python -m pytest tests/test_carteira.py::TestDepositar -v`
