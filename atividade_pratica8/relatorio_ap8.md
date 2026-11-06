# Relatório Técnico — Atividade Prática 8 (AP8)
# Smart Contract, EVM e Integração Local

**Disciplina:** Sistemas Distribuídos  
**Tema:** Registro e Verificação Descentralizada de Documentos e Certificados (`DocumentRegistry.sol`)  
**Data:** 06/11/2026  
**Ambiente de Execução:** Python 3.14.7 | solc 0.8.20 (EVM target `paris`) | `web3.py 8.0.0` | `eth-tester 0.14.0b1` | `py-evm 0.12.1b1`

---

## 1. Modelagem de Estado e Invariantes On-Chain

O contrato inteligente [`DocumentRegistry.sol`](./DocumentRegistry.sol) foi projetado para atuar como uma âncora imutável de proveniência, autenticidade e validade temporal de documentos e certificados no âmbito da Máquina Virtual Ethereum (**EVM**).

### 1.1 Estruturas de Dados e Variáveis de Estado

```solidity
struct DocumentRecord {
    bool exists;        // Indica se o hash foi registrado previamente
    bool isValid;       // Indica se o documento está ativo ou revogado
    uint256 timestamp;  // Carimbo de tempo Unix do bloco em que foi registrado
    address registrant; // Endereço da conta que submeteu o registro
}

address public immutable owner;                     // Endereço do administrador/emissor
uint256 public totalRegistered;                    // Contador cumulativo de documentos
mapping(bytes32 => DocumentRecord) private documents; // Tabela hash on-chain O(1)
```

* **`owner` (`address public immutable`):** Gravado no bytecode no momento do deploy e imutável durante todo o ciclo de vida do contrato, eliminando custos de `SLOAD` para leitura de permissão de administração.
* **`documents` (`mapping(bytes32 => DocumentRecord) private`):** Armazena os registros utilizando a função de dispersão criptográfica Keccak-256 sobre a chave de armazenamento, garantindo acesso em tempo $O(1)$ sem a necessidade de percorrer estruturas dinâmicas ou arrays on-chain.
* **`totalRegistered` (`uint256 public`):** Contador incremental que permite telemetria pública imediata do volume de registros emitidos.

### 1.2 Eventos On-Chain

* **`DocumentRegistered(bytes32 indexed docHash, address indexed registrant, uint256 timestamp)`:** Emitido em toda transação de registro bem-sucedida. O uso do modificador `indexed` no hash e no endereço do emissor indexa os argumentos nos tópicos do log de recibo da EVM (*Bloom Filter* do bloco), permitindo que indexadores off-chain filtrem instantaneamente registros por documento ou por remetente.
* **`DocumentRevoked(bytes32 indexed docHash, address indexed revokedBy, uint256 timestamp)`:** Emitido sempre que o `owner` revoga a validade de um documento existente.

### 1.3 Invariantes Formais Garantidas pelo Contrato

1. **Invariante 1 — Não-Vacuidade ($I_1$):**
   $$\forall h \in \text{Domain}(\text{registerDocument}), \quad h \neq \texttt{bytes32(0)}$$
   Garantida por: `require(docHash != bytes32(0), "Invalid empty document hash");`. Impede poluição do estado com hashes vazios ou inicializações espúrias.

2. **Invariante 2 — Unicidade e Imutabilidade de Autoria ($I_2$):**
   $$\forall h, \quad \text{documents}[h].\text{exists} = \text{true} \implies (\text{registrant e timestamp são imutáveis})$$
   Garantida por: `require(!documents[docHash].exists, "Document already registered");`. Evita sobrescrita de proveniência e falsificação retroativa de autoria.

3. **Invariante 3 — Autoridade Estrita de Revogação ($I_3$):**
   $$\text{Caller}(\text{revokeDocument}) = \text{owner}$$
   Garantida pelo modificador `onlyOwner`: `require(msg.sender == owner, "Caller is not the owner");`. Protege contra revogações maliciosas executadas por contas não autorizadas.

