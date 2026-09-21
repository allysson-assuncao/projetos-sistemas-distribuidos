"""
middleware.py — Internal Middleware Voting Engine.

This module is used INTERNALLY by middleware_server.py only.
External clients MUST NOT import or instantiate this class directly.
They should connect to middleware_server.py via XML-RPC on MIDDLEWARE_PORT.

Voting Algorithm (Simplified Byzantine Fault Tolerance):
  - Sends XML-RPC call to ALL controllers in parallel.
  - Collects responses within configured timeout.
  - If >= QUORUM_MINIMO concordant responses: returns the majority result.
  - If quorum not reached: raises ErroQuorum.

Fault Models Handled:
  1. Controller crash: timeout on call → controller ignored.
  2. Byzantine controller: discrepant response → outvoted by honest majority.
"""

import concurrent.futures
import collections
import json
import uuid
import xmlrpc.client
from typing import Any
from estufa import config


class ErroQuorum(Exception):
    """Raised when quorum of concordant responses cannot be reached."""
    pass


class Middleware:
    """
    Distributed invocation middleware for the controller cluster.

    Used internally by MiddlewareServer. Not a public API.
    """

    def __init__(self, controladores: list = None, timeout: int = None):
        self._controladores = controladores or config.CONTROLADORES
        self._timeout = timeout or config.TIMEOUT_RPC_SEGUNDOS

    def _criar_proxy(self, controlador: dict) -> xmlrpc.client.ServerProxy:
        """Creates an XML-RPC proxy for the specified controller."""
        url = f"http://{controlador['host']}:{controlador['port']}"
        return xmlrpc.client.ServerProxy(url, allow_none=True)

    def _chamar_controlador(self, controlador: dict, metodo: str, *args) -> Any:
        """Performs a single XML-RPC call to a controller."""
        proxy = self._criar_proxy(controlador)
        func = getattr(proxy, metodo)
        return func(*args)

    def _votar(self, metodo: str, *args) -> Any:
        """
        Core majority voting algorithm.

        Sends call to all controllers in parallel (ThreadPoolExecutor),
        waits for timeout, checks if concordant quorum exists.
        """
        resultados = []
        erros      = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._controladores)) as executor:
            futures = {
                executor.submit(self._chamar_controlador, ctrl, metodo, *args): ctrl
                for ctrl in self._controladores
            }
            for future in concurrent.futures.as_completed(futures, timeout=self._timeout + 1):
                ctrl = futures[future]
                try:
                    resultado = future.result(timeout=self._timeout)
                    resultados.append((ctrl["id"], resultado))
                except Exception as e:
                    erros.append((ctrl["id"], str(e)))
                    print(f"[MIDDLEWARE] ⚠️  Controlador {ctrl['id']} falhou: {e}")

        if not resultados:
            raise ErroQuorum(
                f"Nenhuma resposta recebida de {len(self._controladores)} controladores. "
                f"Erros: {erros}"
            )

        # ── Voting ────────────────────────────────────────────────────────────
        def _normalizar(valor: Any) -> str:
            if isinstance(valor, dict):
                copia = {k: v for k, v in valor.items()
                         if k not in ("ultima_atualizacao", "controlador_id", "_byzantino")}
                return json.dumps(copia, sort_keys=True)
            return str(valor)

        contagem = collections.Counter(_normalizar(r) for _, r in resultados)
        mais_comum, votos = contagem.most_common(1)[0]

        print(f"[MIDDLEWARE] Votos: {dict(contagem)} | Quorum mínimo: {config.QUORUM_MINIMO}")

        if votos < config.QUORUM_MINIMO:
            raise ErroQuorum(
                f"Quorum não atingido: {votos} voto(s) para a resposta mais comum "
                f"(mínimo: {config.QUORUM_MINIMO}). Respostas: {resultados}"
            )

        for _, resultado in resultados:
            if _normalizar(resultado) == mais_comum:
                return resultado

    # ─── Public API ─────────────────────────────────────────────────────────

    def obter_estado(self) -> dict:
        """Queries the current greenhouse state via majority voting."""
        return self._votar("obter_estado")

    def comandar_bomba(self, acao: str) -> dict:
        """
        Sends pump command to all controllers with a shared UUID for deduplication.
        The UUID is passed as 'comando_id' so all 3 controllers publish the same ID,
        allowing the actuator LRU cache to discard the 2 redundant MQTT publishes.
        """
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] 🆔 Gerando comando_id={comando_id[:8]}... para bomba {acao}")
        return self._votar("comandar_bomba", acao, comando_id)

    def comandar_exaustor(self, acao: str) -> dict:
        """
        Sends exhaust fan command to all controllers with a shared UUID for deduplication.
        """
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] 🆔 Gerando comando_id={comando_id[:8]}... para exaustor {acao}")
        return self._votar("comandar_exaustor", acao, comando_id)

    def verificar_saude(self) -> dict:
        """Checks which controllers are responding (health-check)."""
        saude = {}
        for ctrl in self._controladores:
            try:
                proxy = self._criar_proxy(ctrl)
                resp  = proxy.ping()
                saude[ctrl["id"]] = "ok" if "pong" in str(resp) else f"resposta inesperada: {resp}"
            except Exception as e:
                saude[ctrl["id"]] = f"OFFLINE: {e}"
        return saude
