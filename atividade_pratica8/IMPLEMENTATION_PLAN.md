# IMPLEMENTATION PLAN — Atividade Prática 8 (AP8): Contrato Inteligente e Integração Local

## 1. Visão Geral e Decisões Arquiteturais Alinhadas

* **Disciplina:** Sistemas Distribuídos — Atividade Prática 8 (Bloco V: EVM, Solidity, Smart Contracts).
* **Diretório de Trabalho:** `atividade_pratica8`
* **Tema Selecionado:** Registro e Verificação de Documentos/Certificados (`DocumentRegistry.sol`).
* **Stack Tecnológica Aprovada:**
  * **Linguagem do Contrato:** Solidity `^0.8.20` (compilado via `py-solc-x` com target EVM `paris` para máxima compatibilidade).
  * **Ambiente EVM Local (In-Process):** Python `3.14+` com `web3.py`, `eth-tester` e `py-evm` (`PyEVMBackend`), sem necessidade de servidor RPC externo em background ou dependências Node.js.
  * **Suíte de Testes Automatizados:** `pytest` (6 testes automatizados cobrindo persistência de estado, emissão de eventos, revogação autorizada e múltiplos cenários de `revert`).
* **Estrutura Flat de Arquivos (Padrão AP6/AP7):**
  ```text
  atividade_pratica8/
  ├── Conteúdo e Enunciado Atividade Prática 8 - SD.pdf
  ├── HANDOFF_PLANNING.md
  ├── IMPLEMENTATION_PLAN.md
  ├── requirements.txt           # Dependências Python com wheels binárias pré-compiladas
  ├── DocumentRegistry.sol       # Contrato inteligente em Solidity
  ├── contract_env.py            # Utilitário de compilação solc e deploy na EVM local (PyEVM)
  ├── test_document_registry.py  # Suíte pytest (6 testes automatizados: sucesso, eventos e reverts)
  ├── demo.py                    # Roteiro completo de laboratório + geração de execucao_ap8.log
  ├── execucao_ap8.log           # Evidência real capturada (endereço, tx hashes, eventos, gas)
  ├── README.md                  # Instruções de instalação, execução e checklist da atividade
  └── relatorio_ap8.md           # Relatório técnico completo + 3 riscos + REST vs On-Chain + 5 questões
  ```

---

## 2. Pré-Requisitos e Instalação de Dependências

> [!IMPORTANT]
> No Windows com Python 3.14, **NÃO** utilize o extra `eth-tester[py-evm]` com colchetes, pois ele força o download de `safe-pysha3` (sem wheel para Python 3.14, exigindo compilador C++ MSVC). Instale os pacotes listados abaixo diretamente — todos possuem wheels pré-compiladas (`cp314-win_amd64` / `py3-none-any`).

### Arquivo 1: `requirements.txt`
Caminho: `atividade_pratica8/requirements.txt`

```text
web3>=7.0.0
py-solc-x>=2.0.0
eth-tester>=0.12.0b1
py-evm>=0.10.0b1
pytest>=8.0.0
```

### Comando de Instalação:
```powershell
python -m pip install -r requirements.txt
```

---

## 3. Especificação Exata do Código-Fonte

### Arquivo 2: `DocumentRegistry.sol`
Caminho: `atividade_pratica8/DocumentRegistry.sol`

**Invariantes modeladas no contrato:**
1. **Unicidade de Registro ($I_1$):** Um `docHash` não nulo (`bytes32(0)`) só pode ser registrado uma única vez (`!documents[docHash].exists`).
2. **Autoria e Timestamp Imutáveis ($I_2$):** Uma vez registrado, `registrant` e `timestamp` jamais são sobrescritos.
3. **Controle de Acesso Estrito na Revogação ($I_3$):** Apenas o `owner` (endereço que implantou o contrato) pode executar `revokeDocument`.
4. **Monotonicidade de Validade ($I_4$):** Um documento revogado (`isValid == false`) não pode ser revogado novamente nem reativado.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title DocumentRegistry
 * @notice Registro descentralizado de hashes criptograficos de documentos com controle de revogacao.
 */
