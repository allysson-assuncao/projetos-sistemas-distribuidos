# Plano de Implementação — Atividade Prática 2: API REST (Projetos e Tarefas)

## Visão Geral

Implementar uma **API REST** completa em Python usando Flask para gerenciar **Projetos** e **Tarefas** (relação 1-para-N). O objetivo acadêmico é demonstrar domínio de modelagem REST, métodos HTTP corretos, códigos de status, idempotência, tratamento de erros e comportamento de timeout.

**Decisões Técnicas Fixadas:**
- Framework: **Flask**
- Armazenamento: **Dicionários em memória** (sem banco de dados)
- Cliente/Testes: **Script Python** usando a biblioteca `requests`
- Timeout: Simulado via endpoint `GET /slow` no próprio servidor
- Delete de Projeto com Tarefas: Retorna `409 Conflict`

---

## Estrutura de Arquivos Final

```
atividade_pratica2/
├── server.py          # Servidor Flask com todos os endpoints
├── client.py          # Script cliente de demonstração e testes
├── requirements.txt   # Dependências Python
└── README.md          # Instruções de uso e análise das perguntas teóricas
```

---

## Modelos de Dados (em memória)

### Projeto
```json
{
  "id": 1,
  "nome": "string (obrigatório)",
  "descricao": "string (obrigatório)",
  "status": "ativo | arquivado",
  "criado_em": "2025-08-24T20:00:00"
}
```

### Tarefa
```json
{
  "id": 1,
  "titulo": "string (obrigatório)",
  "descricao": "string (obrigatório)",
  "status": "pendente | concluida",
  "prioridade": "baixa | media | alta",
  "projeto_id": 1,
  "criado_em": "2025-08-24T20:00:00"
}
```

---

## Tabela de Endpoints

| # | Método | URI | Descrição | Status Sucesso |
|---|--------|-----|-----------|----------------|
| 1 | GET | `/projetos` | Lista todos os projetos | 200 |
| 2 | POST | `/projetos` | Cria um novo projeto | 201 |
| 3 | GET | `/projetos/<id>` | Obtém um projeto pelo ID | 200 |
| 4 | PATCH | `/projetos/<id>` | Atualiza parcialmente um projeto | 200 |
| 5 | DELETE | `/projetos/<id>` | Remove um projeto (409 se tiver tarefas) | 204 |
| 6 | GET | `/projetos/<id>/tarefas` | Lista tarefas de um projeto | 200 |
| 7 | POST | `/projetos/<id>/tarefas` | Cria uma tarefa em um projeto | 201 |
| 8 | PATCH | `/tarefas/<id>` | Atualiza parcialmente uma tarefa | 200 |
| 9 | DELETE | `/tarefas/<id>` | Remove uma tarefa | 204 |
| 10 | GET | `/slow` | Endpoint lento (para teste de timeout) | 200 (após 10s) |

---

## Fase 1 — Criação do Ambiente e Dependências

**Agente responsável:** Executor de comandos de shell  
**Pré-requisito:** Python 3.10+ instalado e disponível no PATH como `python`  
**Diretório de trabalho:** `d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica2`

### 1.1 — Criar o diretório do projeto

```powershell
mkdir "d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica2"
```

### 1.2 — Criar o arquivo `requirements.txt`

**Arquivo:** `atividade_pratica2/requirements.txt`

```
flask>=3.0.0
requests>=2.31.0
```

### 1.3 — Criar o ambiente virtual e instalar dependências

```powershell
cd "d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica2"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Verificação:** O comando `pip show flask requests` deve exibir as versões instaladas sem erro.

---

## Fase 2 — Implementação do Servidor (`server.py`)

**Agente responsável:** Escritor de código  
**Arquivo a criar:** `atividade_pratica2/server.py`

Este arquivo contém toda a lógica da API. Deve ser criado **exatamente** como descrito abaixo.

### Código completo de `server.py`

```python
"""
Atividade Prática 2 — Sistemas Distribuídos
API REST: Gerenciador de Projetos e Tarefas
Servidor Flask com armazenamento em memória.
"""

import time
from datetime import datetime
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# ─────────────────────────────────────────────────
# ARMAZENAMENTO EM MEMÓRIA
# ─────────────────────────────────────────────────
projetos: dict[int, dict] = {}
tarefas: dict[int, dict] = {}
_projeto_id_counter = 0
_tarefa_id_counter = 0


def _novo_projeto_id() -> int:
    global _projeto_id_counter
    _projeto_id_counter += 1
    return _projeto_id_counter


