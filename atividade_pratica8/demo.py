from __future__ import annotations

from pathlib import Path
from web3 import Web3

from contract_env import REVERT_EXCEPTIONS, SOLC_VERSION, deploy_local_environment

LOG_FILE = Path(__file__).parent / "execucao_ap8.log"


def run_demo() -> None:
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log("=" * 78)
    log("ATIVIDADE PRATICA 8 (AP8) - SMART CONTRACT & INTEGRACAO LOCAL (EVM)")
    log("Contrato: DocumentRegistry.sol | Compilador: solc " + SOLC_VERSION)
    log("=" * 78)

    # 1. Implantacao em no local
    w3, contract, deploy_receipt, accounts = deploy_local_environment()
    owner, alice, bob = accounts[0], accounts[1], accounts[2]

    log("\n[1] IMPLANTACAO EM NO EVM LOCAL (PyEVMBackend)")
    log(f"  - Endereco do Contrato : {contract.address}")
    log(f"  - Hash Tx Implantacao  : 0x{deploy_receipt.transactionHash.hex()}")
    log(f"  - Bloco de Implantacao : {deploy_receipt.blockNumber}")
    log(f"  - Owner (Deployer)     : {owner}")
    log(f"  - Conta Alice (Usuaria): {alice}")
    log(f"  - Conta Bob (Terceiro) : {bob}")
    log(f"  - Gas Usado no Deploy  : {deploy_receipt.gasUsed}")

    # 2. Registro de documento (Transacao que altera estado)
    doc_content = "Diploma-Mestrado-Sistemas-Distribuidos-2026-Registro-0001"
    doc_hash = Web3.keccak(text=doc_content)

    log("\n[2] TRANSACAO DE ESCRITA: registerDocument(bytes32)")
    log(f"  - Conteudo Off-Chain   : '{doc_content}'")
    log(f"  - Hash On-Chain (keccak): 0x{doc_hash.hex()}")
    reg_tx_hash = contract.functions.registerDocument(doc_hash).transact({"from": alice})
    reg_receipt = w3.eth.wait_for_transaction_receipt(reg_tx_hash)
    log(f"  - Hash da Transacao    : 0x{reg_receipt.transactionHash.hex()}")
    log(f"  - Numero do Bloco      : {reg_receipt.blockNumber}")
    log(f"  - Status da Execucao   : {reg_receipt.status} (1 = Sucesso)")
    log(f"  - Gas Usado (Registro) : {reg_receipt.gasUsed}")

    # 3. Consulta de estado (Funcao view gratuita off-chain)
    exists, is_valid, timestamp, registrant = contract.functions.verifyDocument(doc_hash).call()
    total_reg = contract.functions.totalRegistered().call()
    log("\n[3] CONSULTA DE ESTADO (VIEW): verifyDocument(bytes32)")
    log(f"  - exists               : {exists}")
    log(f"  - isValid              : {is_valid}")
    log(f"  - timestamp (Bloco)    : {timestamp}")
    log(f"  - registrant           : {registrant}")
    log(f"  - totalRegistered      : {total_reg}")
    log("  - Custo de Gas On-Chain: 0 (leitura local via eth_call)")

    # 4. Observacao de eventos emitidos
    reg_events = contract.events.DocumentRegistered().process_receipt(reg_receipt)
    ev = reg_events[0]
    log("\n[4] EVENTO OBSERVADO NO RECEIPT: DocumentRegistered")
    log(f"  - Evento               : {ev['event']}")
    log(f"  - Endereco Emissor     : {ev['address']}")
    log(f"  - Bloco / LogIndex     : Bloco {ev['blockNumber']} / Log #{ev['logIndex']}")
    log(f"  - arg docHash          : 0x{ev['args']['docHash'].hex()}")
    log(f"  - arg registrant       : {ev['args']['registrant']}")
    log(f"  - arg timestamp        : {ev['args']['timestamp']}")

    # 5. Tentativas invalidas e confirmacao de revert
    log("\n[5] TESTES DE REVERT (REGRAS DE VALIDACAO E CONTROLE DE ACESSO)")
    try:
        contract.functions.registerDocument(doc_hash).transact({"from": bob})
        log("  [ERRO] Registro duplicado nao reverteu!")
    except REVERT_EXCEPTIONS as exc:
        log("  - Tentativa 5A (Registro Duplicado por Bob):")
        log(f"    -> REVERT CONFIRMADO : {type(exc).__name__} - {exc}")

    try:
        contract.functions.revokeDocument(doc_hash).transact({"from": bob})
        log("  [ERRO] Revogacao nao autorizada nao reverteu!")
    except REVERT_EXCEPTIONS as exc:
        log("  - Tentativa 5B (Revogacao Sem Permissao por Bob != Owner):")
        log(f"    -> REVERT CONFIRMADO : {type(exc).__name__} - {exc}")

    # 6. Revogacao autorizada pelo Owner e observacao de evento
    log("\n[6] TRANSACAO DE ESCRITA (OWNER): revokeDocument(bytes32)")
    rev_tx_hash = contract.functions.revokeDocument(doc_hash).transact({"from": owner})
    rev_receipt = w3.eth.wait_for_transaction_receipt(rev_tx_hash)
    rev_events = contract.events.DocumentRevoked().process_receipt(rev_receipt)
    rev_ev = rev_events[0]

    log(f"  - Hash da Transacao    : 0x{rev_receipt.transactionHash.hex()}")
    log(f"  - Numero do Bloco      : {rev_receipt.blockNumber}")
    log(f"  - Gas Usado (Revogacao): {rev_receipt.gasUsed}")
    log(f"  - Evento Emitido       : {rev_ev['event']} (revokedBy={rev_ev['args']['revokedBy']}, ts={rev_ev['args']['timestamp']})")

    exists_after, is_valid_after, ts_after, reg_after = contract.functions.verifyDocument(doc_hash).call()
    log("\n[7] ESTADO FINAL APOS REVOGACAO: verifyDocument(bytes32)")
    log(f"  - exists               : {exists_after}")
    log(f"  - isValid              : {is_valid_after} (Alterado de True para False)")
    log(f"  - timestamp original   : {ts_after} (Preservado)")
    log(f"  - registrant original  : {reg_after} (Preservado)")

    log("\n" + "=" * 78)
    log("RESUMO DE CONSUMO DE GAS POR OPERACAO")
    log("-" * 78)
    log(f"  1. Deploy DocumentRegistry        : {deploy_receipt.gasUsed:>8} gas (Transacao On-Chain)")
    log(f"  2. registerDocument (escrita SSTORE): {reg_receipt.gasUsed:>6} gas (Transacao On-Chain)")
    log(f"  3. revokeDocument (atualizacao)   : {rev_receipt.gasUsed:>8} gas (Transacao On-Chain)")
    log(f"  4. verifyDocument (view / eth_call):        0 gas (Leitura Local Off-Chain)")
    log("=" * 78)

    LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run_demo()