4. **Invariante 4 — Monotonicidade de Validade ($I_4$):**
   $$\text{documents}[h].\text{isValid} : \text{true} \longrightarrow \text{false} \quad (\text{transição irreversível})$$
   Garantida por: `require(documents[docHash].exists, "Document does not exist");` e `require(documents[docHash].isValid, "Document already revoked");`. Uma vez revogado, o documento jamais transita de volta para válido.

---

## 2. Evidências de Laboratório e Medições On-Chain

A execução dos testes automatizados e do script de demonstração local gerou o log de evidências auditáveis registrado em [`execucao_ap8.log`](./execucao_ap8.log).

### 2.1 Resumo dos Dados Reais Capturados

| Parâmetro / Operação | Valor Medido / Capturado na Execução |
| :--- | :--- |
| **Endereço do Contrato** | `0xF2E246BB76DF876Cef8b38ae84130F4F55De395b` |
| **Owner (Deployer Account)** | `0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf` |
| **Conta Alice (Registrante)** | `0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF` |
| **Conta Bob (Não Autorizado)** | `0x6813Eb9362372EEF6200f3b1dbC3f819671cBA69` |
| **Tx Hash: Deploy** | `0xe133ac365249c90f0b42ac88da7558e9de7e7cbda257aa95cfcb17bc32d072d0` (Bloco 1) |
| **Tx Hash: `registerDocument`** | `0xf8bfb89b0cb305d66b6c19a2b30dfcf78e60fc9cf4184febe40ea78dc9eac9d3` (Bloco 2) |
| **Tx Hash: `revokeDocument`** | `0x413b27a8d50eeff5c7283b4cdbb693b7da522e5d9b81779d679f3a8e76d2a996` (Bloco 3) |
| **Hash do Documento Registrado**| `0x7e9a0969041dfd59463bb3ea52edbe7b310b9556cda703a3aec294d9132ff68b` |
| **Conteúdo Off-Chain de Teste** | `"Diploma-Mestrado-Sistemas-Distribuidos-2026-Registro-0001"` |
| **Timestamp do Bloco** | `1793975616` (Registro) / `1793975617` (Revogação) |

### 2.2 Consumo de Gas por Operação

| Operação | Natureza da Chamada | Custo de Gas Medido | Justificativa Técnica do Consumo |
| :--- | :--- | :---: | :--- |
| **Deploy (`constructor`)** | Transação On-Chain | **602.478 gas** | Criação do contrato, inicialização da variável imutável `owner`, execução do runtime init e gravação do bytecode final no storage da EVM via `CREATE`. |
| **`registerDocument`** | Transação On-Chain | **113.574 gas** | Alocação de novo slot no mapping (`SSTORE` de slot não-zero: 20.000 gas base + custos de hash e escrita nos 4 membros do `DocumentRecord`), incremento de `totalRegistered` e emissão do evento com 2 tópicos indexados (`LOG3`). |
| **`revokeDocument`** | Transação On-Chain | **29.714 gas** | Modificação de slot já existente (`SSTORE` de valor true para false: 5.000 gas ou atualização de slot aquecido), validação de `onlyOwner` (`SLOAD`) e emissão de evento com 2 tópicos (`LOG3`). |
| **`verifyDocument`** | Chamada Local (`view`) | **0 gas** | Consulta estática off-chain executada localmente via RPC `eth_call`. Lê o estado local do nó sem minerar transação nem despender gas da conta consultante. |

### 2.3 Validação dos Reverts e Controle de Acesso

O script de demonstração submeteu duas chamadas anômalas para testar as proteções do contrato:
1. **Tentativa 5A (Registro Duplicado):** A conta `Bob` tentou registrar o mesmo `docHash` já pertencente a `Alice`. A EVM interceptou e reverteu a transação com a mensagem exata:
   ```text
   TransactionFailed - execution reverted: Document already registered
   ```
2. **Tentativa 5B (Revogação Não Autorizada):** A conta `Bob` tentou invocar `revokeDocument(docHash)` sem ser o proprietário do contrato. A transação reverteu imediatamente:
   ```text
   TransactionFailed - execution reverted: Caller is not the owner
   ```