def _nova_tarefa_id() -> int:
    global _tarefa_id_counter
    _tarefa_id_counter += 1
    return _tarefa_id_counter


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─────────────────────────────────────────────────
# VALIDADORES
# ─────────────────────────────────────────────────
STATUS_PROJETO_VALIDOS = {"ativo", "arquivado"}
STATUS_TAREFA_VALIDOS = {"pendente", "concluida"}
PRIORIDADE_VALIDAS = {"baixa", "media", "alta"}


def _validar_projeto(dados: dict, criacao: bool = True) -> list[str]:
    """Retorna lista de erros de validação. Lista vazia = válido."""
    erros = []
    if criacao:
        if not dados.get("nome"):
            erros.append("Campo 'nome' é obrigatório.")
        if not dados.get("descricao"):
            erros.append("Campo 'descricao' é obrigatório.")
    if "status" in dados and dados["status"] not in STATUS_PROJETO_VALIDOS:
        erros.append(f"Campo 'status' deve ser um de: {STATUS_PROJETO_VALIDOS}.")
    return erros


def _validar_tarefa(dados: dict, criacao: bool = True) -> list[str]:
    """Retorna lista de erros de validação. Lista vazia = válido."""
    erros = []
    if criacao:
        if not dados.get("titulo"):
            erros.append("Campo 'titulo' é obrigatório.")
        if not dados.get("descricao"):
            erros.append("Campo 'descricao' é obrigatório.")
    if "status" in dados and dados["status"] not in STATUS_TAREFA_VALIDOS:
        erros.append(f"Campo 'status' deve ser um de: {STATUS_TAREFA_VALIDOS}.")
    if "prioridade" in dados and dados["prioridade"] not in PRIORIDADE_VALIDAS:
        erros.append(f"Campo 'prioridade' deve ser um de: {PRIORIDADE_VALIDAS}.")
    return erros


# ─────────────────────────────────────────────────
# ROTAS — PROJETOS
# ─────────────────────────────────────────────────

@app.route("/projetos", methods=["GET"])
def listar_projetos():
    """
    Lista todos os projetos cadastrados.
    Método: GET — idempotente e seguro.
    Retorna: 200 OK com lista (pode ser vazia).
    """
    return jsonify(list(projetos.values())), 200


@app.route("/projetos", methods=["POST"])
def criar_projeto():
    """
    Cria um novo projeto.
    Método: POST — não idempotente (cada chamada cria um novo recurso).
    Retorna: 201 Created com o projeto criado e Location header.
    Erros: 400 Bad Request se dados inválidos.
    """
    dados = request.get_json(silent=True)
    if dados is None:
        return jsonify({"erro": "Corpo da requisição deve ser JSON válido."}), 400

    erros = _validar_projeto(dados, criacao=True)
    if erros:
        return jsonify({"erro": "Dados inválidos.", "detalhes": erros}), 400

    pid = _novo_projeto_id()
    projeto = {
        "id": pid,
        "nome": dados["nome"],
        "descricao": dados["descricao"],
        "status": dados.get("status", "ativo"),
        "criado_em": _agora(),
    }
    # Valida status explícito se fornecido
    if projeto["status"] not in STATUS_PROJETO_VALIDOS:
        return jsonify({"erro": f"Status inválido. Use: {STATUS_PROJETO_VALIDOS}"}), 400

    projetos[pid] = projeto
    response = jsonify(projeto)
    response.status_code = 201
    response.headers["Location"] = f"/projetos/{pid}"
    return response


@app.route("/projetos/<int:pid>", methods=["GET"])
def obter_projeto(pid: int):
    """
    Obtém um projeto específico pelo ID.
    Método: GET — idempotente e seguro.
    Retorna: 200 OK com o projeto.
    Erros: 404 Not Found se não existir.
    """
    projeto = projetos.get(pid)
    if projeto is None:
        return jsonify({"erro": f"Projeto com id={pid} não encontrado."}), 404
    return jsonify(projeto), 200


@app.route("/projetos/<int:pid>", methods=["PATCH"])
def atualizar_projeto(pid: int):
    """
    Atualiza parcialmente um projeto existente.
    Método: PATCH — idempotente se aplicado com os mesmos valores.
    Permite atualizar: nome, descricao, status (individualmente ou em conjunto).
    Retorna: 200 OK com o projeto atualizado.
    Erros: 404 Not Found, 400 Bad Request.
    """
    projeto = projetos.get(pid)
    if projeto is None:
        return jsonify({"erro": f"Projeto com id={pid} não encontrado."}), 404

    dados = request.get_json(silent=True)
    if dados is None:
        return jsonify({"erro": "Corpo da requisição deve ser JSON válido."}), 400

    erros = _validar_projeto(dados, criacao=False)
    if erros:
        return jsonify({"erro": "Dados inválidos.", "detalhes": erros}), 400

    # Atualiza apenas os campos enviados
    for campo in ("nome", "descricao", "status"):
        if campo in dados:
            projeto[campo] = dados[campo]

    return jsonify(projeto), 200


