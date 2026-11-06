from __future__ import annotations

from pathlib import Path
from typing import Any

import solcx
from eth_tester import EthereumTester, PyEVMBackend
from eth_tester.exceptions import TransactionFailed
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import Web3Exception

SOLC_VERSION = "0.8.20"
CONTRACT_PATH = Path(__file__).parent / "DocumentRegistry.sol"
REVERT_EXCEPTIONS = (TransactionFailed, Web3Exception)

_CACHED_ARTIFACTS: tuple[list[dict[str, Any]], str] | None = None


def compile_contract() -> tuple[list[dict[str, Any]], str]:
    """Compila DocumentRegistry.sol usando solc 0.8.20 (target EVM paris) e retorna (abi, bytecode)."""
    global _CACHED_ARTIFACTS
    if _CACHED_ARTIFACTS is not None:
        return _CACHED_ARTIFACTS

    installed_versions = [str(v) for v in solcx.get_installed_solc_versions()]
    if not any(v.startswith(SOLC_VERSION) for v in installed_versions):
        solcx.install_solc(SOLC_VERSION)

    source_code = CONTRACT_PATH.read_text(encoding="utf-8")
    compiled = solcx.compile_source(
        source_code,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        evm_version="paris",
    )

    target_key = next(k for k in compiled if k.endswith(":DocumentRegistry"))
    interface = compiled[target_key]
    _CACHED_ARTIFACTS = (interface["abi"], interface["bin"])
    return _CACHED_ARTIFACTS


def deploy_local_environment() -> tuple[Web3, Any, Any, list[str]]:
    """
    Inicializa um no EVM local em memoria (PyEVMBackend), implanta DocumentRegistry
    a partir de accounts[0] (owner) e retorna (w3, contract, deploy_receipt, accounts).
    """
    abi, bytecode = compile_contract()
    tester = EthereumTester(backend=PyEVMBackend())
    w3 = Web3(EthereumTesterProvider(tester))
    accounts = list(w3.eth.accounts)
    owner = accounts[0]

    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    deploy_tx_hash = factory.constructor().transact({"from": owner})
    deploy_receipt = w3.eth.wait_for_transaction_receipt(deploy_tx_hash)

    contract = w3.eth.contract(address=deploy_receipt.contractAddress, abi=abi)
    return w3, contract, deploy_receipt, accounts
