# Atividade Prática 4 — Carteira Digital com gRPC

**Disciplina:** Sistemas Distribuídos  
**Tema:** Comunicação RPC com gRPC e Protocol Buffers  
**Linguagem:** Python 3.x  

---

## Tema e Contexto

Este projeto implementa um serviço de **Carteira Digital** usando **gRPC** e **Protocol Buffers (proto3)**. O objetivo é explorar na prática os conceitos de chamada de procedimento remoto (RPC), contratos de interface tipados, mecanismos de deadline, concorrência com locking granular e evolução de contrato sem quebra de compatibilidade.

A atividade integra uma sequência de três paradigmas de comunicação distribuída estudados ao longo do semestre:

| AP | Protocolo | Paradigma              |
|----|-----------|------------------------|
| 2  | REST/HTTP  | Orientado a recursos   |
| 3  | MQTT       | Publish/Subscribe assíncrono |
| **4** | **gRPC** | **RPC síncrono tipado** |

---

## Estrutura de Arquivos

```
atividade_pratica4/
│
├── carteira/                        # Pacote principal da aplicação
│   ├── __init__.py                  # Injeta carteira/ no sys.path (fix para imports dos stubs)
│   ├── carteira.proto               # Contrato gRPC (fonte única da verdade)
│   ├── carteira_pb2.py              # Stubs gerados — classes de mensagens Protobuf
│   ├── carteira_pb2_grpc.py         # Stubs gerados — classes de serviço gRPC
│   ├── store.py                     # AccountStore: armazenamento em memória com locking por conta
│   ├── server.py                    # Servidor gRPC com todas as 5 RPCs implementadas
│   └── client.py                    # Cliente gRPC com deadline configurável e demo interativo
│
├── tests/
│   ├── __init__.py                  # Marca tests/ como pacote Python
│   └── test_carteira.py             # 18 testes unitários determinísticos (unittest + pytest)
│
├── scripts/
│   ├── run_experiments.py           # Runner dos 4 experimentos (Indisponibilidade, Deadline, Concorrência, Evolução)
│   └── run_server.ps1               # Script PowerShell para iniciar o servidor com parâmetros
│
├── relatorio/
│   └── analise.md                   # Relatório completo: comparativo, tabela de resultados e 5 questões analíticas
│
├── gerar_stubs.ps1                  # Geração dos stubs via grpc_tools.protoc (Windows)
├── gerar_stubs.sh                   # Geração dos stubs via grpc_tools.protoc (Linux/macOS)
├── requirements.txt                 # Dependências: grpcio, grpcio-tools, pytest
└── README.md                        # Este arquivo
```

---

## Contrato gRPC (`carteira.proto`)

O arquivo `.proto` define o **serviço `CarteiraService`** com 5 RPCs unárias:

| RPC              | Request              | Response             | Descrição                          |
|------------------|----------------------|----------------------|------------------------------------|
| `CriarConta`     | `CriarContaRequest`  | `TransacaoResponse`  | Cria conta com saldo inicial       |
| `ConsultarSaldo` | `ContaRequest`       | `SaldoResponse`      | Retorna saldo e dados do titular   |
| `Depositar`      | `TransacaoRequest`   | `TransacaoResponse`  | Adiciona valor ao saldo            |
| `Sacar`          | `TransacaoRequest`   | `TransacaoResponse`  | Subtrai valor do saldo             |
| `Transferir`     | `TransferirRequest`  | `TransacaoResponse`  | Move valor entre duas contas       |

O campo `moeda` no `TransacaoRequest` foi adicionado como campo `4` para demonstrar **evolução de contrato backward-compatible**.

---

## Arquitetura e Decisões de Design

### 1. Armazenamento (`store.py`) — Locking Granular

O `AccountStore` usa **dois níveis de lock** para maximizar a concorrência sem race conditions:

- **`_registry_lock`**: Lock global do dicionário — mantido apenas durante leitura/escrita de chaves (microssegundos).
- **`account["lock"]`**: Lock individual por conta — mantido durante a mutação do saldo. Dois threads em contas distintas **nunca competem** pelo mesmo lock.

**Prevenção de deadlock em `Transferir`**: Locks são sempre adquiridos em ordem lexicográfica (`sorted(conta_id)`), eliminando o ciclo clássico do *dining philosophers*.

### 2. Servidor (`server.py`) — Status Codes gRPC

O servidor mapeia validações para os 4 status codes exigidos pela atividade:

| Situação                             | Status Code gRPC        |
|--------------------------------------|-------------------------|
| Campos obrigatórios vazios / valor inválido | `INVALID_ARGUMENT` |
| Conta não encontrada                 | `NOT_FOUND`             |
| Conta já existe (duplicata)          | `ALREADY_EXISTS`        |
| Saldo insuficiente para saque/transferência | `FAILED_PRECONDITION` |

O flag `--delay` injeta latência artificial por requisição para os experimentos de deadline.

### 3. Cliente (`client.py`) — Deadline Propagado

Todas as chamadas recebem um parâmetro `timeout` (padrão: 5s). O gRPC propaga esse deadline via metadados HTTP/2 para o servidor, que interrompe o processamento se o prazo expirar.

### 4. Evolução de Contrato (Protobuf Backward Compatibility)

