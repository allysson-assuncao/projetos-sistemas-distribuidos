"""
AP5 — Módulo de Autenticação
Decorator @requer_token que valida Bearer Token no header Authorization.

Propriedade de segurança coberta: Autenticidade + Autorização.
Em produção, o token seria validado via JWT/OAuth2. Aqui,
um token pré-compartilhado é suficiente para o laboratório.

Uso:
    from auth import requer_token

    @app.route("/rota-protegida")
    @requer_token
    def rota_protegida():
        ...
"""

from __future__ import annotations

import os
from functools import wraps
from flask import request, jsonify

# Lê token do ambiente; fallback hardcoded exclusivo para laboratório.
# Em produção: NUNCA use fallback hardcoded.
TOKEN_VALIDO: str = os.environ.get("AP5_TOKEN", "ap5-laboratorio-token-2026")


def requer_token(f):
    """
    Decorator que valida o header 'Authorization: Bearer <token>'.

    Rejeita com 401 Unauthorized se:
      - Header Authorization ausente.
      - Formato diferente de 'Bearer <valor>'.
      - Token não corresponde a TOKEN_VALIDO.

    Em caso de sucesso, a requisição prossegue normalmente.
    """
    @wraps(f)
    def decorado(*args, **kwargs):
        header_auth: str = request.headers.get("Authorization", "")

        # Valida formato "Bearer <token>"
        if not header_auth.startswith("Bearer "):
            return jsonify({
                "erro": "Token ausente ou formato inválido",
                "dica": "Envie o header: Authorization: Bearer <token>",
                "propriedade_violada": "Autenticidade",
            }), 401

        token = header_auth[len("Bearer "):].strip()

        if token != TOKEN_VALIDO:
            return jsonify({
                "erro": "Token inválido ou expirado",
                "propriedade_violada": "Autorização",
            }), 401

        return f(*args, **kwargs)

    return decorado
