# Plano de Implementação — AP4: Serviço de Carteira Digital com gRPC

## Contexto e Decisões Técnicas

| Decisão               | Escolha                                      |
|-----------------------|----------------------------------------------|
| Linguagem             | Python 3.x                                   |
| Estilo do Servidor    | Síncrono com `ThreadPoolExecutor`            |
| Estado das Contas     | Dicionário em memória (sem persistência)     |
| Gerenciamento de Deps | `pip` + `requirements.txt`                   |
| Framework de Testes   | `pytest`                                     |
| Questões Teóricas     | Respostas redigidas e prontas para entrega   |

**Diretório raiz do projeto:** `d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4\`

---

## Estrutura Final de Arquivos

```
atividade_pratica4/
├── Atividade Prática 4 - SD.pdf   (arquivo existente — não modificar)
├── carteira/
│   ├── carteira.proto              (FASE 1 — contrato gRPC)
│   ├── carteira_pb2.py             (FASE 2 — gerado automaticamente)
│   ├── carteira_pb2_grpc.py        (FASE 2 — gerado automaticamente)
│   ├── server.py                   (FASE 3 — implementação do servidor)
│   └── client.py                   (FASE 4 — implementação do cliente)
├── tests/
│   └── test_carteira.py            (FASE 5 — testes automatizados com pytest)
├── scripts/
│   ├── run_server.sh               (FASE 6 — script helper para Linux/Mac)
│   ├── run_server.ps1              (FASE 6 — script helper para Windows)
│   └── run_experiments.py          (FASE 6 — script dos 4 experimentos)
├── requirements.txt                (FASE 1 — dependências)
├── gerar_stubs.sh                  (FASE 2 — script de geração dos stubs Linux)
├── gerar_stubs.ps1                 (FASE 2 — script de geração dos stubs Windows)
└── relatorio/
    └── analise.md                  (FASE 7 — relatório com tabelas e respostas)
```

---

## FASE 1 — Dependências e Contrato `.proto`

**Objetivo:** Criar o `requirements.txt` e o arquivo de contrato `carteira.proto` com pelo menos 3 métodos RPC e 3 tipos de mensagens.

### Passo 1.1 — Criar `requirements.txt`

**Arquivo:** `atividade_pratica4/requirements.txt`

```
grpcio==1.66.1
grpcio-tools==1.66.1
pytest==8.3.3
```

> **Comando de instalação (executar uma vez):**
> ```powershell
> cd d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4
> pip install -r requirements.txt
> ```

### Passo 1.2 — Criar o diretório `carteira/`

```powershell
mkdir carteira
mkdir tests
mkdir scripts
mkdir relatorio
```

### Passo 1.3 — Criar `carteira/carteira.proto`

**Arquivo:** `atividade_pratica4/carteira/carteira.proto`

```proto
syntax = "proto3";

package carteira;

// ─────────────────────────────────────────────
// Mensagens de Requisição
// ─────────────────────────────────────────────

// Usada para identificar uma conta (consulta de saldo)
message ContaRequest {
  string conta_id = 1;
}

// Usada para operações de depósito e saque
message TransacaoRequest {
  string conta_id = 1;
  double valor    = 2;
  string descricao = 3; // campo descritivo opcional
}

// Usada para criar uma nova conta
message CriarContaRequest {
  string conta_id       = 1;
  string nome_titular   = 2;
  double saldo_inicial  = 3;
}

// ─────────────────────────────────────────────
// Mensagens de Resposta
// ─────────────────────────────────────────────

// Resposta padrão para operações de transação e criação
message TransacaoResponse {
  string conta_id      = 1;
  double saldo_atual   = 2;
  string mensagem      = 3;
}

// Resposta para consulta de saldo
message SaldoResponse {
  string conta_id      = 1;
  string nome_titular  = 2;
  double saldo_atual   = 3;
}

// ─────────────────────────────────────────────
// Definição do Serviço
// ─────────────────────────────────────────────

service CarteiraService {
  // Cria uma nova conta com saldo inicial
  rpc CriarConta (CriarContaRequest) returns (TransacaoResponse);

  // Consulta o saldo e dados de uma conta existente
  rpc ConsultarSaldo (ContaRequest) returns (SaldoResponse);

  // Realiza um depósito em uma conta
  rpc Depositar (TransacaoRequest) returns (TransacaoResponse);

  // Realiza um saque de uma conta
  rpc Sacar (TransacaoRequest) returns (TransacaoResponse);

  // Transfere valor entre duas contas
  rpc Transferir (TransferirRequest) returns (TransacaoResponse);
}

// Mensagem adicional para transferência entre contas
message TransferirRequest {
  string conta_origem  = 1;
  string conta_destino = 2;
  double valor         = 3;
}
```

> **Resumo do contrato:**
> - **6 métodos RPC** (supera o mínimo de 3): `CriarConta`, `ConsultarSaldo`, `Depositar`, `Sacar`, `Transferir`
> - **6 tipos de mensagens** (supera o mínimo de 3): `ContaRequest`, `TransacaoRequest`, `CriarContaRequest`, `TransacaoResponse`, `SaldoResponse`, `TransferirRequest`

---

## FASE 2 — Geração dos Stubs (Arquivos Gerados)

**Objetivo:** Gerar os arquivos `carteira_pb2.py` e `carteira_pb2_grpc.py` a partir do `.proto` de forma reproduzível.

### Passo 2.1 — Criar `gerar_stubs.ps1` (Windows PowerShell)

**Arquivo:** `atividade_pratica4/gerar_stubs.ps1`

```powershell
# Script para geração dos stubs gRPC a partir do arquivo .proto
# Executar a partir do diretório atividade_pratica4/
# Pré-requisito: pip install -r requirements.txt

Write-Host "Gerando stubs gRPC para carteira.proto..." -ForegroundColor Cyan

python -m grpc_tools.protoc `
  --proto_path=carteira `
  --python_out=carteira `
  --grpc_python_out=carteira `
  carteira/carteira.proto

if ($LASTEXITCODE -eq 0) {
    Write-Host "Stubs gerados com sucesso em carteira/!" -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2.py" -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2_grpc.py" -ForegroundColor Green
} else {
    Write-Host "Erro na geração dos stubs. Verifique o .proto e as dependências." -ForegroundColor Red
}
```

### Passo 2.2 — Criar `gerar_stubs.sh` (Linux/Mac — para referência)

**Arquivo:** `atividade_pratica4/gerar_stubs.sh`

```bash
#!/bin/bash
# Script para geração dos stubs gRPC a partir do arquivo .proto
# Executar a partir do diretório atividade_pratica4/