### 2.4 Resultado da Suíte Automatizada (`pytest`)

A suíte [`test_document_registry.py`](./test_document_registry.py) obteve 100% de sucesso em todos os 6 cenários:

```text
atividade_pratica8/test_document_registry.py::test_1_register_document_persists_state PASSED [ 16%]
atividade_pratica8/test_document_registry.py::test_2_register_document_emits_event PASSED [ 33%]
atividade_pratica8/test_document_registry.py::test_3_revoke_document_by_owner PASSED [ 50%]
atividade_pratica8/test_document_registry.py::test_4_revert_on_duplicate_registration PASSED [ 66%]
atividade_pratica8/test_document_registry.py::test_5_revert_on_unauthorized_revocation PASSED [ 83%]
atividade_pratica8/test_document_registry.py::test_6_revert_on_empty_hash_or_nonexistent_revocation PASSED [100%]
====================== 6 passed, 1146 warnings in 6.95s =======================
```

---

## 3. Análise de Riscos de Segurança (Mínimo de 3 Riscos)

### Risco 1: Quebra de Controle de Acesso e Ponto Único de Falha na Chave do Proprietário (`owner`)
* **Descrição do Risco:** A revogação de documentos no contrato é um privilégio administrativo crítico. Caso a validação `require(msg.sender == owner)` fosse omitida em `revokeDocument`, qualquer nó participante da rede poderia revogar unilateralmente diplomas e contratos de terceiros, caracterizando um ataque severo de *Broken Access Control* (Seção 14.10) e negação de serviço de integridade. Além disso, a gestão do `owner` por uma única EOA (*Externally Owned Account*) introduz um ponto central de falha (*Single Point of Failure*): se a chave privada da autoridade emissora for vazada ou perdida, todos os documentos do sistema ficam permanentemente expostos à sabotagem ou sem possibilidade de revogação legítima.
* **Mitigação Implementada e Práticas Recomendadas:** No código implementado, aplicou-se o modificador `onlyOwner` verificado pelo Teste 5 e pela tentativa 5B do script de demonstração. Em sistemas produtivos de alta criticidade (ex.: universidades federais ou cartórios), o endereço `owner` deve ser transferido para uma carteira multifirmada (*Multisig*, ex.: Safe) com quórum $M$-de-$N$ ou um módulo RBAC (*Role-Based Access Control* baseado no padrão OpenZeppelin `AccessControl`) com separação entre papéis de auditoria, emissão e revogação.

### Risco 2: Preempção na Fila de Transações Públicas (*Front-Running* / MEV)
* **Descrição do Risco:** Em redes blockchain públicas (como a Mainnet Ethereum), transações enviadas por clientes não entram diretamente nos blocos: elas aguardam em uma fila pública e visível denominada *mempool*. Bots de *Maximal Extractable Value* (MEV) monitoram a mempool em tempo real. Se um usuário submete uma transação legítima `registerDocument(docHash)`, um atacante pode observar o hash antes da confirmação do bloco e submeter uma transação idêntica com o mesmo `docHash`, porém oferecendo uma taxa de prioridade (*priority fee* / *gas price*) ligeiramente superior aos validadores. Devido à ordenação por incentivo econômico, a transação do atacante é minerada antes; como o contrato impõe `!documents[docHash].exists`, a transação do usuário original falha por reversão (`Document already registered`) e a autoria on-chain do documento é indevidamente atribuída ao atacante.
* **Mitigação Técnica Viável:** 
  1. Adoção do padrão **Commit-Reveal** em duas fases: na fase 1, o usuário publica apenas um compromisso $C = \text{keccak256}(\text{docHash} \parallel \text{msg.sender} \parallel \text{salt})$; na fase 2 (após a inclusão e profundidade de blocos segura), o usuário revela o `docHash` e o `salt`. Bots não conseguem antecipar o registro porque o compromisso está atrelado à identidade do remetente.
  2. Uso de assinaturas criptográficas off-chain tipadas (EIP-712), onde o contrato valida a assinatura da autoridade emissora antes de persistir o registro.