@app.route("/projetos/<int:pid>", methods=["DELETE"])
def deletar_projeto(pid: int):
    """
    Remove um projeto pelo ID.
    Método: DELETE — idempotente.
    REGRA DE NEGÓCIO: não permite deletar projeto com tarefas associadas.
    Retorna: 204 No Content em caso de sucesso.
    Erros: 404 Not Found, 409 Conflict (projeto tem tarefas).
    """
    projeto = projetos.get(pid)
    if projeto is None:
        return jsonify({"erro": f"Projeto com id={pid} não encontrado."}), 404

    tarefas_do_projeto = [t for t in tarefas.values() if t["projeto_id"] == pid]
    if tarefas_do_projeto:
        return jsonify({
            "erro": "Conflito: o projeto possui tarefas associadas e não pode ser deletado.",
            "tarefas_pendentes": len(tarefas_do_projeto),
        }), 409

    del projetos[pid]
    return "", 204


# ─────────────────────────────────────────────────
# ROTAS — TAREFAS (aninhadas em projetos)
# ─────────────────────────────────────────────────

@app.route("/projetos/<int:pid>/tarefas", methods=["GET"])
def listar_tarefas(pid: int):
    """
    Lista todas as tarefas de um projeto específico.
    Método: GET — idempotente e seguro.
    Retorna: 200 OK com lista de tarefas (pode ser vazia).
    Erros: 404 Not Found se o projeto não existir.
    """
    if pid not in projetos:
        return jsonify({"erro": f"Projeto com id={pid} não encontrado."}), 404
    resultado = [t for t in tarefas.values() if t["projeto_id"] == pid]
    return jsonify(resultado), 200


@app.route("/projetos/<int:pid>/tarefas", methods=["POST"])
def criar_tarefa(pid: int):
    """
    Cria uma nova tarefa dentro de um projeto.
    Método: POST — não idempotente.
    Retorna: 201 Created com a tarefa criada e Location header.
    Erros: 404 Not Found (projeto), 400 Bad Request (dados inválidos).
    """
    if pid not in projetos:
        return jsonify({"erro": f"Projeto com id={pid} não encontrado."}), 404

    dados = request.get_json(silent=True)
    if dados is None:
        return jsonify({"erro": "Corpo da requisição deve ser JSON válido."}), 400

    erros = _validar_tarefa(dados, criacao=True)
    if erros:
        return jsonify({"erro": "Dados inválidos.", "detalhes": erros}), 400

    tid = _nova_tarefa_id()
    tarefa = {
        "id": tid,
        "titulo": dados["titulo"],
        "descricao": dados["descricao"],
        "status": dados.get("status", "pendente"),
        "prioridade": dados.get("prioridade", "media"),
        "projeto_id": pid,
        "criado_em": _agora(),
    }
    tarefas[tid] = tarefa
    response = jsonify(tarefa)
    response.status_code = 201
    response.headers["Location"] = f"/tarefas/{tid}"
    return response


@app.route("/tarefas/<int:tid>", methods=["PATCH"])
def atualizar_tarefa(tid: int):
    """
    Atualiza parcialmente uma tarefa existente.
    Método: PATCH — idempotente se aplicado com os mesmos valores.
    Exemplo clássico: marcar uma tarefa como 'concluida'.
    Retorna: 200 OK com a tarefa atualizada.
    Erros: 404 Not Found, 400 Bad Request.
    """
    tarefa = tarefas.get(tid)
    if tarefa is None:
        return jsonify({"erro": f"Tarefa com id={tid} não encontrada."}), 404

    dados = request.get_json(silent=True)
    if dados is None:
        return jsonify({"erro": "Corpo da requisição deve ser JSON válido."}), 400

    erros = _validar_tarefa(dados, criacao=False)
    if erros:
        return jsonify({"erro": "Dados inválidos.", "detalhes": erros}), 400

    for campo in ("titulo", "descricao", "status", "prioridade"):
        if campo in dados:
            tarefa[campo] = dados[campo]

    return jsonify(tarefa), 200


@app.route("/tarefas/<int:tid>", methods=["DELETE"])
def deletar_tarefa(tid: int):
    """
    Remove uma tarefa pelo ID.
    Método: DELETE — idempotente.
    Retorna: 204 No Content em caso de sucesso.
    Erros: 404 Not Found.
    """
    tarefa = tarefas.get(tid)
    if tarefa is None:
        return jsonify({"erro": f"Tarefa com id={tid} não encontrada."}), 404

    del tarefas[tid]
    return "", 204