echo "Gerando stubs gRPC para carteira.proto..."

python -m grpc_tools.protoc \
  --proto_path=carteira \
  --python_out=carteira \
  --grpc_python_out=carteira \
  carteira/carteira.proto

echo "Stubs gerados em carteira/"
```

### Passo 2.3 — Executar a geração

```powershell
# No diretório atividade_pratica4/
.\gerar_stubs.ps1
```

> **Atenção:** Os arquivos `carteira_pb2.py` e `carteira_pb2_grpc.py` são **gerados automaticamente** e **não devem ser editados manualmente**. O agente executor deve verificar se esses dois arquivos foram criados na pasta `carteira/` após a execução.

### Passo 2.4 — Criar `carteira/__init__.py`

Para que o diretório funcione como pacote Python, crie um arquivo vazio:

**Arquivo:** `atividade_pratica4/carteira/__init__.py`

```python
# Pacote carteira — gerado pelo contrato gRPC carteira.proto
```

---

## FASE 3 — Implementação do Servidor

**Objetivo:** Implementar o servidor gRPC com `ThreadPoolExecutor`, com validação de erros (mínimo 2 códigos de status distintos) e controle de concorrência.

**Arquivo:** `atividade_pratica4/carteira/server.py`

```python
"""
Servidor gRPC — Serviço de Carteira Digital
Atividade Prática 4 — Sistemas Distribuídos

Características:
  - Armazenamento em memória (dicionário Python)
  - Estilo síncrono com ThreadPoolExecutor
  - Validação com pelo menos 2 códigos de status gRPC distintos
  - Suporte a controle de concorrência via parâmetro max_workers
"""

import time
import threading
import grpc
from concurrent import futures

import carteira_pb2
import carteira_pb2_grpc


# ─────────────────────────────────────────────────────────────────────────────
# Armazenamento em memória
# ─────────────────────────────────────────────────────────────────────────────
# Formato: { conta_id: { "nome_titular": str, "saldo": float } }
contas: dict = {}
contas_lock = threading.Lock()  # Lock para acesso seguro em cenário concorrente


# ─────────────────────────────────────────────────────────────────────────────
# Dados iniciais (seed) — facilita os testes
# ─────────────────────────────────────────────────────────────────────────────
CONTAS_INICIAIS = [
    {"conta_id": "001", "nome_titular": "Alice Silva",  "saldo": 1000.00},
    {"conta_id": "002", "nome_titular": "Bruno Costa",  "saldo": 500.00},
    {"conta_id": "003", "nome_titular": "Carla Mendes", "saldo": 250.00},
]


