# Relatório Técnico — Atividade Prática 7 (AP7)
## Construindo uma Blockchain Didática Distribuída

**Disciplina:** Sistemas Distribuídos  
**Ambiente:** Python 3.10+ (FastAPI, Uvicorn, Requests)  
**Arquivos de Código:** [`blockchain.py`](blockchain.py), [`node.py`](node.py), [`demo.py`](demo.py)  

---

## 1. Introdução e Objetivos

Este relatório documenta a implementação da Atividade Prática 7 (AP7), na qual a estrutura de encadeamento criptográfico desenvolvida na AP6 foi estendida para um **sistema distribuído real**.

Nesta atividade, foram implementados:
1. **Proof of Work (PoW):** Mecanismo de custo computacional com meta de dificuldade baseada em prefixo de zeros.
2. **Nós HTTP Autônomos:** Servidores FastAPI executados em processos separados que se comunicam via API REST.
3. **Bifurcação Controlada (*Fork*):** Produção de blocos concorrentes em nós distintos a partir do mesmo ancestral.
4. **Reconciliação com Validação Prévia:** Algoritmo de resolução que valida cada bloco da cadeia remota antes de adotar o ramo mais longo.
5. **Tolerância a Falhas e Rejeição de Adulteração:** Resiliência contra peers indisponíveis e recusa de cadeias com dados corrompidos.

---

## 2. Arquitetura da Solução

O sistema foi estruturado de forma desacoplada em três módulos:

* **`blockchain.py`:** Contém as estruturas fundamentais (`Block` e `Blockchain`), com rotinas de serialização determinística, mineração com busca de `nonce` e método estático `valid_chain(chain, difficulty)` capaz de validar qualquer lista de blocos recebida pela rede.
* **`node.py`:** Expõe o nó como uma API REST (FastAPI) com endpoints para consulta da cadeia (`GET /chain`), mineração local (`POST /mine`), cadastro de vizinhos (`POST /peers`), validação de integridade (`GET /validate`), teste de adulteração (`POST /tamper`) e reconciliação distribuída (`POST /resolve`).
* **`demo.py`:** Script que automatiza o ciclo completo de testes em dois nós executados nas portas `8001` e `8002`.

---

## 3. Registro dos Experimentos e Evidências

Todos os passos foram executados entre o Nó 1 (`http://127.0.0.1:8001`) e o Nó 2 (`http://127.0.0.1:8002`).