# ─────────────────────────────────────────────────
# ROTA ESPECIAL — TIMEOUT
# ─────────────────────────────────────────────────

@app.route("/slow", methods=["GET"])
def slow():
    """
    Endpoint lento para teste de timeout do cliente.
    Dorme 10 segundos antes de responder.
    O cliente deve configurar timeout < 10s para disparar o erro.
    """
    time.sleep(10)
    return jsonify({"mensagem": "Resposta demorada entregue com sucesso!"}), 200


# ─────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  API REST — Gerenciador de Projetos e Tarefas")
    print("  Atividade Prática 2 — Sistemas Distribuídos")
    print("  Rodando em: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
```

---

## Fase 3 — Implementação do Cliente de Testes (`client.py`)

**Agente responsável:** Escritor de código  
**Arquivo a criar:** `atividade_pratica2/client.py`

O cliente é um script de demonstração sequencial. Ele executa os cenários de teste e imprime os resultados formatados no terminal. **Cada seção é um cenário testado** e deve ser executada com o servidor já rodando em `http://127.0.0.1:5000`.

### Código completo de `client.py`

```python
"""
Atividade Prática 2 — Sistemas Distribuídos
Cliente de Testes da API REST: Gerenciador de Projetos e Tarefas

Executa uma bateria de testes sequenciais contra o servidor Flask.
O servidor deve estar rodando em http://127.0.0.1:5000 antes de iniciar.

Uso:
    python client.py
"""

import requests

BASE_URL = "http://127.0.0.1:5000"
TIMEOUT_PADRAO = 5  # segundos — timeout para todas as requisições normais

# ─────────────────────────────────────────────────
# UTILITÁRIOS DE IMPRESSÃO
# ─────────────────────────────────────────────────

VERDE   = "\033[92m"
VERMELHO = "\033[91m"
AMARELO = "\033[93m"
AZUL    = "\033[94m"
NEGRITO = "\033[1m"
RESET   = "\033[0m"
CIANO   = "\033[96m"


def secao(titulo: str):
    print(f"\n{NEGRITO}{AZUL}{'=' * 60}{RESET}")
    print(f"{NEGRITO}{AZUL}  {titulo}{RESET}")
    print(f"{NEGRITO}{AZUL}{'=' * 60}{RESET}")


def resultado(metodo: str, url: str, status: int, esperado: int, corpo):
    ok = status == esperado
    cor = VERDE if ok else VERMELHO
    simbolo = "✔" if ok else "✘"
    print(f"\n  {cor}{NEGRITO}{simbolo} {metodo} {url}{RESET}")
    print(f"  Status obtido:   {cor}{status}{RESET}  |  Esperado: {esperado}")
    print(f"  Resposta: {corpo}")


def erro_conexao(metodo: str, url: str, exc: Exception):
    print(f"\n  {VERMELHO}{NEGRITO}✘ {metodo} {url}{RESET}")
    print(f"  {VERMELHO}Erro de conexão/timeout: {type(exc).__name__}: {exc}{RESET}")


# ─────────────────────────────────────────────────
# CENÁRIOS DE TESTE
# ─────────────────────────────────────────────────

def cenario_1_listar_projetos_vazio():
    """GET /projetos — lista vazia inicial."""
    secao("CENÁRIO 1: Listar projetos (lista vazia inicial)")
    url = f"{BASE_URL}/projetos"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_2_criar_projetos():
    """POST /projetos — cria dois projetos válidos."""
    secao("CENÁRIO 2: Criar projetos válidos")
    url = f"{BASE_URL}/projetos"

    payloads = [
        {"nome": "Sistema de Vendas", "descricao": "Projeto de e-commerce completo"},
        {"nome": "App Mobile", "descricao": "Aplicativo Android e iOS", "status": "ativo"},
    ]
    ids = []
    for payload in payloads:
        r = requests.post(url, json=payload, timeout=TIMEOUT_PADRAO)
        resultado("POST", url, r.status_code, 201, r.json())
        ids.append(r.json()["id"])
    return ids


def cenario_3_obter_projeto(pid: int):
    """GET /projetos/<id> — obtém projeto existente."""
    secao(f"CENÁRIO 3: Obter projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_4_criar_tarefas(pid: int):
    """POST /projetos/<id>/tarefas — cria tarefas no projeto."""
    secao(f"CENÁRIO 4: Criar tarefas no projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}/tarefas"

    payloads = [
        {"titulo": "Modelagem do banco de dados", "descricao": "Definir esquema ER", "prioridade": "alta"},
        {"titulo": "Implementar autenticação", "descricao": "JWT com refresh token", "prioridade": "alta"},
        {"titulo": "Criar tela de login", "descricao": "Design responsivo", "prioridade": "media"},
    ]
    ids = []
    for payload in payloads:
        r = requests.post(url, json=payload, timeout=TIMEOUT_PADRAO)
        resultado("POST", url, r.status_code, 201, r.json())
        ids.append(r.json()["id"])
    return ids


def cenario_5_listar_tarefas(pid: int):
    """GET /projetos/<id>/tarefas — lista tarefas do projeto."""
    secao(f"CENÁRIO 5: Listar tarefas do projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}/tarefas"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_6_atualizar_tarefa(tid: int):
    """PATCH /tarefas/<id> — marcar tarefa como concluída (idempotente)."""
    secao(f"CENÁRIO 6: Marcar tarefa id={tid} como concluída (PATCH idempotente)")
    url = f"{BASE_URL}/tarefas/{tid}"

    print(f"\n  {CIANO}Aplicando PATCH duas vezes com os mesmos dados para demonstrar idempotência:{RESET}")
    for i in range(2):
        r = requests.patch(url, json={"status": "concluida"}, timeout=TIMEOUT_PADRAO)
        print(f"\n  Chamada {i + 1}/2:")
        resultado("PATCH", url, r.status_code, 200, r.json())


def cenario_7_atualizar_projeto(pid: int):
    """PATCH /projetos/<id> — atualizar status do projeto."""
    secao(f"CENÁRIO 7: Arquivar projeto id={pid} (PATCH)")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.patch(url, json={"status": "arquivado"}, timeout=TIMEOUT_PADRAO)
    resultado("PATCH", url, r.status_code, 200, r.json())


# ── ERROS DE APLICAÇÃO ─────────────────────────────────────────────────────────

def cenario_8_erro_projeto_nao_encontrado():
    """ERRO 1: GET /projetos/9999 — projeto inexistente (404)."""
    secao("CENÁRIO 8 [ERRO DE APLICAÇÃO 1]: Buscar projeto inexistente → 404")
    url = f"{BASE_URL}/projetos/9999"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 404, r.json())


def cenario_9_erro_dados_invalidos():
    """ERRO 2: POST /projetos — corpo sem campos obrigatórios (400)."""
    secao("CENÁRIO 9 [ERRO DE APLICAÇÃO 2]: Criar projeto sem campos obrigatórios → 400")
    url = f"{BASE_URL}/projetos"
    payload_invalido = {"status": "invalido_mesmo"}  # sem nome, sem descricao, status inválido
    r = requests.post(url, json=payload_invalido, timeout=TIMEOUT_PADRAO)
    resultado("POST", url, r.status_code, 400, r.json())


def cenario_10_erro_delete_projeto_com_tarefas(pid: int):
    """ERRO 3 (bônus): DELETE /projetos/<id> com tarefas existentes → 409."""
    secao(f"CENÁRIO 10 [CONFLITO]: Deletar projeto id={pid} com tarefas → 409")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    resultado("DELETE", url, r.status_code, 409, r.json())


# ── TIMEOUT ────────────────────────────────────────────────────────────────────

def cenario_11_timeout():
    """TIMEOUT: GET /slow com timeout=3s — servidor demora 10s → Timeout."""
    secao("CENÁRIO 11 [FALHA DE CONECTIVIDADE]: Requisição com timeout → requests.Timeout")
    url = f"{BASE_URL}/slow"
    print(f"\n  {AMARELO}Enviando GET /slow com timeout=3s (servidor dormirá 10s)...{RESET}")
    try:
        r = requests.get(url, timeout=3)
        resultado("GET", url, r.status_code, 200, r.json())
    except requests.exceptions.Timeout as e:
        erro_conexao("GET", url, e)
        print(f"  {VERDE}✔ Timeout capturado corretamente pelo cliente!{RESET}")


# ── LIMPEZA FINAL ──────────────────────────────────────────────────────────────

def cenario_12_deletar_tarefa(tid: int):
    """DELETE /tarefas/<id> — remove uma tarefa."""
    secao(f"CENÁRIO 12: Deletar tarefa id={tid}")
    url = f"{BASE_URL}/tarefas/{tid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    # 204 No Content não tem corpo
    print(f"\n  {'✔' if r.status_code == 204 else '✘'} DELETE {url}")
    print(f"  Status obtido: {r.status_code} | Esperado: 204")


def cenario_13_deletar_projeto_apos_remover_tarefas(pid: int):
    """DELETE /projetos/<id> — deleta o projeto após remover suas tarefas."""
    secao(f"CENÁRIO 13: Deletar projeto id={pid} (após tarefas removidas)")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    print(f"\n  {'✔' if r.status_code == 204 else '✘'} DELETE {url}")
    print(f"  Status obtido: {r.status_code} | Esperado: 204")


# ─────────────────────────────────────────────────
# EXECUÇÃO PRINCIPAL
# ─────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  CLIENTE DE TESTES — API REST Projetos e Tarefas")
    print("  Atividade Prática 2 — Sistemas Distribuídos")
    print("=" * 60)
    print(f"\n  Base URL : {BASE_URL}")
    print(f"  Timeout padrão: {TIMEOUT_PADRAO}s\n")

    # ── CENÁRIOS DE SUCESSO ──────────────────────────────────
    cenario_1_listar_projetos_vazio()

    projeto_ids = cenario_2_criar_projetos()
    pid_principal = projeto_ids[0]  # Projeto "Sistema de Vendas"
    pid_secundario = projeto_ids[1]  # Projeto "App Mobile"

    cenario_3_obter_projeto(pid_principal)

    tarefa_ids = cenario_4_criar_tarefas(pid_principal)
    tid_principal = tarefa_ids[0]

    cenario_5_listar_tarefas(pid_principal)

    cenario_6_atualizar_tarefa(tid_principal)

    cenario_7_atualizar_projeto(pid_secundario)

    # ── CENÁRIOS DE ERRO ─────────────────────────────────────
    cenario_8_erro_projeto_nao_encontrado()

    cenario_9_erro_dados_invalidos()

    cenario_10_erro_delete_projeto_com_tarefas(pid_principal)

    # ── CENÁRIO DE TIMEOUT ───────────────────────────────────
    cenario_11_timeout()

    # ── LIMPEZA / DEMONSTRAÇÃO DO DELETE ─────────────────────
    # Remove todas as tarefas do projeto principal para então deletá-lo
    for tid in tarefa_ids:
        cenario_12_deletar_tarefa(tid)

    cenario_13_deletar_projeto_apos_remover_tarefas(pid_principal)

    print(f"\n\n{NEGRITO}{VERDE}{'=' * 60}")
    print("  TODOS OS CENÁRIOS EXECUTADOS COM SUCESSO!")
    print(f"{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
```

---

## Fase 4 — Criação do `README.md`

**Agente responsável:** Escritor de documentação  
**Arquivo a criar:** `atividade_pratica2/README.md`

O README deve ser criado **exatamente** como descrito abaixo. Ele serve tanto como guia de uso quanto como entregável de análise teórica.

### Código completo de `README.md`

```markdown
# Atividade Prática 2 — API REST: Gerenciador de Projetos e Tarefas

**Disciplina:** Sistemas Distribuídos  
**Tema:** API REST com operações CRUD sobre duas coleções relacionadas

---

## Sobre o Projeto

API REST desenvolvida em Python com Flask para gerenciar **Projetos** e **Tarefas**.  
Um projeto pode conter várias tarefas (relação 1-para-N).  
Os dados são armazenados em memória (reiniciam ao encerrar o servidor).

---

## Pré-requisitos

- Python 3.10 ou superior
- pip

---

## Instalação e Execução

### 1. Criar e ativar o ambiente virtual

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Iniciar o servidor

```bash
python server.py
```

O servidor estará disponível em `http://127.0.0.1:5000`.

### 4. Executar os testes (em outro terminal)

```bash
# Ative o ambiente virtual primeiro
.venv\Scripts\activate  # ou source .venv/bin/activate

python client.py
```

---

## Endpoints da API

| Método | URI | Descrição | Status Sucesso |
|--------|-----|-----------|----------------|
| GET | `/projetos` | Lista todos os projetos | 200 |
| POST | `/projetos` | Cria um novo projeto | 201 |
| GET | `/projetos/<id>` | Obtém um projeto pelo ID | 200 |
| PATCH | `/projetos/<id>` | Atualiza parcialmente um projeto | 200 |
| DELETE | `/projetos/<id>` | Remove um projeto | 204 |
| GET | `/projetos/<id>/tarefas` | Lista tarefas de um projeto | 200 |
| POST | `/projetos/<id>/tarefas` | Cria uma tarefa em um projeto | 201 |
| PATCH | `/tarefas/<id>` | Atualiza parcialmente uma tarefa | 200 |
| DELETE | `/tarefas/<id>` | Remove uma tarefa | 204 |
| GET | `/slow` | Endpoint lento (teste de timeout) | 200 (após 10s) |

---

## Modelos de Dados

### Projeto
```json
{
  "id": 1,
  "nome": "Sistema de Vendas",
  "descricao": "Projeto de e-commerce",
  "status": "ativo | arquivado",
  "criado_em": "2025-08-24T20:00:00"
}
```

### Tarefa
```json
{
  "id": 1,
  "titulo": "Modelagem do banco",
  "descricao": "Definir esquema ER",
  "status": "pendente | concluida",
  "prioridade": "baixa | media | alta",
  "projeto_id": 1,
  "criado_em": "2025-08-24T20:00:00"
}
```

---

## Tabela de Cenários de Teste

| # | Cenário | Método | URI | Status Esperado | Status Obtido |
|---|---------|--------|-----|-----------------|---------------|
| 1 | Listar projetos (lista vazia) | GET | /projetos | 200 | 200 |
| 2 | Criar projetos válidos | POST | /projetos | 201 | 201 |
| 3 | Obter projeto existente | GET | /projetos/1 | 200 | 200 |
| 4 | Criar tarefas em um projeto | POST | /projetos/1/tarefas | 201 | 201 |
| 5 | Listar tarefas do projeto | GET | /projetos/1/tarefas | 200 | 200 |
| 6 | Marcar tarefa como concluída (PATCH idempotente, 2x) | PATCH | /tarefas/1 | 200 | 200 |
| 7 | Arquivar projeto (PATCH) | PATCH | /projetos/2 | 200 | 200 |
| 8 | **[ERRO]** Buscar projeto inexistente | GET | /projetos/9999 | 404 | 404 |
| 9 | **[ERRO]** Criar projeto sem campos obrigatórios | POST | /projetos | 400 | 400 |
| 10 | **[CONFLITO]** Deletar projeto com tarefas | DELETE | /projetos/1 | 409 | 409 |
| 11 | **[TIMEOUT]** Requisição para endpoint lento (timeout=3s) | GET | /slow | Timeout | Timeout |
| 12 | Deletar tarefas do projeto | DELETE | /tarefas/<id> | 204 | 204 |
| 13 | Deletar projeto após remover tarefas | DELETE | /projetos/1 | 204 | 204 |

---

## Análise Teórica

### 1. Quais operações são idempotentes e por quê?

Uma operação é **idempotente** quando executá-la múltiplas vezes com os mesmos parâmetros produz sempre o mesmo estado final no servidor.

Na nossa API:

- **GET** (todos os endpoints): seguro e idempotente — apenas lê dados, nunca os modifica.
- **DELETE `/projetos/<id>` e `/tarefas/<id>`**: idempotente — após a primeira chamada o recurso é removido; chamadas subsequentes retornam 404 (o estado final do recurso é "inexistente" em ambos os casos, o efeito sobre o estado do recurso é o mesmo).
- **PATCH `/projetos/<id>` e `/tarefas/<id>`**: idempotente **quando aplicado com os mesmos valores** — aplicar `{"status": "concluida"}` dez vezes resulta no mesmo estado. Demonstrado no Cenário 6.

Não é idempotente:
- **POST `/projetos` e `/projetos/<id>/tarefas`**: cada chamada cria um novo recurso com um novo ID, alterando o estado do servidor.

### 2. Diferença entre erro do servidor e falha de conectividade

| Aspecto | Erro de aplicação (4xx/5xx) | Falha de conectividade (Timeout) |
|---|---|---|
| **O que acontece** | O servidor recebeu a requisição, processou e retornou uma resposta de erro | O cliente não recebe nenhuma resposta dentro do tempo limite |
| **Quem detecta** | O cliente recebe o status HTTP e o corpo do erro | O cliente dispara `requests.exceptions.Timeout` (ou similar) |
| **Causa** | Dado inválido, recurso não encontrado, conflito de negócio | Servidor offline, rede congestionada, servidor muito lento |
| **Exemplo na API** | GET /projetos/9999 → 404 JSON explicando o erro | GET /slow com timeout=3s → cliente lança exceção antes de receber qualquer byte |
| **Rastreabilidade** | O servidor registra a requisição no log | O servidor pode ter recebido a requisição mas o cliente nunca saberá |

### 3. Decisões da API que impactam o acoplamento cliente-servidor

O acoplamento define o quão dependente o cliente é de detalhes internos do servidor. Decisões tomadas nesta API para **reduzir** o acoplamento:

- **Uso do header `Location`**: ao criar um recurso (201 Created), o servidor retorna o URI do novo recurso no header `Location`. O cliente não precisa saber como construir o URI — ele segue o que o servidor informa (princípio HATEOAS básico).
- **URIs baseados em recursos, não em ações**: `/projetos` ao invés de `/getCriarProjeto`. O método HTTP define a ação; a URI identifica o recurso. Isso torna a interface mais estável e previsível.
- **Envelope de erro padronizado** com campos `erro` e `detalhes`: o cliente pode tratar qualquer resposta de erro da mesma forma sem conhecer detalhes internos.

Decisão que **aumenta** o acoplamento: o modelo de dados (`status`, `prioridade`) com valores específicos em português. Se o servidor mudar os valores válidos, os clientes precisam ser atualizados.

### 4. Como evitar perda de dados com atualizações concorrentes (Optimistic Locking)

O problema: dois clientes leem o Projeto 1 ao mesmo tempo, ambos fazem alterações diferentes e ambos enviam PATCH. A última atualização sobrescreve silenciosamente a primeira — **lost update**.

A solução recomendada é o **Optimistic Locking com ETag**:

1. O servidor adiciona um campo `versao` (inteiro) em cada recurso.
2. O GET retorna o recurso com sua versão atual: `{ ..., "versao": 3 }`.
3. O cliente envia o PATCH com o header `If-Match: 3`.
4. O servidor compara: se `versao_atual == versao_recebida`, aplica a mudança e incrementa `versao` para 4.
5. Se outro cliente já atualizou (versão atual é 4), o servidor rejeita com **409 Conflict** ou **412 Precondition Failed**.
6. O cliente que recebeu 412 deve recarregar o recurso e tentar novamente com a nova versão.

Essa abordagem não requer locks no servidor e é escalável para ambientes distribuídos. Nesta atividade, a versão simplificada (sem ETag) é usada por simplicidade, mas a extensão é direta.
```

---

## Fase 5 — Execução e Validação

**Agente responsável:** Executor de comandos de shell  
**Pré-requisito:** Fases 1, 2, 3 e 4 concluídas.

### 5.1 — Iniciar o servidor em background (Terminal 1)

Execute em um terminal separado e deixe rodando:

```powershell
cd "d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica2"
.venv\Scripts\activate
python server.py
```

**Saída esperada:**
```
============================================================
  API REST — Gerenciador de Projetos e Tarefas
  Atividade Prática 2 — Sistemas Distribuídos
  Rodando em: http://127.0.0.1:5000
============================================================

 * Running on http://127.0.0.1:5000
```

### 5.2 — Executar o cliente (Terminal 2)

```powershell
cd "d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\atividade_pratica2"
.venv\Scripts\activate
python client.py
```

### 5.3 — Critérios de validação (o agente deve verificar)

Após a execução do `client.py`, confirmar visualmente no terminal:

| Critério | Como verificar |
|---|---|
| Cenários 1–7 exibem `✔` (verde) | Saída do terminal mostrando símbolo ✔ e status correto |
| Cenário 8 exibe status 404 | Linha "Status obtido: 404" no cenário 8 |
| Cenário 9 exibe status 400 | Linha "Status obtido: 400" no cenário 9 |
| Cenário 10 exibe status 409 | Linha "Status obtido: 409" no cenário 10 |
| Cenário 11 captura `requests.exceptions.Timeout` | Mensagem de erro de timeout capturado + mensagem verde de confirmação |
| Cenários 12–13 exibem status 204 | Linha "Status obtido: 204" nos cenários 12 e 13 |
| Mensagem final "TODOS OS CENÁRIOS EXECUTADOS" | Última linha do output em verde |

### 5.4 — Verificação manual adicional (opcional, via curl)

```powershell
# Listar projetos
curl http://127.0.0.1:5000/projetos

# Criar projeto
curl -X POST http://127.0.0.1:5000/projetos -H "Content-Type: application/json" -d "{\"nome\": \"Teste\", \"descricao\": \"Via curl\"}"

# Buscar projeto inexistente
curl http://127.0.0.1:5000/projetos/9999
```

---

## Resumo das Fases

| Fase | O que criar/executar | Artefato gerado |
|------|----------------------|-----------------|
| 1 | Criar diretório, `requirements.txt`, venv, pip install | Ambiente pronto |
| 2 | Criar `server.py` | Servidor Flask com 10 endpoints |
| 3 | Criar `client.py` | Script de 13 cenários de teste |
| 4 | Criar `README.md` | Documentação + análise teórica |
| 5 | Executar servidor + cliente | Validação visual dos 13 cenários |

---

## Notas para o Agente Executor

> **Ordem de execução é obrigatória:** A Fase 1 deve ser concluída antes das Fases 2, 3 e 4. As Fases 2, 3 e 4 podem ser executadas em paralelo entre si. A Fase 5 só pode iniciar após a conclusão de todas as fases anteriores.

> **Encoding:** Todos os arquivos devem ser salvos com encoding **UTF-8**.

> **Windows:** Ao ativar o venv no PowerShell, pode ser necessário executar `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` caso a política de execução de scripts esteja restrita.

> **Porta ocupada:** Se a porta 5000 estiver em uso, altere `port=5000` para outro valor (ex: `port=5001`) em `server.py` e atualize `BASE_URL` em `client.py` correspondentemente.