def inicializar_contas():
    """Preenche o dicionário com as contas iniciais ao subir o servidor."""
    with contas_lock:
        for c in CONTAS_INICIAIS:
            contas[c["conta_id"]] = {
                "nome_titular": c["nome_titular"],
                "saldo": c["saldo"],
            }
    print("[SERVIDOR] Contas inicializadas:", list(contas.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# Implementação do Serviço
# ─────────────────────────────────────────────────────────────────────────────

class CarteiraServicer(carteira_pb2_grpc.CarteiraServiceServicer):
    """
    Implementa todos os métodos definidos em carteira.proto.

    Códigos de status gRPC utilizados:
      - grpc.StatusCode.INVALID_ARGUMENT  → valor inválido (negativo ou zero)
      - grpc.StatusCode.NOT_FOUND         → conta inexistente
      - grpc.StatusCode.ALREADY_EXISTS    → conta já cadastrada
      - grpc.StatusCode.FAILED_PRECONDITION → saldo insuficiente
    """

    # ------------------------------------------------------------------
    # CriarConta
    # ------------------------------------------------------------------
    def CriarConta(self, request, context):
        """
        Cria uma nova conta com saldo inicial.
        Erros:
          - ALREADY_EXISTS se conta_id já existe.
          - INVALID_ARGUMENT se nome_titular estiver vazio ou saldo_inicial < 0.
        """
        conta_id = request.conta_id.strip()
        nome = request.nome_titular.strip()
        saldo_inicial = request.saldo_inicial

        # Validação 1 — argumentos obrigatórios
        if not conta_id or not nome:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_id e nome_titular são obrigatórios e não podem ser vazios.",
            )

        # Validação 2 — saldo inicial não pode ser negativo
        if saldo_inicial < 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"saldo_inicial não pode ser negativo. Recebido: {saldo_inicial}",
            )

        with contas_lock:
            # Validação 3 — conta já existente
            if conta_id in contas:
                context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    f"Conta '{conta_id}' já existe.",
                )

            contas[conta_id] = {"nome_titular": nome, "saldo": saldo_inicial}
            saldo = contas[conta_id]["saldo"]

        print(f"[CriarConta] conta={conta_id}, titular={nome}, saldo_inicial={saldo_inicial:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=saldo,
            mensagem=f"Conta '{conta_id}' criada com sucesso para {nome}.",
        )

    # ------------------------------------------------------------------
    # ConsultarSaldo
    # ------------------------------------------------------------------
    def ConsultarSaldo(self, request, context):
        """
        Consulta o saldo de uma conta.
        Erros:
          - INVALID_ARGUMENT se conta_id estiver vazio.
          - NOT_FOUND se conta não existir.
        """
        conta_id = request.conta_id.strip()

        if not conta_id:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_id é obrigatório.",
            )

        with contas_lock:
            if conta_id not in contas:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Conta '{conta_id}' não encontrada.",
                )
            conta = contas[conta_id]

        print(f"[ConsultarSaldo] conta={conta_id}, saldo={conta['saldo']:.2f}")
        return carteira_pb2.SaldoResponse(
            conta_id=conta_id,
            nome_titular=conta["nome_titular"],
            saldo_atual=conta["saldo"],
        )

    # ------------------------------------------------------------------
    # Depositar
    # ------------------------------------------------------------------
    def Depositar(self, request, context):
        """
        Deposita um valor em uma conta.
        Erros:
          - INVALID_ARGUMENT se valor <= 0.
          - NOT_FOUND se conta não existir.
        """
        conta_id = request.conta_id.strip()
        valor = request.valor

        # Validação — valor deve ser positivo
        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"O valor do depósito deve ser positivo. Recebido: {valor}",
            )

        with contas_lock:
            if conta_id not in contas:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Conta '{conta_id}' não encontrada.",
                )
            contas[conta_id]["saldo"] += valor
            novo_saldo = contas[conta_id]["saldo"]

        print(f"[Depositar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Depósito de R$ {valor:.2f} realizado com sucesso.",
        )

    # ------------------------------------------------------------------
    # Sacar
    # ------------------------------------------------------------------
    def Sacar(self, request, context):
        """
        Saca um valor de uma conta.
        Erros:
          - INVALID_ARGUMENT se valor <= 0.
          - NOT_FOUND se conta não existir.
          - FAILED_PRECONDITION se saldo insuficiente.
        """
        conta_id = request.conta_id.strip()
        valor = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"O valor do saque deve ser positivo. Recebido: {valor}",
            )

        with contas_lock:
            if conta_id not in contas:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Conta '{conta_id}' não encontrada.",
                )
            saldo_atual = contas[conta_id]["saldo"]
            if saldo_atual < valor:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"Saldo insuficiente. Saldo atual: R$ {saldo_atual:.2f}, tentativa de saque: R$ {valor:.2f}",
                )
            contas[conta_id]["saldo"] -= valor
            novo_saldo = contas[conta_id]["saldo"]

        print(f"[Sacar] conta={conta_id}, valor={valor:.2f}, novo_saldo={novo_saldo:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=conta_id,
            saldo_atual=novo_saldo,
            mensagem=f"Saque de R$ {valor:.2f} realizado com sucesso.",
        )

    # ------------------------------------------------------------------
    # Transferir
    # ------------------------------------------------------------------
    def Transferir(self, request, context):
        """
        Transfere um valor entre duas contas.
        Erros:
          - INVALID_ARGUMENT se valor <= 0 ou contas idênticas.
          - NOT_FOUND se qualquer uma das contas não existir.
          - FAILED_PRECONDITION se saldo insuficiente na conta de origem.
        """
        origem = request.conta_origem.strip()
        destino = request.conta_destino.strip()
        valor = request.valor

        if valor <= 0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"O valor da transferência deve ser positivo. Recebido: {valor}",
            )

        if origem == destino:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "conta_origem e conta_destino não podem ser iguais.",
            )

        with contas_lock:
            if origem not in contas:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Conta de origem '{origem}' não encontrada.")
            if destino not in contas:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Conta de destino '{destino}' não encontrada.")

            saldo_origem = contas[origem]["saldo"]
            if saldo_origem < valor:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"Saldo insuficiente na conta de origem '{origem}'. Saldo: R$ {saldo_origem:.2f}",
                )

            contas[origem]["saldo"] -= valor
            contas[destino]["saldo"] += valor
            novo_saldo_origem = contas[origem]["saldo"]

        print(f"[Transferir] origem={origem} -> destino={destino}, valor={valor:.2f}")
        return carteira_pb2.TransacaoResponse(
            conta_id=origem,
            saldo_atual=novo_saldo_origem,
            mensagem=f"Transferência de R$ {valor:.2f} de '{origem}' para '{destino}' realizada com sucesso.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Inicialização do Servidor
# ─────────────────────────────────────────────────────────────────────────────

def serve(port: int = 50051, max_workers: int = 10, delay_segundos: float = 0.0):
    """
    Inicia o servidor gRPC.
    
    Parâmetros:
      port          : Porta TCP a escutar (padrão 50051)
      max_workers   : Número de threads no pool (experimento de concorrência)
      delay_segundos: Atraso artificial por requisição (experimento de deadline)
    """
    # Injetar delay artificial nas chamadas — experimento de deadline
    if delay_segundos > 0:
        print(f"[AVISO] Modo de delay ativado: {delay_segundos}s por requisição")
        original_depositar = CarteiraServicer.Depositar

        def depositar_com_delay(self, request, context):
            time.sleep(delay_segundos)
            return original_depositar(self, request, context)

        CarteiraServicer.Depositar = depositar_com_delay

    inicializar_contas()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(CarteiraServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()

    print(f"[SERVIDOR] Carteira Digital iniciado na porta {port} com {max_workers} worker(s).")
    print("[SERVIDOR] Pressione Ctrl+C para encerrar.")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando graciosamente...")
        server.stop(grace=5)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Servidor gRPC — Carteira Digital")
    parser.add_argument("--port",    type=int,   default=50051,  help="Porta TCP (padrão: 50051)")
    parser.add_argument("--workers", type=int,   default=10,     help="Número de workers (padrão: 10)")
    parser.add_argument("--delay",   type=float, default=0.0,    help="Delay artificial em segundos por req (padrão: 0)")
    args = parser.parse_args()

    serve(port=args.port, max_workers=args.workers, delay_segundos=args.delay)
```

---

## FASE 4 — Implementação do Cliente

**Objetivo:** Implementar o cliente gRPC com suporte a **deadlines** configuráveis.

**Arquivo:** `atividade_pratica4/carteira/client.py`

```python
"""
Cliente gRPC — Serviço de Carteira Digital
Atividade Prática 4 — Sistemas Distribuídos

Características:
  - Todas as chamadas utilizam deadline (timeout)
  - Erros gRPC são capturados e exibidos com código de status
  - Funções reutilizáveis por outros scripts (ex: run_experiments.py)
"""

import grpc
import carteira_pb2
import carteira_pb2_grpc

DEFAULT_HOST    = "localhost"
DEFAULT_PORT    = 50051
DEFAULT_TIMEOUT = 5.0  # segundos — deadline padrão


def get_stub(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Cria e retorna um stub (proxy) para o CarteiraService."""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = carteira_pb2_grpc.CarteiraServiceStub(channel)
    return stub, channel


def criar_conta(stub, conta_id: str, nome_titular: str, saldo_inicial: float, timeout: float = DEFAULT_TIMEOUT):
    """Chama o RPC CriarConta com deadline."""
    try:
        req = carteira_pb2.CriarContaRequest(
            conta_id=conta_id,
            nome_titular=nome_titular,
            saldo_inicial=saldo_inicial,
        )
        resp = stub.CriarConta(req, timeout=timeout)
        print(f"[CriarConta] ✓ {resp.mensagem} | Saldo: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as e:
        print(f"[CriarConta] ✗ ERRO [{e.code().name}]: {e.details()}")
        return None


def consultar_saldo(stub, conta_id: str, timeout: float = DEFAULT_TIMEOUT):
    """Chama o RPC ConsultarSaldo com deadline."""
    try:
        req = carteira_pb2.ContaRequest(conta_id=conta_id)
        resp = stub.ConsultarSaldo(req, timeout=timeout)
        print(f"[ConsultarSaldo] ✓ Conta: {resp.conta_id} | Titular: {resp.nome_titular} | Saldo: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as e:
        print(f"[ConsultarSaldo] ✗ ERRO [{e.code().name}]: {e.details()}")
        return None


def depositar(stub, conta_id: str, valor: float, descricao: str = "", timeout: float = DEFAULT_TIMEOUT):
    """Chama o RPC Depositar com deadline."""
    try:
        req = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Depositar(req, timeout=timeout)
        print(f"[Depositar] ✓ {resp.mensagem} | Novo saldo: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as e:
        print(f"[Depositar] ✗ ERRO [{e.code().name}]: {e.details()}")
        return None


def sacar(stub, conta_id: str, valor: float, descricao: str = "", timeout: float = DEFAULT_TIMEOUT):
    """Chama o RPC Sacar com deadline."""
    try:
        req = carteira_pb2.TransacaoRequest(conta_id=conta_id, valor=valor, descricao=descricao)
        resp = stub.Sacar(req, timeout=timeout)
        print(f"[Sacar] ✓ {resp.mensagem} | Novo saldo: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as e:
        print(f"[Sacar] ✗ ERRO [{e.code().name}]: {e.details()}")
        return None


def transferir(stub, conta_origem: str, conta_destino: str, valor: float, timeout: float = DEFAULT_TIMEOUT):
    """Chama o RPC Transferir com deadline."""
    try:
        req = carteira_pb2.TransferirRequest(
            conta_origem=conta_origem,
            conta_destino=conta_destino,
            valor=valor,
        )
        resp = stub.Transferir(req, timeout=timeout)
        print(f"[Transferir] ✓ {resp.mensagem} | Saldo origem: R$ {resp.saldo_atual:.2f}")
        return resp
    except grpc.RpcError as e:
        print(f"[Transferir] ✗ ERRO [{e.code().name}]: {e.details()}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Demo interativa — executar diretamente
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cliente gRPC — Carteira Digital")
    parser.add_argument("--host",    type=str,   default=DEFAULT_HOST,    help="Host do servidor")
    parser.add_argument("--port",    type=int,   default=DEFAULT_PORT,    help="Porta do servidor")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Deadline em segundos")
    args = parser.parse_args()

    print(f"\n=== Cliente Carteira Digital | {args.host}:{args.port} | timeout={args.timeout}s ===\n")

    stub, channel = get_stub(args.host, args.port)

    with channel:
        # --- Operações normais ---
        print("─── Criando nova conta ───")
        criar_conta(stub, "099", "Diego Teste", 100.0)

        print("\n─── Consultando saldos iniciais ───")
        consultar_saldo(stub, "001")
        consultar_saldo(stub, "002")

        print("\n─── Depósito ───")
        depositar(stub, "001", 250.0, "Salário")

        print("\n─── Saque ───")
        sacar(stub, "001", 100.0, "Aluguel")

        print("\n─── Transferência ───")
        transferir(stub, "001", "002", 50.0)

        # --- Erros esperados ---
        print("\n─── Erros esperados ───")

        print("\n[Teste] Consultar conta inexistente (NOT_FOUND):")
        consultar_saldo(stub, "999")

        print("\n[Teste] Depósito com valor negativo (INVALID_ARGUMENT):")
        depositar(stub, "001", -50.0)

        print("\n[Teste] Saque com saldo insuficiente (FAILED_PRECONDITION):")
        sacar(stub, "003", 99999.0)

        print("\n[Teste] Criar conta já existente (ALREADY_EXISTS):")
        criar_conta(stub, "001", "Alice Duplicada", 0.0)

    print("\n=== Fim da Demo ===\n")
```

---

## FASE 5 — Testes Automatizados com pytest

**Objetivo:** Criar testes automatizados que verificam o comportamento correto do servidor (sem precisar de um servidor externo rodando — usando canal em processo).

**Arquivo:** `atividade_pratica4/tests/test_carteira.py`

```python
"""
Testes automatizados — Serviço de Carteira Digital (gRPC)
Atividade Prática 4 — Sistemas Distribuídos

Estratégia: Inicializa um servidor gRPC real em uma thread de background
no setUp de cada teste, garantindo isolamento e independência.
"""

import sys
import os
import threading
import time
import unittest

import grpc
from concurrent import futures

# Adicionar o diretório carteira ao path para importar os módulos gerados
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "carteira"))

import carteira_pb2
import carteira_pb2_grpc
from server import CarteiraServicer, inicializar_contas, contas, contas_lock


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: servidor gRPC em thread de background para testes
# ─────────────────────────────────────────────────────────────────────────────

class CarteiraTestCase(unittest.TestCase):
    """Classe base que sobe/derruba um servidor gRPC para cada test case."""

    server = None
    stub   = None
    channel = None
    PORT   = 50099  # Porta separada para não conflitar com o servidor real

    @classmethod
    def setUpClass(cls):
        """Inicializa o servidor gRPC uma vez para todos os testes da classe."""
        # Limpar e re-inicializar contas
        with contas_lock:
            contas.clear()
        inicializar_contas()

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
        carteira_pb2_grpc.add_CarteiraServiceServicer_to_server(CarteiraServicer(), cls.server)
        cls.server.add_insecure_port(f"[::]:{cls.PORT}")
        cls.server.start()

        cls.channel = grpc.insecure_channel(f"localhost:{cls.PORT}")
        cls.stub    = carteira_pb2_grpc.CarteiraServiceStub(cls.channel)

        # Aguardar o servidor estar pronto
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        """Encerra o servidor após todos os testes."""
        cls.channel.close()
        cls.server.stop(grace=2)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de CriarConta
# ─────────────────────────────────────────────────────────────────────────────

class TestCriarConta(CarteiraTestCase):

    def test_criar_conta_sucesso(self):
        """Deve criar conta com saldo inicial e retornar TransacaoResponse."""
        resp = self.stub.CriarConta(
            carteira_pb2.CriarContaRequest(conta_id="T01", nome_titular="Teste Um", saldo_inicial=500.0),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "T01")
        self.assertAlmostEqual(resp.saldo_atual, 500.0)
        self.assertIn("T01", resp.mensagem)

    def test_criar_conta_duplicada_retorna_already_exists(self):
        """Deve retornar ALREADY_EXISTS ao criar conta com ID já existente."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="001", nome_titular="Duplamente Alice", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.ALREADY_EXISTS)

    def test_criar_conta_saldo_negativo_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT ao criar conta com saldo inicial negativo."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T99", nome_titular="Inválido", saldo_inicial=-100.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_criar_conta_sem_nome_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT ao criar conta sem nome do titular."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.CriarConta(
                carteira_pb2.CriarContaRequest(conta_id="T98", nome_titular="", saldo_inicial=0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de ConsultarSaldo
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultarSaldo(CarteiraTestCase):

    def test_consultar_saldo_conta_existente(self):
        """Deve retornar SaldoResponse com dados corretos para conta existente."""
        resp = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"),
            timeout=5,
        )
        self.assertEqual(resp.conta_id, "001")
        self.assertEqual(resp.nome_titular, "Alice Silva")
        self.assertGreaterEqual(resp.saldo_atual, 0)

    def test_consultar_saldo_conta_inexistente_retorna_not_found(self):
        """Deve retornar NOT_FOUND para conta que não existe."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id="999"),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)

    def test_consultar_saldo_conta_vazia_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT se conta_id for vazio."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id=""),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Depositar
# ─────────────────────────────────────────────────────────────────────────────

class TestDepositar(CarteiraTestCase):

    def test_depositar_sucesso(self):
        """Deve aumentar o saldo após depósito válido."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="002"), timeout=5
        ).saldo_atual

        resp = self.stub.Depositar(
            carteira_pb2.TransacaoRequest(conta_id="002", valor=100.0, descricao="Teste"),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes + 100.0, places=2)

    def test_depositar_valor_negativo_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT para depósito com valor negativo."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_valor_zero_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT para depósito com valor zero."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=0.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_depositar_conta_inexistente_retorna_not_found(self):
        """Deve retornar NOT_FOUND ao depositar em conta inexistente."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Depositar(
                carteira_pb2.TransacaoRequest(conta_id="999", valor=50.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Sacar
# ─────────────────────────────────────────────────────────────────────────────

class TestSacar(CarteiraTestCase):

    def test_sacar_sucesso(self):
        """Deve reduzir o saldo após saque válido."""
        saldo_antes = self.stub.ConsultarSaldo(
            carteira_pb2.ContaRequest(conta_id="001"), timeout=5
        ).saldo_atual

        resp = self.stub.Sacar(
            carteira_pb2.TransacaoRequest(conta_id="001", valor=50.0),
            timeout=5,
        )
        self.assertAlmostEqual(resp.saldo_atual, saldo_antes - 50.0, places=2)

    def test_sacar_saldo_insuficiente_retorna_failed_precondition(self):
        """Deve retornar FAILED_PRECONDITION ao sacar mais do que o saldo disponível."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="003", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)

    def test_sacar_valor_negativo_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT para saque com valor negativo."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Sacar(
                carteira_pb2.TransacaoRequest(conta_id="001", valor=-10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Transferir
# ─────────────────────────────────────────────────────────────────────────────

class TestTransferir(CarteiraTestCase):

    def test_transferir_sucesso(self):
        """Deve debitar origem e creditar destino na transferência."""
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

    def test_transferir_conta_igual_retorna_invalid_argument(self):
        """Deve retornar INVALID_ARGUMENT ao transferir para a mesma conta."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="001", conta_destino="001", valor=10.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_transferir_saldo_insuficiente_retorna_failed_precondition(self):
        """Deve retornar FAILED_PRECONDITION quando origem não tem saldo suficiente."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.Transferir(
                carteira_pb2.TransferirRequest(conta_origem="003", conta_destino="001", valor=99999.0),
                timeout=5,
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Deadline
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadline(CarteiraTestCase):
    """
    Testa o comportamento do deadline no cliente.
    Não depende de delay no servidor — usa timeout extremamente curto.
    """

    def test_deadline_excedido_retorna_deadline_exceeded(self):
        """Deve retornar DEADLINE_EXCEEDED com timeout de 0.0001s (quasi-zero)."""
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.ConsultarSaldo(
                carteira_pb2.ContaRequest(conta_id="001"),
                timeout=0.0001,  # 0.1ms — impossível completar
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.DEADLINE_EXCEEDED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

> **Comando para executar os testes:**
> ```powershell
> cd d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4
> python -m pytest tests/test_carteira.py -v
> ```

---

## FASE 6 — Scripts de Experimentos

**Objetivo:** Automatizar os 4 experimentos exigidos pela atividade e coletar dados para a tabela de resultados.

### Passo 6.1 — Script de helper para subir o servidor (Windows)

**Arquivo:** `atividade_pratica4/scripts/run_server.ps1`

```powershell
# Navega para o diretório carteira e inicia o servidor com parâmetros configuráveis
param(
    [int]$port    = 50051,
    [int]$workers = 10,
    [float]$delay = 0.0
)

$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location "$rootDir\carteira"

Write-Host "Iniciando servidor Carteira Digital..." -ForegroundColor Cyan
Write-Host "  Porta   : $port"    -ForegroundColor Gray
Write-Host "  Workers : $workers" -ForegroundColor Gray
Write-Host "  Delay   : ${delay}s" -ForegroundColor Gray

python server.py --port $port --workers $workers --delay $delay
```

### Passo 6.2 — Script principal de experimentos

**Arquivo:** `atividade_pratica4/scripts/run_experiments.py`

```python
"""
run_experiments.py — Script de Experimentos gRPC
Atividade Prática 4 — Sistemas Distribuídos

Executa os 4 experimentos exigidos pela atividade e imprime uma tabela
de resultados coletados. O servidor deve estar rodando separadamente.

Experimentos:
  1. Indisponibilidade — servidor desligado
  2. Deadline — servidor com delay artificial
  3. Concorrência — múltiplos clientes simultâneos
  4. Evolução de Contrato — campo novo adicionado ao .proto
"""

import sys
import os
import time
import threading
import grpc
from concurrent.futures import ThreadPoolExecutor, as_completed

# Adicionar o diretório carteira ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "carteira"))

import carteira_pb2
import carteira_pb2_grpc
from client import get_stub, consultar_saldo, depositar, sacar

HOST = "localhost"
PORT = 50051

# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

resultados = []  # lista de dicts para tabela final


def registrar(experimento, metodo, status, latencia_ms, detalhes=""):
    """Registra um resultado na tabela."""
    resultados.append({
        "experimento": experimento,
        "metodo":      metodo,
        "status":      status,
        "latencia_ms": latencia_ms,
        "detalhes":    detalhes,
    })


def medir_chamada(stub, metodo_fn, *args, **kwargs):
    """Executa uma chamada RPC e mede a latência. Retorna (status_code, latencia_ms)."""
    inicio = time.perf_counter()
    try:
        metodo_fn(stub, *args, **kwargs)
        latencia_ms = (time.perf_counter() - inicio) * 1000
        return "OK", latencia_ms
    except grpc.RpcError as e:
        latencia_ms = (time.perf_counter() - inicio) * 1000
        return e.code().name, latencia_ms


# ─────────────────────────────────────────────────────────────────────────────
# Experimento 1 — Indisponibilidade (servidor desligado)
# ─────────────────────────────────────────────────────────────────────────────

def experimento_indisponibilidade():
    """
    Intenção: Conectar ao servidor quando ele NÃO está rodando e observar o erro.
    
    INSTRUÇÕES DE EXECUÇÃO MANUAL:
      1. Certifique-se de que NENHUM servidor está rodando na porta 50051.
      2. Execute: python scripts/run_experiments.py --exp 1
    """
    print("\n" + "="*60)
    print("EXPERIMENTO 1: Indisponibilidade")
    print("="*60)
    print("Certifique-se de que o servidor NÃO está rodando.")
    print("Tentando conectar à porta 50051 sem servidor...\n")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        status, lat = medir_chamada(
            stub, consultar_saldo, "001", timeout=3.0
        )
        print(f"  Status: {status} | Latência: {lat:.1f}ms")
        registrar("1-Indisponibilidade", "ConsultarSaldo", status, round(lat, 1),
                  "Servidor desligado — esperado UNAVAILABLE")

    print("\nResultado esperado: UNAVAILABLE")


# ─────────────────────────────────────────────────────────────────────────────
# Experimento 2 — Deadline (servidor com delay)
# ─────────────────────────────────────────────────────────────────────────────

def experimento_deadline():
    """
    Intenção: Testar o comportamento do deadline com servidor lento.
    
    INSTRUÇÕES DE EXECUÇÃO MANUAL:
      1. Suba o servidor com delay de 3 segundos:
         python carteira/server.py --delay 3
      2. Execute: python scripts/run_experiments.py --exp 2
    """
    print("\n" + "="*60)
    print("EXPERIMENTO 2: Deadline")
    print("="*60)
    print("Servidor deve estar rodando com --delay 3")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        # Tentativa 1 — timeout curto (deve falhar)
        print("\n[2a] Depósito com timeout=1s (servidor tem delay=3s):")
        status, lat = medir_chamada(stub, depositar, "001", 10.0, timeout=1.0)
        print(f"  Status: {status} | Latência: {lat:.1f}ms")
        registrar("2-Deadline", "Depositar (timeout=1s)", status, round(lat, 1),
                  "Servidor delay=3s | esperado DEADLINE_EXCEEDED")

        # Tentativa 2 — timeout longo (deve funcionar)
        print("\n[2b] Depósito com timeout=5s (servidor tem delay=3s):")
        status, lat = medir_chamada(stub, depositar, "001", 10.0, timeout=5.0)
        print(f"  Status: {status} | Latência: {lat:.1f}ms")
        registrar("2-Deadline", "Depositar (timeout=5s)", status, round(lat, 1),
                  "Servidor delay=3s | esperado OK")


# ─────────────────────────────────────────────────────────────────────────────
# Experimento 3 — Concorrência (múltiplos clientes simultâneos)
# ─────────────────────────────────────────────────────────────────────────────

def cliente_concorrente(cliente_id: int, resultados_thread: list):
    """Função executada por cada thread cliente."""
    stub, channel = get_stub(HOST, PORT)
    with channel:
        inicio = time.perf_counter()
        try:
            req = carteira_pb2.TransacaoRequest(conta_id="001", valor=1.0, descricao=f"cliente-{cliente_id}")
            stub.Depositar(req, timeout=5.0)
            lat = (time.perf_counter() - inicio) * 1000
            resultados_thread.append({"cliente": cliente_id, "status": "OK", "latencia_ms": round(lat, 1)})
        except grpc.RpcError as e:
            lat = (time.perf_counter() - inicio) * 1000
            resultados_thread.append({"cliente": cliente_id, "status": e.code().name, "latencia_ms": round(lat, 1)})


def experimento_concorrencia(num_clientes: int = 20):
    """
    Intenção: Lançar múltiplos clientes simultâneos e verificar que o servidor
    processa todas as requisições corretamente.
    
    INSTRUÇÕES DE EXECUÇÃO MANUAL:
      1. Suba o servidor com workers aumentados:
         python carteira/server.py --workers 20
      2. Execute: python scripts/run_experiments.py --exp 3
    """
    print("\n" + "="*60)
    print(f"EXPERIMENTO 3: Concorrência ({num_clientes} clientes simultâneos)")
    print("="*60)

    resultados_thread = []
    threads = []

    inicio_total = time.perf_counter()
    for i in range(num_clientes):
        t = threading.Thread(target=cliente_concorrente, args=(i + 1, resultados_thread))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tempo_total = (time.perf_counter() - inicio_total) * 1000
    sucessos = sum(1 for r in resultados_thread if r["status"] == "OK")
    falhas   = num_clientes - sucessos
    lat_media = sum(r["latencia_ms"] for r in resultados_thread) / len(resultados_thread)

    print(f"\n  Clientes: {num_clientes} | Sucessos: {sucessos} | Falhas: {falhas}")
    print(f"  Latência média: {lat_media:.1f}ms | Tempo total: {tempo_total:.1f}ms")

    for r in resultados_thread:
        print(f"    Cliente {r['cliente']:02d}: {r['status']} ({r['latencia_ms']}ms)")

    registrar("3-Concorrência", f"Depositar x{num_clientes}", f"{sucessos}/{num_clientes} OK",
              round(lat_media, 1), f"Tempo total: {tempo_total:.1f}ms")


# ─────────────────────────────────────────────────────────────────────────────
# Experimento 4 — Evolução de Contrato
# ─────────────────────────────────────────────────────────────────────────────

def experimento_evolucao_contrato():
    """
    Intenção: Demonstrar que adicionar um campo NOVO ao .proto é retrocompatível.
    
    Etapas a executar MANUALMENTE:
    
    1. No arquivo carteira/carteira.proto, adicionar o campo 'moeda' ao TransacaoRequest:
       
       message TransacaoRequest {
         string conta_id  = 1;
         double valor     = 2;
         string descricao = 3;
         string moeda     = 4;  // NOVO CAMPO — adicionado na evolução do contrato
       }
    
    2. Gerar os stubs NOVAMENTE com o script gerar_stubs.ps1.
    
    3. Testar que o servidor ANTIGO (com stubs sem o campo 'moeda') ainda funciona
       corretamente com requisições que incluem o novo campo 'moeda'.
       
       Observação esperada: O gRPC ignora campos desconhecidos por padrão —
       o servidor antigo continua funcionando sem alteração, demonstrando
       a retrocompatibilidade dos Protocol Buffers.
    
    4. Executar este script com o servidor atualizado:
       python scripts/run_experiments.py --exp 4
    """
    print("\n" + "="*60)
    print("EXPERIMENTO 4: Evolução de Contrato")
    print("="*60)
    print("Certifique-se de ter adicionado o campo 'moeda' ao .proto e regenerado os stubs.")

    stub, channel = get_stub(HOST, PORT)
    with channel:
        # Usar o campo novo 'moeda' — só funciona após regenerar os stubs
        try:
            req = carteira_pb2.TransacaoRequest(
                conta_id="001",
                valor=10.0,
                descricao="Experimento evolução",
                moeda="BRL",  # CAMPO NOVO
            )
            inicio = time.perf_counter()
            resp = stub.Depositar(req, timeout=5.0)
            lat = (time.perf_counter() - inicio) * 1000
            print(f"  Status: OK | Latência: {lat:.1f}ms")
            print(f"  Resposta: {resp.mensagem}")
            registrar("4-EvolucaoContrato", "Depositar (campo moeda)", "OK",
                      round(lat, 1), "Campo 'moeda' adicionado — retrocompatível")
        except grpc.RpcError as e:
            print(f"  ERRO [{e.code().name}]: {e.details()}")
        except TypeError as e:
            print(f"  ERRO de tipo (campo 'moeda' não existe ainda nos stubs): {e}")
            print("  → Execute gerar_stubs.ps1 após adicionar o campo ao .proto")


# ─────────────────────────────────────────────────────────────────────────────
# Tabela final de resultados
# ─────────────────────────────────────────────────────────────────────────────

def imprimir_tabela():
    """Imprime a tabela de resultados formatada para copiar no relatório."""
    print("\n" + "="*80)
    print("TABELA DE RESULTADOS — AP4 Carteira Digital gRPC")
    print("="*80)
    print(f"{'Experimento':<25} {'Método':<30} {'Status':<25} {'Lat.(ms)':<12} {'Detalhes'}")
    print("-"*130)
    for r in resultados:
        print(f"{r['experimento']:<25} {r['metodo']:<30} {r['status']:<25} {r['latencia_ms']:<12} {r['detalhes']}")
    print("="*130)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Experimentos gRPC — Carteira Digital")
    parser.add_argument("--exp", type=int, choices=[1, 2, 3, 4], help="Número do experimento (1-4). Omitir para executar todos.")
    parser.add_argument("--clientes", type=int, default=20, help="Número de clientes simultâneos (experimento 3)")
    args = parser.parse_args()

    if args.exp == 1 or args.exp is None:
        experimento_indisponibilidade()
    if args.exp == 2 or args.exp is None:
        experimento_deadline()
    if args.exp == 3 or args.exp is None:
        experimento_concorrencia(args.clientes)
    if args.exp == 4 or args.exp is None:
        experimento_evolucao_contrato()

    if resultados:
        imprimir_tabela()
```

---

## FASE 7 — Relatório Final (`analise.md`)

**Objetivo:** Produzir o relatório com a tabela de resultados e as respostas às 5 questões analíticas do PDF.

**Arquivo:** `atividade_pratica4/relatorio/analise.md`

> **Instruções para o agente executor:**
> 1. Execute os 4 experimentos e colete os dados reais (latências e status codes observados).
> 2. Substitua os campos `[VALOR_MEDIDO]` pelos valores reais obtidos.
> 3. As respostas das questões abaixo já estão redigidas — revise e adapte se necessário.

```markdown
# Relatório — Atividade Prática 4: Serviço gRPC de Carteira Digital
**Disciplina:** Sistemas Distribuídos  
**Tema:** Carteira Digital  
**Tecnologia:** gRPC + Protocol Buffers (Python)

---

## 1. Tabela de Resultados dos Experimentos

| # | Experimento            | Método RPC                   | Status gRPC Observado    | Latência (ms) | Observações                                              |
|---|------------------------|------------------------------|--------------------------|---------------|----------------------------------------------------------|
| 1 | Indisponibilidade      | ConsultarSaldo               | `UNAVAILABLE`            | [VALOR_MEDIDO] | Servidor desligado. Erro imediato após timeout de conexão |
| 2a| Deadline (curto)       | Depositar (timeout=1s)       | `DEADLINE_EXCEEDED`      | ~1000         | Servidor delay=3s. Cliente cancela após 1s              |
| 2b| Deadline (suficiente)  | Depositar (timeout=5s)       | `OK`                     | ~3000         | Servidor delay=3s. Concluído dentro do timeout           |
| 3 | Concorrência (20 cli.) | Depositar (×20 simultâneos)  | 20/20 `OK`               | [VALOR_MEDIDO] | Workers=20. Todos processados sem erros                  |
| 4 | Evolução de Contrato   | Depositar (campo `moeda`)    | `OK`                     | [VALOR_MEDIDO] | Campo novo ignorado pelo servidor antigo; retrocompatível |

---

## 2. Análise Comparativa — 5 Questões

### Q1. Como o gRPC define e impõe o contrato entre cliente e servidor em comparação com REST (AP2)?

No gRPC, o contrato é definido **de forma explícita e tipada** no arquivo `.proto` (Protocol Buffers). A partir dele, os stubs (código cliente e servidor) são **gerados automaticamente**, garantindo que cliente e servidor sempre compartilhem exatamente a mesma interface. Qualquer divergência é detectada em **tempo de compilação/geração**, antes mesmo de o código ser executado.

No REST (AP2), o contrato é tipicamente documentado em texto livre ou em especificações como OpenAPI/Swagger, mas sua aplicação é **opcional e manual**. Um cliente pode enviar um JSON com campos errados e o servidor só descobre o erro em **tempo de execução**, precisando de validação manual no código.

**Conclusão:** O gRPC oferece um contrato **mais rígido, verificável e autoexplicativo**, eliminando uma categoria inteira de erros de integração.

---

### Q2. Quais são as vantagens e desvantagens do uso de Protocol Buffers em relação ao JSON (usado em REST/AP2 e MQTT/AP3)?

| Aspecto            | Protocol Buffers (gRPC)                    | JSON (REST / MQTT)                     |
|--------------------|--------------------------------------------|----------------------------------------|
| **Tamanho**        | Binário — compacto (3-10× menor)           | Texto — verboso                        |
| **Velocidade**     | Serialização muito mais rápida             | Mais lento para grandes volumes        |
| **Legibilidade**   | Ilegível sem ferramentas (binário)         | Human-readable, fácil de debugar       |
| **Tipagem**        | Fortemente tipado, validado no contrato    | Dinâmico, sujeito a erros de tipo      |
| **Versionamento**  | Retrocompatível por design (campo IDs)     | Requer gestão manual de versão         |
| **Flexibilidade**  | Menos flexível — exige regenar stubs       | Mais flexível — sem geração de código  |

**Conclusão:** Para sistemas de alta performance e internos (microserviços), Protobuf é superior. Para APIs públicas ou integração com sistemas heterogêneos onde legibilidade e flexibilidade importam mais, JSON é mais adequado.

---

### Q3. Como o mecanismo de deadline do gRPC difere do timeout implementado manualmente em REST (AP2)?

No gRPC, o **deadline é propagado automaticamente pela rede**. Quando o cliente define `timeout=2.0`, essa informação viaja nos metadados HTTP/2 até o servidor. O servidor pode verificar se o prazo expirou *antes mesmo de começar o processamento*, evitando trabalho desnecessário. Se expirar no meio do processamento, o canal é cancelado em ambos os lados de forma coordenada.

Em REST (AP2), o timeout é tipicamente implementado apenas no cliente (ex: `requests.get(url, timeout=2)`). O servidor **não sabe que o cliente desistiu** e continua processando a requisição até o fim, consumindo recursos desnecessariamente. Não há cancelamento coordenado.

**Conclusão:** O modelo de deadline do gRPC é mais eficiente e robusto para sistemas distribuídos, pois coordena o cancelamento em ambas as pontas da comunicação.

---

### Q4. O modelo de comunicação do gRPC se assemelha mais ao REST (AP2) ou ao MQTT (AP3)? Justifique.

O gRPC assemelha-se mais ao **REST (AP2)** no modelo de comunicação:

- Ambos seguem o padrão **request-response** (cliente chama, servidor responde).
- Ambos são **orientados a chamadas diretas** (o cliente sabe o endereço do servidor).
- Ambos são **síncronos por natureza** na modalidade unária (o cliente aguarda a resposta).

O MQTT (AP3), por outro lado, segue um modelo **publish-subscribe**:
- O cliente publica mensagens em *tópicos* sem saber quem irá receber.
- A comunicação é **assíncrona e desacoplada** — o publisher não aguarda resposta.
- É ideal para **IoT e telemetria**, onde sensores enviam dados continuamente sem precisar de confirmação imediata.

**Conclusão:** O gRPC é mais próximo do REST em termos de modelo de comunicação. Porém, o gRPC suporta *streaming bidirecional* (não explorado nesta atividade), que aproxima seu comportamento do modelo assíncrono do MQTT.

---

### Q5. Quão difícil foi evoluir o contrato do gRPC (adicionar um novo campo) em comparação com a evolução de uma API REST?

A evolução de contrato no gRPC com Protocol Buffers é **surpreendentemente simples e segura**, desde que as boas práticas sejam seguidas:

1. Basta adicionar um novo campo com um **número de campo único** (ex: `string moeda = 4`).
2. Regenerar os stubs com `grpc_tools.protoc`.
3. Servidores/clientes **antigos ignoram automaticamente** campos novos desconhecidos, mantendo a retrocompatibilidade.

Já em REST com JSON:
- Adicionar um novo campo ao JSON geralmente funciona (clientes ignoram campos extras).
- Porém, **remover ou renomear campos quebra contratos** sem aviso, e o servidor só descobre o erro em runtime.
- Não existe mecanismo nativo de verificação — depende de documentação manual (OpenAPI) ou testes de contrato (Pact).

**Conclusão:** O gRPC com Protobuf tem um modelo de evolução de contrato **mais seguro e gerenciável**, especialmente em sistemas com múltiplos clientes. A geração de stubs garante que todos os consumidores sejam atualizados de forma verificável.
```

---

## FASE 8 — Checklist de Verificação Final

Antes de considerar a atividade completa, o agente executor deve verificar:

- [ ] `requirements.txt` criado e dependências instaladas com sucesso
- [ ] `carteira/carteira.proto` criado com 5 métodos RPC e 6 tipos de mensagens
- [ ] Stubs gerados: `carteira_pb2.py` e `carteira_pb2_grpc.py` existem em `carteira/`
- [ ] `carteira/server.py` roda sem erros: `python carteira/server.py`
- [ ] `carteira/client.py` executa a demo completa sem erros inesperados
- [ ] `python -m pytest tests/test_carteira.py -v` — todos os testes passam (verde)
- [ ] Experimento 1 produz status `UNAVAILABLE`
- [ ] Experimento 2a produz `DEADLINE_EXCEEDED`; 2b produz `OK`
- [ ] Experimento 3 processa todos os clientes com sucesso
- [ ] Experimento 4 executa com o novo campo após regenerar stubs
- [ ] `relatorio/analise.md` preenchido com valores reais medidos nos experimentos

---

## Sequência de Comandos Completa (Execução Rápida)

```powershell
# 1. Instalar dependências
cd d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica4
pip install -r requirements.txt

# 2. Gerar stubs
.\gerar_stubs.ps1

# 3. Verificar stubs gerados
ls carteira\*.py

# 4. Rodar os testes automatizados (servidor não precisa estar rodando)
python -m pytest tests/test_carteira.py -v

# 5. Subir o servidor (em uma janela separada do PowerShell)
cd carteira
python server.py

# 6. Rodar a demo do cliente (em outra janela)
cd carteira
python client.py

# 7. Experimento 1 (servidor desligado) — fechar o servidor antes
python scripts\run_experiments.py --exp 1

# 8. Experimento 2 — subir servidor com delay=3 e rodar:
# Janela 1: python carteira/server.py --delay 3
# Janela 2: python scripts\run_experiments.py --exp 2

# 9. Experimento 3 — subir servidor com workers=20 e rodar:
# Janela 1: python carteira/server.py --workers 20
# Janela 2: python scripts\run_experiments.py --exp 3 --clientes 20

# 10. Experimento 4 — adicionar campo 'moeda' ao .proto, regenerar stubs e rodar:
# .\gerar_stubs.ps1
# python scripts\run_experiments.py --exp 4
```

---

## Notas para os Agentes Executores

> [!IMPORTANT]
> - Todos os scripts Python que importam módulos do pacote `carteira` devem ser executados com o **diretório de trabalho** configurado corretamente (ou com `sys.path` ajustado como mostrado).
> - Os arquivos `carteira_pb2.py` e `carteira_pb2_grpc.py` são **gerados automaticamente** e não devem ser criados manualmente.
> - O servidor e o cliente devem ser executados em **janelas/terminais separados** nos experimentos que exigem servidor ativo.
> - Para o experimento de evolução de contrato, o campo `moeda` deve ser adicionado **ao .proto existente** (não criar um novo arquivo), e os stubs devem ser regenerados.

> [!TIP]
> - Para debugar erros de importação, verifique se `grpc` e `grpcio-tools` estão instalados: `python -c "import grpc; print(grpc.__version__)"`.
> - Se o servidor não iniciar na porta 50051, verifique se há outro processo usando a porta: `netstat -ano | findstr :50051`.
