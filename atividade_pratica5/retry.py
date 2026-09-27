"""
AP5 — Módulo de Retry com Backoff Exponencial + Jitter

Implementa a função `requisicao_com_retry` que executa qualquer método
HTTP com retentativas automáticas sobre falhas transitórias.

Fórmula de espera entre tentativas:
    espera = (2 ** n) * base + random.uniform(0, cap_jitter)

    n=0: ~0.20s–0.30s
    n=1: ~0.40s–0.50s
    n=2: ~0.80s–0.90s

Política de retry:
  - FARÁ retry: ConnectionError, Timeout, HTTPError 5xx (falhas transitórias)
  - NÃO FARÁ retry: HTTPError 4xx (erros determinísticos de cliente)
"""

import random
import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, Timeout, HTTPError


def requisicao_com_retry(
    method: str,
    url: str,
    max_tentativas: int = 4,
    base: float = 0.2,
    cap_jitter: float = 0.1,
    timeout_req: float = 1.0,
    **kwargs: Any,
) -> dict:
    """
    Executa requisição HTTP com retry exponencial + jitter.

    Args:
        method:         Método HTTP em minúsculo: "get", "post", "patch", etc.
        url:            URL completa do endpoint.
        max_tentativas: Número máximo de tentativas (padrão 4).
        base:           Fator base do backoff em segundos (padrão 0.2).
        cap_jitter:     Limite superior do jitter aleatório (padrão 0.1s).
        timeout_req:    Timeout por requisição individual em segundos.
        **kwargs:       Demais argumentos repassados a requests (json=, headers=, etc.).

    Returns:
        dict com campos:
            sucesso (bool)             — True se alguma tentativa teve êxito.
            resposta (Response|None)   — Objeto Response da última tentativa com êxito.
            metricas (list[dict])      — Lista de métricas por tentativa.
            tentativas_realizadas (int)
            tipo_erro (str|None)       — Nome da exceção ou código HTTP do erro final.
    """
    metricas: list[dict] = []
    ultimo_erro: Exception | None = None

    for tentativa in range(max_tentativas):
        t0 = time.perf_counter()
        try:
            resp: requests.Response = getattr(requests, method.lower())(
                url, timeout=timeout_req, **kwargs
            )
            latencia_ms = (time.perf_counter() - t0) * 1000

            # Erros 4xx são determinísticos — não faz retry
            if 400 <= resp.status_code < 500:
                metricas.append({
                    "tentativa": tentativa + 1,
                    "status": resp.status_code,
                    "latencia_ms": round(latencia_ms, 2),
                    "resultado": "ERRO_DETERMINÍSTICO",
                    "tipo_erro": f"HTTP_{resp.status_code}",
                })
                return {
                    "sucesso": False,
                    "resposta": resp,
                    "metricas": metricas,
                    "tentativas_realizadas": tentativa + 1,
                    "tipo_erro": f"HTTP_{resp.status_code}",
                }

            # 5xx vira HTTPError via raise_for_status
            resp.raise_for_status()

            metricas.append({
                "tentativa": tentativa + 1,
                "status": resp.status_code,
                "latencia_ms": round(latencia_ms, 2),
                "resultado": "SUCESSO",
                "tipo_erro": None,
            })
            return {
                "sucesso": True,
                "resposta": resp,
                "metricas": metricas,
                "tentativas_realizadas": tentativa + 1,
                "tipo_erro": None,
            }

        except (Timeout, ConnectionError, HTTPError) as exc:
            latencia_ms = (time.perf_counter() - t0) * 1000
            tipo_exc = type(exc).__name__
            ultimo_erro = exc

            metricas.append({
                "tentativa": tentativa + 1,
                "status": getattr(getattr(exc, "response", None), "status_code", None),
                "latencia_ms": round(latencia_ms, 2),
                "resultado": "FALHA",
                "tipo_erro": tipo_exc,
            })

            if tentativa < max_tentativas - 1:
                espera = (2 ** tentativa) * base + random.uniform(0, cap_jitter)
                print(f"    [retry] falha: {tipo_exc} | próxima tentativa em {espera:.2f}s "
                      f"(tentativa {tentativa + 2}/{max_tentativas})")
                time.sleep(espera)

    # Todas as tentativas esgotadas
    return {
        "sucesso": False,
        "resposta": None,
        "metricas": metricas,
        "tentativas_realizadas": max_tentativas,
        "tipo_erro": type(ultimo_erro).__name__ if ultimo_erro else "DESCONHECIDO",
    }