### Risco 3: Negação de Serviço por Exaustão de Gas (*Out-of-Gas DoS*) e Inchaço de Estado (*State Bloat*)
* **Descrição do Risco:** Na EVM, persistir dados em disco consome a instrução `SSTORE`, precificada em 20.000 gas para cada palavra de 32 bytes alocada pela primeira vez. Se a aplicação tentasse armazenar o conteúdo bruto dos documentos (PDFs, imagens de diplomas, contratos jurídicos de dezenas de megabytes) diretamente on-chain em variáveis do tipo `bytes` ou `string`, o consumo de gas excederia instantaneamente o limite de gas por bloco (*Block Gas Limit* de 30 milhões de gas), impossibilitando a mineração da transação. Da mesma forma, manter coleções de documentos em arrays dinâmicos lineares (`bytes32[]`) percorridos com laços de repetição `for` on-chain criaria uma vulnerabilidade de *Unbounded Loop DoS*: com o crescimento do histórico, a execução do loop exigiria mais gas do que o limite do bloco, congelando permanentemente as operações de consulta e verificação.
* **Mitigação Implementada:** O contrato armazena rigorosamente apenas o resumo de 32 bytes (`bytes32 docHash`) e uma estrutura compacta em mapeamento hash (`mapping(bytes32 => DocumentRecord)`). Isso assegura complexidade computacional e consumo de gas estritamente $O(1)$, independente de o sistema possuir 10 ou 10 milhões de documentos cadastrados.

---

## 4. Comparação Arquitetural: Lógica On-Chain vs. Serviço REST Tradicional

| Dimensão Arquitetural | Smart Contract On-Chain (EVM) | Serviço REST Tradicional (API + SGBD) |
| :--- | :--- | :--- |
| **Modelo de Confiança** | **Descentralizado (*Trustless*):** A execução é auditada e validada deterministicamente por múltiplos nós independentes sob algoritmo de consenso. Nenhuma parte isolada pode violar as regras programadas. | **Centralizado:** O cliente deposita confiança cega na idoneidade do operador da API, na equipe de infraestrutura e no provedor em nuvem. |
| **Replicação e Consistência** | **Máquina de Estados Replicada (*SMR*):** Todos os nós validadores executam exatamente as mesmas instruções e armazenam o mesmo estado global. Consistência forte atingida após finalidade do bloco. | **Mestre-Réplica ou Particionado:** Gerenciado pela aplicação e banco (PostgreSQL, MongoDB). Sujeito a divergências de replicação eventual e particionamento de rede. |
| **Imutabilidade e Auditoria** | **Nativa e Inviolável:** Registros e eventos são assinados criptograficamente pelas contas (`msg.sender`) e encadeados em blocos por hashes SHA-256/Keccak. Impossível alterar dados retroativos sem quebrar a cadeia de consenso. | **Frágil e Externa:** Registros podem ser modificados ou deletados diretamente via `UPDATE` / `DELETE` por qualquer usuário ou invasor com privilégios de `DBA`/`root`. Auditoria exige logs externos adicionais. |
| **Custo de Computação** | **Microcobrança por Instrução (`Gas`):** Cada opcode que altera storage (`SSTORE`) ou processa dados gera custos financeiros diretos na transação. Leituras locais (`view`) são gratuitas. | **Custo Fixo ou Elástico de Infraestrutura:** Cobrança por instâncias de servidores, vCPU, memória RAM e tráfego de dados, independente do número exato de instruções SQL individuais. |
| **Latência e Throughput** | **Baixo Throughput e Alta Latência:** Limitado pelo intervalo entre blocos (ex.: 12 segundos na Ethereum) e pela serialização global das transações. | **Altíssimo Throughput e Baixa Latência:** Respostas em milissegundos e suporte a dezenas de milhares de requisições concorrentes por segundo com escalonamento horizontal. |
| **Privacidade de Dados** | **Público por Padrão:** Qualquer nó conectado à rede pode inspecionar os valores armazenados no storage do contrato, exigindo armazenamento exclusivo de resumos criptográficos (`hashes`) ou provas de conhecimento zero (ZKPs). | **Privado por Padrão:** Dados ficam confinados atrás de firewalls, VPCs e regras de autorização granulares na camada de software, viabilizando conformidade direta com LGPD/GDPR. |
| **Acesso ao Mundo Externo** | **Determinismo Fechado:** Contratos inteligentes não podem emitir requisições HTTP ou interagir diretamente com APIs externas para evitar divergência de consenso entre validadores; requer **Oráculos** (Seção 14.11). | **Totalmente Aberto:** O backend faz chamadas HTTP, consome filas de mensagens (RabbitMQ, Kafka), acessa webhooks e consome serviços terceiros sem restrições de determinismo. |
| **Evolução e Manutenção** | **Imutável após Deploy:** Bugs em produção não podem ser corrigidos com um novo push de código no mesmo endereço. A evolução exige padrões complexos de governança e contratos de atualização (*Upgradeable Proxies* — Seção 14.12). | **Deploy Contínuo (CI/CD):** Pipelines automatizados atualizam containers Docker em produção instantaneamente com rollbacks e migrações de schema automatizadas via scripts SQL. |