### 3.1 Mineração com Proof of Work e Propagação Inicial
* Transação minerada no Nó 1: `{"origem": "Alice", "destino": "Bob", "valor": 50.0}`.
* Nonce encontrado: `179`.
* Hash resultante: `00b99d06134cbce098fa2cae1141819385e7b9d46e50474d2cf2acebf5a88da4` (inicia com `00`, atendendo à dificuldade `2`).
* Sincronização: O Nó 2 executou `/resolve`, validou o bloco e substituiu sua cadeia local, ficando ambos com comprimento 2 (Gênesis + Bloco #1).

### 3.2 Produção de Fork Controlado
Com a base comum no Bloco #1, foram gerados blocos concorrentes em cada nó:
* **Nó 1 (Bloco #2A):** `{"origem": "Alice", "destino": "Carol", "valor": 15.0}`  
  * Nonce: `1192` | Hash: `0087c1c468746d747a7a2b944004886a7d4c43f0197bc5c48f0483c13bb5b455`
* **Nó 2 (Bloco #2B):** `{"origem": "Bob", "destino": "Dave", "valor": 25.0}`  
  * Nonce: `78` | Hash: `00e422a7e52f24830c4c448e31f6c19d91a6ae74f89e43763257f2ad962b7bbd`

Ambos os blocos apontam para o mesmo `previous_hash` (`00b99d06134c...`), configurando formalmente uma bifurcação (*fork*).

### 3.3 Alongamento do Ramo B e Reconciliação
1. O Nó 2 minerou o Bloco #3B (`Dave -> Eve`, valor `10.0`, Nonce `73`, Hash `00805a9b...`), ficando com comprimento 4 contra 3 do Nó 1.
2. O Nó 1 executou `POST /resolve`. O Nó 1 baixou a cadeia do Nó 2, reconstruiu os objetos `Block`, verificou que todos os hashes e nonces eram válidos e adotou a cadeia do Nó 2 por ser mais longa.
3. O Bloco #2A do Nó 1 foi descartado (reorganização de histórico), prevalecendo os blocos #2B e #3B.

### 3.4 Teste de Adulteração e Rejeição
* O Bloco #1 do Nó 2 foi deliberadamente adulterado via `/tamper`, alterando seu valor para `999999.99`.
* A validação interna do Nó 2 passou a retornar `valid: False` (`hash armazenado difere do recalculado`).
* O Nó 1 acionou `/resolve` contra o Nó 2. O algoritmo de validação do Nó 1 detectou a violação matemática na cadeia remota e **rejeitou a substituição**, preservando sua cadeia local intacta.

### 3.5 Resiliência a Nós Offline
* Cadastrou-se no Nó 1 um peer inexistente (`http://127.0.0.1:8999`).
* O endpoint `/resolve` tratou o timeout da requisição via bloco `except requests.RequestException` e concluiu o ciclo sem travamento ou queda do processo.

---

## 4. Tabela de Limitações: Protótipo vs. Blockchain Real

| Dimensão | Protótipo Didático (AP7) | Blockchain de Produção (ex.: Bitcoin) |
| :--- | :--- | :--- |
| **Autoria e Integridade de Transações** | Strings em texto claro (`origem`, `destino`) sem assinatura | Criptografia assimétrica (ECDSA / Schnorr); apenas o dono da chave privada pode gastar |
| **Validação de Saldo** | Não verifica saldo contábil nem histórico prévio de fundos | Modelo UTXO ou balanço de contas com prevenção estrita de saldo negativo |
| **Mempool e Fila** | Sem fila de espera; cada requisição gera imediatamente um bloco | Mempool compartilhado P2P com priorização por taxas e reinjeção de transações órfãs |
| **Topologia de Rede** | HTTP REST ponto a ponto com cadastro manual via `/peers` | Rede P2P descentralizada com nós semente (*seed nodes*) e protocolo de fofoca (*Gossip*) |
| **Ajuste de Dificuldade** | Dificuldade fixa (`difficulty = 2`) | Ajuste dinâmico a cada 2016 blocos para estabilizar o tempo médio de mineração |
| **Proteção contra Ataques Sybil** | Inexistente (qualquer um pode criar nós locais livremente) | Custo energético contínuo no PoW ou garantia financeira substancial no PoS |
| **Persistência de Dados** | Estado volátil mantido em memória RAM | Banco de dados embarcado em disco (LevelDB ou RocksDB) com recuperação após falha |

---

## 5. Respostas às Questões para Análise

### Questão 1: Que propriedade o Proof of Work acrescentou ao simples encadeamento?
O encadeamento por hash garante apenas que qualquer alteração pontual em um bloco invalide o ponteiro do bloco seguinte. No entanto, em um computador comum, recalcular ponteiros SHA-256 é computacionalmente trivial (consome frações de milissegundo).

O **Proof of Work introduz assimetria computacional**: gerar um bloco novo exige realizar em média centenas ou milhares de iterações de teste de `nonce` até encontrar um hash com a quantidade de zeros estipulada pela dificuldade. Em contrapartida, validar se o bloco atende ao critério requer apenas uma única operação de hash. Isso impede que um invasor isolado reescreva blocos antigos com facilidade, pois ele precisaria refazer o trabalho acumulado de toda a cadeia enquanto o restante da rede continua avançando.

### Questão 2: Sua regra de reconciliação pode perder transações?
**Sim.** A regra da cadeia mais longa (*Longest Chain Rule*) descarta integralmente o ramo menor (*orphaned branch*). Se o bloco abandonado continha transações que não foram incluídas no ramo vencedor (como ocorreu com a transação `Alice -> Carol` do Bloco #2A), esses dados deixam de existir no histórico canônico da rede.

Em blockchains de produção, esse problema é mitigado pelo **mempool**: quando ocorre uma reorganização de cadeia, as transações pertencentes aos blocos órfãos retornam automaticamente à fila de espera para serem incluídas nos blocos seguintes.

### Questão 3: Como um nó malicioso poderia explorar sua implementação?
A implementação didática apresenta três superfícies de ataque evidentes:
1. **Forja de Transações:** Não há verificação de assinatura digital. Qualquer cliente pode emitir uma requisição `POST /mine` fingindo ser qualquer usuário e transferir valores que não lhe pertencem.
2. **Ataque de Reorganização Arbitrária (51% Didático):** Como a dificuldade é baixa e fixa, um nó com capacidade de processamento ligeiramente superior pode minerar silenciosamente uma cadeia privada mais longa e forçar todos os outros nós a descartarem suas transações legítimas ao chamar `/resolve`.
3. **Exaustão de Recursos no `/resolve`:** Um peer malicioso pode expor um endpoint `/chain` que retorna listas infinitas ou blocos maliciosamente construídos para estourar a memória RAM do nó receptor durante a desserialização.

### Questão 4: O que seria necessário para autenticar autoria de transações?
Seria necessário adotar **criptografia de chave pública (assimétrica)**:
* Cada participante da rede possuiria um par de chaves (pública e privada). O endereço da carteira seria derivado da chave pública.
* Para realizar uma transferência, o emissor criaria a transação e a assinaria digitalmente utilizando sua chave privada.
* Antes de minerar ou aceitar um bloco, cada nó usaria a chave pública do remetente para verificar matematicamente se a assinatura é válida. Sem a chave privada, nenhum invasor conseguiria forjar uma movimentação em nome de outro usuário.

### Questão 5: Quais condições de rede podem manter forks temporários?
Forks temporários ocorrem e se sustentam sob as seguintes condições:
1. **Alta Latência e Assimetria de Propagação:** Quando o tempo necessário para um bloco viajar pela rede física é próximo ou superior ao tempo médio de mineração de novos blocos, mineradores distantes encontram soluções quase ao mesmo tempo e propagam blocos concorrentes para metades diferentes da rede.
2. **Partição de Rede (*Network Split*):** Falhas em roteadores ou cabos submarinos podem isolar grupos de nós em regiões geográficas distintas. Cada partição continuará minerando sua própria versão da cadeia de forma independente até que a conectividade seja restabelecida.
3. **Perda de Pacotes e Jitter:** Atrasos na entrega de mensagens entre nós mineradores retardam a notificação de novos blocos, permitindo que nós continuem trabalhando sobre blocos que já foram superados em outras partes da rede.

---

## 6. Conclusão

A AP7 demonstrou que a transição de uma cadeia de blocos local para uma blockchain distribuída exige **mecanismos de coordenação que combinam criptografia (hashing), custo de consenso (Proof of Work) e protocolos de comunicação em rede resilientes a falhas**. O protótipo atendeu a todos os requisitos didáticos de funcionamento, evidenciando simultaneamente as razões pelas quais redes reais demandam assinaturas assimétricas, mempool compartilhado e regras de descoberta descentralizadas.