contract DocumentRegistry {
    struct DocumentRecord {
        bool exists;
        bool isValid;
        uint256 timestamp;
        address registrant;
    }

    address public immutable owner;
    uint256 public totalRegistered;
    mapping(bytes32 => DocumentRecord) private documents;

    event DocumentRegistered(
        bytes32 indexed docHash,
        address indexed registrant,
        uint256 timestamp
    );

    event DocumentRevoked(
        bytes32 indexed docHash,
        address indexed revokedBy,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Registra um novo hash de documento no estado on-chain.
     * @param docHash Hash SHA-256 / Keccak-256 (32 bytes) do documento original off-chain.
     */
    function registerDocument(bytes32 docHash) external {
        require(docHash != bytes32(0), "Invalid empty document hash");
        require(!documents[docHash].exists, "Document already registered");

        documents[docHash] = DocumentRecord({
            exists: true,
            isValid: true,
            timestamp: block.timestamp,
            registrant: msg.sender
        });
        totalRegistered += 1;

        emit DocumentRegistered(docHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Revoga a validade de um documento previamente registrado (restrito ao owner).
     * @param docHash Hash de 32 bytes do documento a ser revogado.
     */
    function revokeDocument(bytes32 docHash) external onlyOwner {
        require(documents[docHash].exists, "Document does not exist");
        require(documents[docHash].isValid, "Document already revoked");

        documents[docHash].isValid = false;

        emit DocumentRevoked(docHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Consulta gratuita (view) do estado de um documento pelo seu hash.
     */
    function verifyDocument(bytes32 docHash)
        external
        view
        returns (
            bool exists,
            bool isValid,
            uint256 timestamp,
            address registrant
        )
    {
        DocumentRecord memory doc = documents[docHash];
        return (doc.exists, doc.isValid, doc.timestamp, doc.registrant);
    }
}
```

---

### Arquivo 3: `contract_env.py`
Caminho: `atividade_pratica8/contract_env.py`

Responsável por instalar/verificar o binário oficial do compilador `solc 0.8.20`, compilar `DocumentRegistry.sol` e instanciar o nó EVM local (`EthereumTesterProvider(PyEVMBackend())`).

```python
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
```

---

### Arquivo 4: `test_document_registry.py`
Caminho: `atividade_pratica8/test_document_registry.py`

Suíte com 6 testes automatizados cobrindo todos os requisitos obrigatórios do enunciado (mínimo exigido: 4 testes).

```python
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
```

---

### Arquivo 5: `demo.py`
Caminho: `atividade_pratica8/demo.py`

Script determinístico que executa todos os 7 passos do **Roteiro Mínimo** (páginas 11–12 do PDF), mede o consumo de gas de cada operação e grava automaticamente o log completo em `execucao_ap8.log`.

```python
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
```

---

## 4. Especificação da Documentação e Relatório Técnico

### Arquivo 6: `README.md`
Caminho: `atividade_pratica8/README.md`

O arquivo `README.md` deve conter:
1. Descrição concisa do projeto (`DocumentRegistry.sol` — Registro e Verificação On-Chain de Documentos).
2. Estrutura de arquivos do diretório:
   - [`DocumentRegistry.sol`](./DocumentRegistry.sol)
   - [`contract_env.py`](./contract_env.py)
   - [`test_document_registry.py`](./test_document_registry.py)
   - [`demo.py`](./demo.py)
   - [`execucao_ap8.log`](./execucao_ap8.log)
   - [`relatorio_ap8.md`](./relatorio_ap8.md)
3. Comandos exatos de instalação, compilação/testes e implantação local:
   ```powershell
   # 1. Instalar dependências (wheels binárias pré-compiladas)
   python -m pip install -r requirements.txt

   # 2. Compilar o contrato e executar os 6 testes automatizados (pytest)
   python -m pytest test_document_registry.py -v

   # 3. Implantar em nó EVM local, executar transações, observar eventos e gerar execucao_ap8.log
   python demo.py
   ```
4. Checklist de validação antes da apresentação (página 13 do PDF) com todos os itens marcados `[x]`.

---

### Arquivo 7: `relatorio_ap8.md`
Caminho: `atividade_pratica8/relatorio_ap8.md`

> [!NOTE]
> O agente executor deve rodar `python demo.py` e `python -m pytest test_document_registry.py -v` **antes** de redigir `relatorio_ap8.md`, copiando os hashes de transação, endereço do contrato e valores de `gasUsed` reais gerados em `execucao_ap8.log` para a Seção 2 do relatório.

O `relatorio_ap8.md` deve seguir exatamente a estrutura e o conteúdo técnico abaixo:

#### Seção 1: Modelagem de Estado e Invariantes On-Chain
* Explicação da estrutura `DocumentRecord` (`bool exists`, `bool isValid`, `uint256 timestamp`, `address registrant`), variáveis de estado (`owner`, `totalRegistered`, `mapping(bytes32 => DocumentRecord) private documents`) e eventos (`DocumentRegistered`, `DocumentRevoked`).
* Definição das 4 invariantes formais garantidas por `require`/`revert`:
  * **Invariante 1 (Não-vacuidade):** `docHash != bytes32(0)`.
  * **Invariante 2 (Imutabilidade e Unicidade de Registro):** `!documents[docHash].exists` impede sobrescrita de autoria (`registrant`) ou carimbo de tempo (`timestamp`).
  * **Invariante 3 (Autoridade Administrativa):** `msg.sender == owner` (via modificador `onlyOwner`) restringe a revogação exclusivamente à autoridade emissora/implantadora.
  * **Invariante 4 (Transição de Estado Válida):** `revokeDocument` exige `exists == true` e `isValid == true`, garantindo transição unidirecional ($\text{Válido} \to \text{Revogado}$).

#### Seção 2: Evidências de Laboratório (Compilação, Implantação, Eventos, Reverts e Gas)
* Tabela resumo com os dados reais extraídos de `execucao_ap8.log`:
  * Endereço do contrato implantado (`0x...`)
  * Hash da transação de deploy, de `registerDocument` e de `revokeDocument`
  * Consumo de gas medido em cada operação (`Deploy`, `registerDocument`, `revokeDocument`, `verifyDocument`)
  * Saída da suíte `pytest` (`6 passed`)
  * Transcrição dos eventos decodificados (`DocumentRegistered` e `DocumentRevoked`) e das mensagens de `revert` capturadas (`Document already registered` e `Caller is not the owner`).

#### Seção 3: Análise de Riscos de Segurança (Mínimo de 3 Riscos)
1. **Risco 1 — Falha de Controle de Acesso e Centralização de Chave Administrativa (`owner`):**
   * *Descrição:* Se a verificação `require(msg.sender == owner)` estivesse ausente em `revokeDocument`, qualquer participante da rede poderia invalidar certificados legítimos de terceiros (ataque de negação de serviço lógica/sabotagem). Adicionalmente, o uso de uma única EOA (*Externally Owned Account*) como `owner` cria um ponto único de falha caso a chave privada seja comprometida ou perdida.
   * *Mitigação Aplicada e Evolução:* No contrato, aplicou-se o modificador `onlyOwner` (`immutable owner`) validado pelo Teste 5. Em produção crítica, recomenda-se substituir a EOA única por uma carteira *Multisig* (ex.: Safe) ou controle de acesso baseado em papéis (*Role-Based Access Control* — RBAC) com múltiplos emissores autorizados.
2. **Risco 2 — Front-Running (Preempção na Mempool / MEV) no Registro de Documentos:**
   * *Descrição:* Em redes EVM públicas, transações enviadas aguardam na *mempool* pública antes da inclusão em bloco. Um atacante monitorando a mempool pode observar uma chamada pendente `registerDocument(docHash)` de `Alice` e submeter uma transação idêntica com o mesmo `docHash`, mas pagando uma taxa de prioridade (*priority fee / gas price*) superior. Como o contrato valida apenas `!documents[docHash].exists`, a transação do atacante seria minerada primeiro, usurpando a autoria (`registrant`) e fazendo a transação legítima de Alice reverter.
   * *Mitigação Possível:* Esquema **Commit-Reveal** em duas fases (Fase 1: usuário registra `keccak256(abi.encodePacked(docHash, msg.sender, salt))`; Fase 2: usuário revela `docHash` e `salt` após confirmação do bloco) ou restrição de registro mediante assinatura criptográfica (`ecrecover` / EIP-712) do emissor.
3. **Risco 3 — Negação de Serviço por Exaustão de Gas (*Out-of-Gas DoS*) e Explosão de Estado (*State Bloat*):**
   * *Descrição:* Armazenar o conteúdo integral de documentos (PDFs, textos longos) na EVM consome 20.000 gas por palavra de 32 bytes na instrução `SSTORE` (~640.000 gas por KB), tornando o contrato economicamente inviável ou atingindo o limite de gas do bloco (*block gas limit*). Além disso, estruturas iteráveis (arrays dinâmicos percorridos com laços `for` on-chain) sofrem de *Unbounded Loop DoS* conforme o número de registros cresce.
   * *Mitigação Aplicada:* O contrato armazena exclusivamente o resumo criptográfico de tamanho fixo (`bytes32 docHash`) e utiliza `mapping(bytes32 => DocumentRecord)` com custo computacional constante $O(1)$ tanto para escrita quanto para leitura, sem laços de repetição on-chain.

#### Seção 4: Comparação Arquitetural — Lógica On-Chain (Smart Contract) vs. Serviço REST Tradicional

| Dimensão Arquitetural | Smart Contract On-Chain (EVM) | Serviço REST Tradicional (API + SGBD) |
| :--- | :--- | :--- |
| **Modelo de Confiança** | Descentralizado (*trustless*): regras impostas por consenso e verificação criptográfica entre nós. | Centralizado: depende da idoneidade do operador do servidor, administrador do banco e provedor cloud. |
| **Consistência e Replicação** | Replicação máquina de estados (*State Machine Replication*) total entre todos os nós validadores; consistência forte após finalidade do bloco. | Replicação mestre-réplica ou particionada gerenciada internamente; sujeita a configurações locais (ACID ou eventual). |
| **Imutabilidade e Auditoria** | Nativa: transações assinadas pelo remetente (`msg.sender`) e histórico encadeado por hashes criptográficos à prova de adulteração retroativa. | Frágil: logs e linhas de tabela podem ser alterados ou truncados por um administrador com privilégio `root`/`DBA`. |
| **Custo de Execução** | Proporcional à computação e armazenamento (`gas` pago por transação de escrita; leituras `view` locais são gratuitas). | Custo fixo/elástico de infraestrutura (CPU, RAM, IOPS e banda), sem cobrança individual por instrução executada. |
| **Latência e Throughput** | Alta latência de escrita (tempo de bloco: segundos a minutos) e throughput limitado pela ordenação global serializada. | Baixíssima latência (milissegundos) e alto throughput (milhares de requisições concorrentes por segundo). |
| **Privacidade de Dados** | Estado público por padrão em todos os nós; exige manter dados sensíveis off-chain e publicar apenas hashes/provas. | Dados privados por padrão, protegidos por firewall, TLS e controle de acesso na camada de aplicação. |
| **Acesso ao Mundo Externo** | Isolado e determinístico: contratos não fazem chamadas HTTP externas diretamente; dependem de **oráculos** (Seção 14.11). | Nativo: o backend REST consome APIs externas, webhooks, filas de mensagens e serviços de terceiros livremente. |
| **Manutenção e Evolução** | Código imutável após deploy no endereço; evolução exige migração de estado ou padrões de *Proxy/Upgradeability* e governança (Seção 14.12). | Deploy contínuo (CI/CD), *hotfixes* imediatos e migrações de schema (`ALTER TABLE`) simples. |

#### Seção 5: Respostas às 5 Questões para Análise (Página 12 do Enunciado)

1. **Que parte do estado precisa realmente estar on-chain?**
   Apenas a **âncora criptográfica de integridade e autoria** precisa estar on-chain: o hash de 32 bytes do documento (`bytes32 docHash`), o endereço do emissor/registrante (`address registrant`), o carimbo de tempo do bloco (`uint256 timestamp`) e os flags booleanos de existência/validade (`exists`, `isValid`). O arquivo original completo (PDF, contrato jurídico, diploma em alta resolução ou dados pessoais sujeitos à LGPD) **deve permanecer off-chain** (em armazenamento objeto, IPFS ou banco institucional), pois armazená-lo na EVM teria custo proibitivo de gas e exporia dados confidenciais publicamente em todos os nós da rede.

2. **Qual função consome gas quando enviada como transação e por quê?**
   As funções **`registerDocument(bytes32)`** e **`revokeDocument(bytes32)`** (além do `constructor` no momento do deploy) consomem gas porque são enviadas como **transações que mutam o estado global persistente da EVM** (executando opcodes de escrita em storage como `SSTORE` e emissão de logs `LOG3`). Na arquitetura da EVM, cada nó validador da rede precisa executar deterministicamente essas instruções, atualizar sua árvore de estado (*state trie*) e armazenar os dados permanentemente; o gas remunera esse esforço computacional/armazenamento e protege a rede contra ataques de negação de serviço (loops infinitos ou abuso de disco). Em contrapartida, `verifyDocument(bytes32)` é marcada como `view`: quando invocada off-chain via `eth_call`, ela apenas lê o estado local do nó consultado sem gerar transação nem alterar a blockchain, tendo custo de gas zero para o usuário.

3. **Como eventos ajudam sistemas off-chain?**
   Eventos Solidity (`DocumentRegistered` e `DocumentRevoked`) são gravados na estrutura de *transaction receipt logs* (via opcodes `LOG0`..`LOG4`) com custo de gas muito inferior ao armazenamento em variáveis de estado (`SSTORE`) e possuem campos indexados (`indexed docHash`, `indexed registrant`) que alimentam filtros de Bloom nos cabeçalhos dos blocos. Eles funcionam como um mecanismo assíncrono de **notificação e indexação para sistemas off-chain**: aplicações web, APIs REST, microsserviços e indexadores podem escutar ou filtrar eventos em tempo real sem precisar fazer *polling* exaustivo de variáveis de estado, disparando fluxos externos (envio de e-mail, atualização de cache relacional local, geração de comprovante) e mantendo um histórico auditável de todas as transições ocorridas.

4. **Que vulnerabilidade seria possível se controle de acesso estivesse ausente?**
   Se o modificador `onlyOwner` (`require(msg.sender == owner, "Caller is not the owner")`) estivesse ausente na função `revokeDocument(bytes32)`, ocorreria uma vulnerabilidade crítica de **Controle de Acesso Quebrado (*Broken Access Control* / Escalação de Privilégio Horizontal e Vertical — Seção 14.10)**: qualquer endereço arbitrário na rede poderia invocar `revokeDocument` para qualquer `docHash` existente e alterar seu estado `isValid` para `false`. Isso permitiria que um agente malicioso inutilizasse certificados, diplomas ou documentos de terceiros à vontade, destruindo a confiabilidade e a disponibilidade lógica do registro.

5. **Quando um banco de dados tradicional seria escolha superior?**
   Um banco de dados tradicional (relacional ACID como PostgreSQL ou distribuído gerenciado) é a escolha superior quando:
   * **Existe uma única entidade confiável** (ex.: sistema interno de uma única empresa ou órgão que já detém autoridade legal exclusiva), eliminando a necessidade de consenso descentralizado entre partes mutuamente desconfiadas;
   * **Os requisitos de desempenho exigem baixa latência (milissegundos) e alto throughput** (milhares de escritas por segundo), incompatíveis com o tempo de bloco e a serialização da EVM;
   * **Os dados são volumosos, mutáveis ou confidenciais**, exigindo consultas complexas (`JOIN`, agregações analíticas, busca textual) e direito ao esquecimento/exclusão física de registros (LGPD/GDPR);
   * **A previsibilidade de custos operacionais é prioritária**, evitando taxas variáveis de gas por operação de escrita.

---

## 5. Sequência Passo a Passo de Execução e Verificação

O agente executor deve realizar exatamente os 6 passos abaixo em ordem sequencial:

1. **Instalar Dependências:**
   Criar `requirements.txt` em `atividade_pratica8` e executar:
   ```powershell
   python -m pip install -r requirements.txt
   ```
2. **Criar Contrato e Módulos Python:**
   Escrever os arquivos `DocumentRegistry.sol`, `contract_env.py`, `test_document_registry.py` e `demo.py` exatamente conforme especificado na Seção 3.
3. **Executar Testes Automatizados (`pytest`):**
   ```powershell
   python -m pytest test_document_registry.py -v
   ```
   *Critério de aceite:* 6 testes executados, `6 passed` sem erros.
4. **Executar Script de Demonstração e Capturar Evidências (`demo.py`):**
   ```powershell
   python demo.py
   ```
   *Critério de aceite:* O arquivo `execucao_ap8.log` é gerado automaticamente contendo endereço do contrato, hashes das transações, eventos decodificados, confirmações de `revert` e tabela de consumo de gas.
5. **Gerar Documentação Final (`README.md` e `relatorio_ap8.md`):**
   Escrever `README.md` e `relatorio_ap8.md` conforme a Seção 4, incorporando os valores reais (endereço, hashes, gas, blocos) extraídos de `execucao_ap8.log`.
6. **Validação Final:**
   Confirmar que todos os arquivos obrigatórios existem em `atividade_pratica8/` e que `pytest` continua passando 100%.

---

## 6. Prompt de Execução Autônoma (Executor Prompt)

Copie e cole o bloco abaixo em uma nova sessão de terminal com o `agy` para que um agente executor leve implemente toda a atividade do início ao fim sem intervenção humana:

```markdown
Você é um Agente Executor focado em implementação direta, rápida e determinística.
O planejamento e a especificação desta atividade já foram revisados e aprovados pelo usuário no arquivo:
`atividade_pratica8/IMPLEMENTATION_PLAN.md`

### Sua Missão:
1. Leia integralmente o arquivo `atividade_pratica8/IMPLEMENTATION_PLAN.md`.
   - Nota importante: Este plano (`IMPLEMENTATION_PLAN.md`) É a especificação aprovada pelo usuário para esta atividade. Não crie pastas `openspec/` nem faça perguntas adicionais; execute diretamente os passos definidos no plano.
2. Crie os arquivos especificados na Seção 2 e na Seção 3 dentro de `atividade_pratica8`:
   - `requirements.txt`
   - `DocumentRegistry.sol`
   - `contract_env.py`
   - `test_document_registry.py`
   - `demo.py`
3. Instale as dependências executando:
   `python -m pip install -r requirements.txt`
4. Execute a suíte de testes automatizados e confirme que todos os 6 testes passam:
   `python -m pytest test_document_registry.py -v`
5. Execute o roteiro de demonstração local para gerar o arquivo de evidências `execucao_ap8.log`:
   `python demo.py`
6. Leia o conteúdo gerado em `execucao_ap8.log` e crie os arquivos finais de documentação na pasta `atividade_pratica8` seguindo fielmente a Seção 4 do plano:
   - `README.md` (com instruções de execução, visão geral dos arquivos e checklist completo)
   - `relatorio_ap8.md` (preenchendo a Seção 2 com os hashes de transação, endereço do contrato, eventos e valores de gas reais capturados em `execucao_ap8.log`, além das seções completas de invariantes, 3 riscos de segurança, tabela comparativa On-Chain vs REST e respostas às 5 questões da página 12).
7. Ao concluir, apresente um resumo conciso confirmando os testes aprovados e os arquivos gerados.
```