---

## 5. Respostas às Questões para Análise (Página 12 do Enunciado)

### Questão 1: Que parte do estado precisa realmente estar on-chain?
**Resposta:**  
Apenas a **âncora criptográfica mínima de integridade e autoria** precisa estar on-chain. No contexto do [`DocumentRegistry.sol`](./DocumentRegistry.sol), isso compreende o resumo de 32 bytes do documento original (`bytes32 docHash`), o endereço público da conta que realizou a emissão (`address registrant`), a marcação temporal verificável da rede (`uint256 timestamp`) e as flags booleanas de controle de ciclo de vida (`exists`, `isValid`). 

O arquivo bruto original (seja um arquivo PDF em alta resolução, contrato corporativo ou diploma digital contendo dados pessoais de estudantes) **deve permanecer rigorosamente off-chain** — hospedado em armazenamentos de objetos distribuídos (IPFS, Arweave) ou em repositórios corporativos controlados. Armazenar arquivos brutos on-chain acarretaria custos inviáveis de gas (aproximadamente 640.000 gas por kilobyte persistido via `SSTORE`), esgotaria a capacidade do bloco da rede e violaria preceitos básicos de privacidade e legislações de proteção de dados (LGPD/GDPR), visto que todo estado on-chain é público e imutável.

---

### Questão 2: Qual função consome gas quando enviada como transação e por quê?
**Resposta:**  
As funções **`registerDocument(bytes32)`** e **`revokeDocument(bytes32)`** (além da criação do contrato no `constructor`) consomem gas quando enviadas à rede. Isso ocorre porque ambas são operações de **escrita que mutam o estado global persistente da EVM**. Ao executá-las, o processador da EVM invoca opcodes de alto custo como `SSTORE` (para criar e atualizar entradas no storage persistente dos nós validadores) e instruções de registro de eventos como `LOG3` (para emitir eventos indexados). No modelo econômico e operacional da Ethereum, cada nó validador precisa executar deterministicamente essas transações e gravar o resultado em suas árvores de estado Merkle-Patricia; a taxa de gas serve para remunerar esse consumo de computação e armazenamento e para proteger os nós contra ataques de negação de serviço (como laços infinitos ou inchaço deliberado de disco).

Por outro lado, a função **`verifyDocument(bytes32)`** é declarada com o modificador **`view`**. Quando invocada a partir de uma aplicação externa (via RPC `eth_call`), ela é executada de forma estritamente local e isolada no nó consultado, lendo o estado existente sem gerar transação minerável, sem alterar nenhuma variável na blockchain e, consequentemente, **sem qualquer cobrança de gas para o usuário**.

---

### Questão 3: Como eventos ajudam sistemas off-chain?
**Resposta:**  
Eventos Solidity (como `DocumentRegistered` e `DocumentRevoked`) são gravados na seção de *logs* do recibo da transação (*transaction receipt logs*) utilizando a família de instruções `LOG0` a `LOG4`. Eles são economicamente muito mais baratos em termos de gas do que a alocação de variáveis em storage permanente (`SSTORE`) e possuem suporte a campos indexados (`indexed`), os quais são estruturados nos filtros de Bloom (*Bloom Filters*) dos cabeçalhos dos blocos.