O campo `moeda = 4` foi adicionado ao `TransacaoRequest`. O servidor compilado **sem** esse campo ignora os bytes desconhecidos — o protocolo binário do Protobuf mapeia campos por número, não por nome, garantindo compatibilidade com consumidores antigos.

---

## Como Executar

### Pré-requisitos

```bash
pip install -r requirements.txt
```

### Gerar os stubs (após qualquer mudança no `.proto`)

```powershell
# Windows
.\gerar_stubs.ps1

# Linux/macOS
bash gerar_stubs.sh
```

### Iniciar o servidor

```bash
# Modo padrão
python carteira/server.py

# Com delay artificial (para experimentos de deadline)
python carteira/server.py --delay 3

# Com mais workers (para experimentos de concorrência)
python carteira/server.py --workers 20

# Via script PowerShell
.\scripts\run_server.ps1 -workers 20 -delay 3
```

### Executar o cliente demo

```bash
python carteira/client.py
# Ou com servidor remoto:
python carteira/client.py --host 192.168.1.10 --port 50051 --timeout 3
```

### Executar os testes automatizados

```bash
# A partir do diretório atividade_pratica4/
python -m pytest tests/test_carteira.py -v
```

> **Os testes são completamente autocontidos:** cada classe de teste sobe seu próprio servidor gRPC em porta efêmera (`port=0`) escolhida pelo OS, sem depender de servidor externo.

### Executar os experimentos

```bash
# Todos os experimentos (requer atenção ao estado do servidor — ver instruções no script)
python scripts/run_experiments.py

# Experimento específico
python scripts/run_experiments.py --exp 1   # Indisponibilidade (servidor parado)
python scripts/run_experiments.py --exp 2   # Deadline (servidor com --delay 3)
python scripts/run_experiments.py --exp 3   # Concorrência (servidor com --workers 20)
python scripts/run_experiments.py --exp 4   # Evolução de contrato
```

---

## Contas Pré-seeded (para testes)

O servidor inicia com 3 contas de teste:

| conta_id | Titular       | Saldo Inicial |
|----------|---------------|---------------|
| `001`    | Alice Silva   | R$ 1.000,00   |
| `002`    | Bruno Costa   | R$ 500,00     |
| `003`    | Carla Mendes  | R$ 250,00     |

---

## Testes Automatizados (18 testes)

| Classe              | Cenário Testado                                           |
|---------------------|-----------------------------------------------------------|
| `TestCriarConta`    | Sucesso, duplicata (ALREADY_EXISTS), saldo negativo, nome vazio |
| `TestConsultarSaldo`| Conta existente, inexistente (NOT_FOUND), ID vazio        |
| `TestDepositar`     | Sucesso, valor negativo, valor zero, conta inexistente    |
| `TestSacar`         | Sucesso, saldo insuficiente (FAILED_PRECONDITION), valor negativo |
| `TestTransferir`    | Sucesso atômico, mesma conta, saldo insuficiente          |
| `TestDeadline`      | DEADLINE_EXCEEDED quando timeout < delay do servidor      |

---

## Experimentos e Resultados

| #  | Experimento           | Método RPC                  | Status Observado     | Latência (ms) | Notas                                          |
|----|-----------------------|-----------------------------|----------------------|---------------|------------------------------------------------|
| 1  | Indisponibilidade     | ConsultarSaldo              | `UNAVAILABLE`        | 2300,4        | Servidor parado. Timeout de conexão           |
| 2a | Deadline (curto)      | Depositar (timeout=1s)      | `DEADLINE_EXCEEDED`  | 1030,4        | Delay no servidor=3s. Cliente cancela após 1s |
| 2b | Deadline (suficiente) | Depositar (timeout=5s)      | `OK`                 | 3004,2        | Delay no servidor=3s. Concluído no prazo      |
| 3  | Concorrência (20)     | Depositar ×20 simultâneos   | 20/20 `OK`           | 6,6           | Workers=20. Zero perdas                       |
| 4  | Evolução de Contrato  | Depositar (campo `moeda`)   | `OK`                 | 4,7           | Novo campo ignorado — backward-compatible      |

---

## Relatório Analítico

O arquivo [`relatorio/analise.md`](relatorio/analise.md) responde às 5 questões analíticas da atividade:

1. **Por que RPC ≠ função local?** — Falhas de rede, parcialidade, latência não determinística e o princípio das "8 Falácias da Computação Distribuída".
2. **Erro de aplicação vs. indisponibilidade** — Distinção entre status codes de negócio (`INVALID_ARGUMENT`, `FAILED_PRECONDITION`) e de infraestrutura (`UNAVAILABLE`, `DEADLINE_EXCEEDED`), e implicações para retry.
3. **Acoplamento de contrato forte** — *Schema coupling* introduzido pelo Protobuf, seu custo vs. benefício frente a REST/JSON.
4. **Retry sem duplicar efeitos** — Estratégia de *Idempotency Key* com UUID, registro de operações processadas e exponential backoff.
5. **Mudanças incompatíveis no `.proto`** — Renomear campos, mudar tipo, reutilizar números de campo e como usar `reserved` para mitigar o risco.

---

## Dependências

```
grpcio==1.66.1
grpcio-tools==1.66.1
pytest==8.3.3
```
