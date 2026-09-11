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

    # Internal helpers
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

    # Public API
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