Para sistemas distribuídos off-chain, os eventos atuam como um **canal assíncrono de mensageria, indexação e barramento de notificações**:
1. **Reatividade e Desacoplamento:** Serviços off-chain (backends Python/Node.js, APIs REST e indexadores como *The Graph*) podem escutar eventos via WebSockets ou polling filtrado sem necessidade de interrogar repetidamente variáveis de estado on-chain;
2. **Integração Operacional:** A detecção de um evento `DocumentRegistered` em um bloco confirmado pode disparar fluxos automatizados externos, tais como notificação por e-mail para o titular, emissão de segunda via digital ou atualização de réplicas em bancos de dados relacionais locais;
3. **Auditabilidade Histórica:** Fornecem um log cronológico e indexado de todas as transições de estado pelas quais o contrato passou desde o bloco de gênese até o estado atual.

---

### Questão 4: Que vulnerabilidade seria possível se controle de acesso estivesse ausente?
**Resposta:**  
Caso o modificador de controle de acesso `onlyOwner` (definido pela cláusula `require(msg.sender == owner, "Caller is not the owner")`) estivesse ausente na função `revokeDocument(bytes32)`, o contrato apresentaria uma falha crítica de **Controle de Acesso Quebrado (*Broken Access Control* / Escalação Não Autorizada de Privilégios — Seção 14.10)**.

Sob essa vulnerabilidade, qualquer ator arbitrário conectado à rede EVM, utilizando qualquer endereço de conta gerado instantaneamente (como a conta `Bob` testada no laboratório), poderia invocar `revokeDocument` informando o hash de qualquer documento legítimo pertencente a terceiros (como o diploma de `Alice`). Como a função apenas validava se o documento existia e se estava válido, a chamada seria executada com sucesso, alterando a variável `isValid` para `false`. Isso concederia a qualquer invasor o poder de revogar unilateralmente registros legítimos, anulando certificados e quebrando completamente a confiabilidade, a utilidade e a disponibilidade lógica do registro descentralizado.

---

### Questão 5: Quando um banco de dados tradicional seria escolha superior?
**Resposta:**  
Um banco de dados tradicional (seja um SGBD relacional ACID como PostgreSQL/MySQL ou NoSQL distribuído gerenciado) é uma escolha arquitetural **amplamente superior** a um contrato inteligente on-chain nos seguintes cenários:

1. **Domínio com Autoridade Centralizada Confiável:** Quando o sistema pertence a uma única organização (ex.: sistema acadêmico interno de uma instituição ou prontuário médico intra-hospitalar) que já detém autoridade legal e operacional delegada, tornando o consenso descentralizado entre validadores redundante e computacionalmente ineficiente;
2. **Requisitos Estritos de Desempenho e Throughput:** Aplicações com alta taxa de concorrência que exigem dezenas de milhares de operações de escrita por segundo com latência na casa dos milissegundos, incompatíveis com os tempos de confirmação de blocos e ordenação serializada das redes blockchain;
3. **Volume de Dados e Consultas Analíticas Complexas:** Sistemas que armazenam gigabytes ou terabytes de conteúdo textual/binário e dependem de junções complexas (`JOIN`), buscas de texto completo (*Full-Text Search*), paginação e agregações estatísticas, recursos computacionalmente inviáveis em ambientes EVM;
4. **Conformidade Regulatória e Direito ao Esquecimento:** Casos sujeitos a regulações de privacidade como a LGPD e o GDPR, que exigem a capacidade de exclusão física e retificação de registros de usuários a qualquer momento — preceito incompatível com a natureza estritamente imutável e perpétua da blockchain;
5. **Previsibilidade e Economia de Custos:** Operações onde custos operacionais devem ser estáveis e previsíveis sob modelos de licenciamento ou aluguel de servidores em nuvem, evitando taxas flutuantes de gas dependentes da congestão de mercado da rede.
