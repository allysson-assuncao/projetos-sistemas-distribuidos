"""
Atividade Prática 2 — Sistemas Distribuídos
API REST: Gerenciador de Projetos e Tarefas
Servidor Flask com armazenamento em memória.
"""

import time
from datetime import datetime
# pyrefly: ignore [missing-import]
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
