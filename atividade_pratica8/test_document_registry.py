from __future__ import annotations

import pytest
from web3 import Web3

from contract_env import REVERT_EXCEPTIONS, deploy_local_environment


@pytest.fixture()
def env():
    w3, contract, deploy_receipt, accounts = deploy_local_environment()
    return {
        "w3": w3,
        "contract": contract,
        "deploy_receipt": deploy_receipt,
        "owner": accounts[0],
        "alice": accounts[1],
        "bob": accounts[2],
    }


def test_1_register_document_persists_state(env):
    """Teste 1: Registro bem-sucedido de documento e persistencia de estado on-chain."""
    w3, contract, alice = env["w3"], env["contract"], env["alice"]
    doc_hash = Web3.keccak(text="Certificado-SD-2026-Aluno-Alice")

    tx_hash = contract.functions.registerDocument(doc_hash).transact({"from": alice})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    assert receipt.status == 1
    exists, is_valid, timestamp, registrant = contract.functions.verifyDocument(doc_hash).call()
    assert exists is True
    assert is_valid is True
    assert timestamp > 0
    assert registrant == alice
    assert contract.functions.totalRegistered().call() == 1


def test_2_register_document_emits_event(env):
    """Teste 2: Verificacao da emissao e argumentos do evento DocumentRegistered."""
    w3, contract, alice = env["w3"], env["contract"], env["alice"]
    doc_hash = Web3.keccak(text="Contrato-Prestacao-Servicos-001")

    tx_hash = contract.functions.registerDocument(doc_hash).transact({"from": alice})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    events = contract.events.DocumentRegistered().process_receipt(receipt)
    assert len(events) == 1
    event_args = events[0]["args"]
    assert event_args["docHash"] == doc_hash
    assert event_args["registrant"] == alice
    assert event_args["timestamp"] > 0


def test_3_revoke_document_by_owner(env):
    """Teste 3: Revogacao bem-sucedida pelo owner e emissao do evento DocumentRevoked."""
    w3, contract, owner, alice = env["w3"], env["contract"], env["owner"], env["alice"]
    doc_hash = Web3.keccak(text="Diploma-Revogavel-002")

    contract.functions.registerDocument(doc_hash).transact({"from": alice})
    revoke_tx = contract.functions.revokeDocument(doc_hash).transact({"from": owner})
    receipt = w3.eth.wait_for_transaction_receipt(revoke_tx)

    assert receipt.status == 1
    exists, is_valid, _, registrant = contract.functions.verifyDocument(doc_hash).call()
    assert exists is True
    assert is_valid is False
    assert registrant == alice

    revoke_events = contract.events.DocumentRevoked().process_receipt(receipt)
    assert len(revoke_events) == 1
    assert revoke_events[0]["args"]["docHash"] == doc_hash
    assert revoke_events[0]["args"]["revokedBy"] == owner


def test_4_revert_on_duplicate_registration(env):
    """Teste 4: Falha esperada (revert) ao tentar registrar o mesmo hash duas vezes."""
    contract, alice, bob = env["contract"], env["alice"], env["bob"]
    doc_hash = Web3.keccak(text="Documento-Unico-Imutavel-003")

    contract.functions.registerDocument(doc_hash).transact({"from": alice})

    with pytest.raises(REVERT_EXCEPTIONS):
        contract.functions.registerDocument(doc_hash).transact({"from": bob})

    # Garante que o registrante original (alice) nao foi sobrescrito por bob
    exists, is_valid, _, registrant = contract.functions.verifyDocument(doc_hash).call()
    assert exists is True
    assert is_valid is True
    assert registrant == alice
    assert contract.functions.totalRegistered().call() == 1


def test_5_revert_on_unauthorized_revocation(env):
    """Teste 5: Falha esperada (revert) quando conta nao-owner tenta revogar documento."""
    contract, alice, bob = env["contract"], env["alice"], env["bob"]
    doc_hash = Web3.keccak(text="Documento-Protegido-Owner-004")

    contract.functions.registerDocument(doc_hash).transact({"from": alice})

    with pytest.raises(REVERT_EXCEPTIONS):
        contract.functions.revokeDocument(doc_hash).transact({"from": bob})

    # Documento deve permanecer valido apos tentativa invalida
    _, is_valid, _, _ = contract.functions.verifyDocument(doc_hash).call()
    assert is_valid is True


def test_6_revert_on_empty_hash_or_nonexistent_revocation(env):
    """Teste 6: Falha esperada ao registrar hash nulo ou revogar documento inexistente."""
    contract, owner, alice = env["contract"], env["owner"], env["alice"]
    empty_hash = b"\x00" * 32
    unknown_hash = Web3.keccak(text="Documento-Nao-Registrado-999")

    with pytest.raises(REVERT_EXCEPTIONS):
        contract.functions.registerDocument(empty_hash).transact({"from": alice})

    with pytest.raises(REVERT_EXCEPTIONS):
        contract.functions.revokeDocument(unknown_hash).transact({"from": owner})
