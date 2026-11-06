# Atividade Prática 8 (AP8) — Smart Contract e Integração Local (EVM)

**Disciplina:** Sistemas Distribuídos — Bloco V: Arquiteturas Descentralizadas, EVM e Contratos Inteligentes  
**Tema:** Registro e Verificação Descentralizada de Documentos e Certificados (`DocumentRegistry.sol`)

---

## 1. Visão Geral do Projeto

Este projeto implementa e avalia um sistema descentralizado de registro e verificação de autenticidade de documentos baseado em contrato inteligente para a Máquina Virtual Ethereum (**EVM**). 

A arquitetura adota o princípio de **design de estado mínimo on-chain**: apenas o resumo criptográfico SHA-256 / Keccak-256 (`bytes32 docHash`), o endereço do emissor/registrante (`address registrant`), o carimbo de tempo da rede (`uint256 timestamp`) e os status de existência e validade (`exists`, `isValid`) são mantidos na blockchain. O conteúdo integral dos documentos permanece armazenado off-chain (em sistemas de arquivos distribuídos ou bancos de dados institucionais), minimizando o consumo de gas e eliminando vazamentos de dados confidenciais.

O ambiente de execução e teste é 100% autossuficiente em **Python 3.14+**, empregando `web3.py`, `eth-tester` e `py-evm` (`PyEVMBackend`). Não há necessidade de processos Node.js ou nós RPC externos em segundo plano.

---

## 2. Estrutura de Arquivos

```text
atividade_pratica8/
├── requirements.txt           # Dependências Python com wheels binárias pré-compiladas
├── DocumentRegistry.sol       # Contrato inteligente Solidity (^0.8.20)
├── contract_env.py            # Utilitário de compilação (solc 0.8.20) e deploy na EVM local
├── test_document_registry.py  # Suíte pytest (6 testes cobrindo escrita, eventos e reverts)
├── demo.py                    # Roteiro de laboratório e captura de métricas de gas
├── execucao_ap8.log           # Log com evidências de execução (hashes, endereço, gas, eventos)
├── README.md                  # Este guia de instalação, execução e checklist
└── relatorio_ap8.md           # Relatório técnico completo (invariantes, riscos, REST vs On-Chain, questões)
```

### Links para os Arquivos:
* [`DocumentRegistry.sol`](./DocumentRegistry.sol)
* [`contract_env.py`](./contract_env.py)
* [`test_document_registry.py`](./test_document_registry.py)
* [`demo.py`](./demo.py)
* [`execucao_ap8.log`](./execucao_ap8.log)
* [`relatorio_ap8.md`](./relatorio_ap8.md)

---

## 3. Instruções de Instalação e Execução

Navegue até o diretório da atividade (`atividade_pratica8`):
```bash
cd atividade_pratica8
```

### Passo 1: Instalação das Dependências

Instale os pacotes necessários diretamente via `pip`:
```powershell
python -m pip install -r requirements.txt
```

### Passo 2: Execução dos Testes Automatizados (`pytest`)

Execute a suíte com 6 testes automatizados que cobrem escrita, persistência, verificação de eventos e reverts esperados:
```powershell
python -m pytest test_document_registry.py -v
```

### Passo 3: Execução do Roteiro de Demonstração (`demo.py`)

Execute o roteiro completo de laboratório que compila o contrato, inicializa o nó EVM in-memory, executa as transações on-chain, realiza leituras locais off-chain e gera o arquivo [`execucao_ap8.log`](./execucao_ap8.log):
```powershell
python demo.py
```

---

## 4. Checklist de Validação da Atividade

- [x] **Código do Contrato Inteligente:** [`DocumentRegistry.sol`](./DocumentRegistry.sol) implementado com `solc ^0.8.20`, controle de acesso (`onlyOwner`), validação de hash não nulo, monotonicidade de revogação e emissão de eventos.
- [x] **Ambiente Local EVM Autocontido:** [`contract_env.py`](./contract_env.py) configurado com `PyEVMBackend` e `EthereumTesterProvider`.
- [x] **Suíte de Testes Automatizados:** [`test_document_registry.py`](./test_document_registry.py) com 6 testes aprovados (`6 passed`), validando fluxos felizes e múltiplos cenários de `revert`.
- [x] **Roteiro de Demonstração e Evidências:** [`demo.py`](./demo.py) executado com sucesso e log gerado em [`execucao_ap8.log`](./execucao_ap8.log).
- [x] **Medição de Custos de Gas:** Registro de gas utilizado em deploy, escrita de novo documento, revogação e leitura gratuita (`view`).
- [x] **Relatório Técnico Detalhado:** [`relatorio_ap8.md`](./relatorio_ap8.md) cobrindo modelagem formal de estado, evidências reais de execução, 3 análises de risco de segurança, tabela comparativa Smart Contracts vs REST APIs e respostas às 5 questões conceituais do enunciado.
