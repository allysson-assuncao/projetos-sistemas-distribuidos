"""
AP5 — Servidor de Laboratório de Falhas e Segurança
Disciplina: Sistemas Distribuídos

Extende a base da AP2 (Flask REST — Gerenciador de Projetos) com:
  - /experimento/instavel     GET  — atraso controlado + falha probabilística (C2, C4)
  - /slow                     GET  — dorme 5s para demonstrar timeout (C2)
  - /projetos                 GET  — lista projetos (C1, C5)
  - /projetos                 POST — cria projeto SEM proteção (demonstra não idempotência C5)
  - /experimento/projetos-lab POST — protegido por Bearer Token + suporte a Idempotency-Key (C6, C7)

ATENÇÃO: Este servidor contém endpoints de injeção de falhas.
         NUNCA mantenha este código em ambiente de produção.

Uso:
    python server_lab.py
    python server_lab.py --port 5000   # porta customizada
"""

from __future__ import annotations

import os
import random
import sys
import time
from datetime import datetime

# Configura encoding UTF-8 no stdout/stderr no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, jsonify, request

from auth import requer_token

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Armazenamento em memória
# ---------------------------------------------------------------------------
_projetos: dict[int, dict] = {}
_projeto_counter: int = 0
# Mapa de Idempotency-Key → (status_code, body) para C7
_idempotency_store: dict[str, tuple[int, dict]] = {}


def _nova_id() -> int:
    global _projeto_counter
    _projeto_counter += 1
    return _projeto_counter


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# C1 / C5 — GET /projetos  (sem proteção, idempotente)
# ---------------------------------------------------------------------------
@app.get("/projetos")
def listar_projetos():
    """Lista todos os projetos em memória. Idempotente — seguro para retry."""
    return jsonify(list(_projetos.values())), 200


# ---------------------------------------------------------------------------
# C5 — POST /projetos  (sem proteção, NÃO idempotente)
# Cada chamada cria um novo recurso com ID único.
# Demonstra o efeito adverso de retry em operação não idempotente.
# ---------------------------------------------------------------------------
@app.post("/projetos")
def criar_projeto():
    """
    Cria projeto SEM proteção de autenticação e SEM suporte a Idempotency-Key.
    Propositalmente não idempotente: chamadas repetidas com mesmo payload
    geram recursos distintos (IDs diferentes, mesmo nome).
    """
    dados: dict = request.get_json(silent=True) or {}
    pid = _nova_id()
    projeto = {
        "id": pid,
        "nome": dados.get("nome", f"Projeto {pid}"),
        "criado_em": _agora(),
    }
    _projetos[pid] = projeto
    return jsonify(projeto), 201


# ---------------------------------------------------------------------------
# C2 — GET /slow  (dorme 5s; cliente com timeout=1s lança Timeout)
# ---------------------------------------------------------------------------
@app.get("/slow")
def slow():
    """
    Endpoint de atraso controlado (5 segundos).
    Combinado com timeout=1s no cliente, provoca requests.exceptions.Timeout.
    Demonstra que Timeout ≠ falha do servidor (C2, Q1).
    """
    time.sleep(5)
    return jsonify({"mensagem": "resposta lenta", "atraso_s": 5}), 200


# ---------------------------------------------------------------------------
# C4 — GET /experimento/instavel
# Parâmetros de query:
#   atraso_ms (int, default 0)     — atraso artificial em milissegundos
#   prob_falha (float, default 0)  — probabilidade de retornar 503
# ---------------------------------------------------------------------------
@app.get("/experimento/instavel")
def instavel():
    """
    Endpoint de injeção de falha probabilística.

    Query params:
      atraso_ms  — dorme N milissegundos antes de responder (default 0)
      prob_falha — probabilidade [0.0–1.0] de retornar HTTP 503 (default 0.0)

    Exemplos:
      /experimento/instavel                          → sempre 200
      /experimento/instavel?prob_falha=0.7           → 503 em ~70% das chamadas
      /experimento/instavel?atraso_ms=5000&prob_falha=0 → atraso 5s, sem falha
    """
    atraso_ms = int(request.args.get("atraso_ms", 0))
    prob_falha = float(request.args.get("prob_falha", 0.0))

    if atraso_ms > 0:
        time.sleep(atraso_ms / 1000)

    if random.random() < prob_falha:
        return jsonify({
            "erro": "falha injetada",
            "tipo": "SERVICE_UNAVAILABLE",
            "prob_falha_configurada": prob_falha,
        }), 503

    return jsonify({
        "ok": True,
        "atraso_ms": atraso_ms,
        "prob_falha": prob_falha,
    }), 200


# ---------------------------------------------------------------------------
# C6 + C7 — POST /experimento/projetos-lab
# Protegido por @requer_token (C6) + suporte a Idempotency-Key (C7)
# ---------------------------------------------------------------------------
@app.post("/experimento/projetos-lab")
@requer_token
def criar_projeto_lab():
    """
    Cria projeto COM proteção de autenticação (Bearer Token) e suporte
    a Idempotency-Key para mitigar duplicação em cenários de retry.

    C6 — sem/token inválido → 401 Unauthorized (gerenciado pelo decorator)
    C6 — token válido → 201 Created

    C7 — com header 'Idempotency-Key: <uuid>':
         1ª chamada → processa normalmente → 201 + armazena resultado
         2ª+ chamada com mesma chave → retorna resultado armazenado → 200
    """
    chave_idempotencia: str | None = request.headers.get("Idempotency-Key")

    # C7: Chave já vista → retorna resultado anterior sem criar duplicata (200, não 201)
    if chave_idempotencia and chave_idempotencia in _idempotency_store:
        _status_anterior, corpo_anterior = _idempotency_store[chave_idempotencia]
        return jsonify({**corpo_anterior, "_idempotente": True}), 200

    # Processamento normal
    dados: dict = request.get_json(silent=True) or {}
    pid = _nova_id()
    projeto = {
        "id": pid,
        "nome": dados.get("nome", f"Projeto Lab {pid}"),
        "criado_em": _agora(),
        "protegido": True,
    }
    _projetos[pid] = projeto

    # C7: Armazena para futuras chamadas com a mesma chave
    if chave_idempotencia:
        _idempotency_store[chave_idempotencia] = (201, projeto)

    return jsonify(projeto), 201


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("AP5_PORT", 5000))
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass

    print("=" * 55)
    print("  AP5 — Servidor de Laboratório de Falhas e Segurança")
    print("=" * 55)
    print(f"  URL base  : http://127.0.0.1:{port} (ou http://localhost:{port})")
    print(f"  Token env : AP5_TOKEN (fallback: ap5-laboratorio-token-2026)")
    print()
    print("  Endpoints disponíveis:")
    print(f"    GET  /projetos                      — lista projetos (C1, C5)")
    print(f"    POST /projetos                      — cria projeto s/ proteção (C5)")
    print(f"    GET  /slow                          — dorme 5s (C2 timeout)")
    print(f"    GET  /experimento/instavel          — falha probabilística (C4)")
    print(f"    POST /experimento/projetos-lab      — protegido + idempotente (C6, C7)")
    print("=" * 55)
    print("  AVISO: endpoints de laboratório. Não use em produção.")
    print("=" * 55)

    app.run(host="0.0.0.0", port=port, debug=False)
