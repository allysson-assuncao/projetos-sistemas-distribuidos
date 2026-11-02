"""
middleware.py — Motor de votação e invocação distribuída do Middleware.

Realiza chamadas XML-RPC paralelas para as réplicas de controlador e aplica
votação majoritária (quórum 2 de 3) para mascarar falhas por parada (crash)
ou respostas arbitrárias (bizantinas).
"""

import collections
import concurrent.futures
import json
import uuid
import xmlrpc.client
from typing import Any
from estufa import config


class ErroQuorum(Exception):
    """Exceção lançada quando o quórum mínimo de respostas concordantes não é atingido."""
    pass


class Middleware:
    """Coordena chamadas remotas ao cluster de controladores e apura o quórum."""

    def __init__(self, controladores: list = None, timeout: int = None):
        self._controladores = controladores or config.CONTROLADORES
        self._timeout = timeout or config.TIMEOUT_RPC_SEGUNDOS

    def _criar_proxy(self, controlador: dict) -> xmlrpc.client.ServerProxy:
        """Instancia um proxy XML-RPC para o controlador informado."""
        url = f"http://{controlador['host']}:{controlador['port']}"
        return xmlrpc.client.ServerProxy(url, allow_none=True)

    def _chamar_controlador(self, controlador: dict, metodo: str, *args) -> Any:
        """Executa uma chamada XML-RPC individual em um controlador."""
        proxy = self._criar_proxy(controlador)
        func = getattr(proxy, metodo)
        return func(*args)

    def _votar(self, metodo: str, *args) -> Any:
        """
        Dispara a chamada em paralelo para todos os controladores, normaliza os
        retornos ignorando metadados de instância e verifica o quórum mínimo.
        """
        resultados = []
        erros = []

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
                    print(f"[MIDDLEWARE] Controlador {ctrl['id']} indisponível: {e}")

        if not resultados:
            raise ErroQuorum(
                f"Nenhuma resposta recebida de {len(self._controladores)} controladores. "
                f"Erros: {erros}"
            )

        def _normalizar(valor: Any) -> str:
            if isinstance(valor, dict):
                copia = {
                    k: v for k, v in valor.items()
                    if k not in ("ultima_atualizacao", "controlador_id")
                }
                return json.dumps(copia, sort_keys=True)
            return str(valor)

        contagem = collections.Counter(_normalizar(r) for _, r in resultados)
        mais_comum, votos = contagem.most_common(1)[0]

        print(f"[MIDDLEWARE] Votos: {dict(contagem)} | Quórum mínimo: {config.QUORUM_MINIMO}")

        if votos < config.QUORUM_MINIMO:
            raise ErroQuorum(
                f"Quórum não atingido: {votos} voto(s) para a resposta mais comum "
                f"(mínimo: {config.QUORUM_MINIMO}). Respostas: {resultados}"
            )

        for _, resultado in resultados:
            if _normalizar(resultado) == mais_comum:
                return resultado

    def obter_estado(self) -> dict:
        """Consulta o estado atual da estufa validado por votação majoritária."""
        return self._votar("obter_estado")

    def comandar_bomba(self, acao: str) -> dict:
        """Envia comando manual da bomba às réplicas com UUID único para deduplicação."""
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] Gerando comando_id={comando_id[:8]}... para bomba ({acao})")
        return self._votar("comandar_bomba", acao, comando_id)

    def comandar_exaustor(self, acao: str) -> dict:
        """Envia comando manual do exaustor às réplicas com UUID único para deduplicação."""
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] Gerando comando_id={comando_id[:8]}... para exaustor ({acao})")
        return self._votar("comandar_exaustor", acao, comando_id)

    def verificar_saude(self) -> dict:
        """Verifica a conectividade individual de cada réplica do cluster."""
        saude = {}
        for ctrl in self._controladores:
            try:
                proxy = self._criar_proxy(ctrl)
                resp = proxy.ping()
                saude[ctrl["id"]] = "ok" if "pong" in str(resp) else f"resposta inesperada: {resp}"
            except Exception as e:
                saude[ctrl["id"]] = f"OFFLINE: {e}"
        return saude
