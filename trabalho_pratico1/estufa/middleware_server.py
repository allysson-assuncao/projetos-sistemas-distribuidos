"""
middleware_server.py — Servidor XML-RPC do Middleware.

Expõe um ponto único de acesso na porta configurada em MIDDLEWARE_PORT (9000),
isolando os clientes e os controladores em recuperação da topologia interna
das réplicas.

Uso:
    python -m estufa.middleware_server [--host HOST] [--port PORT]
"""

import argparse
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from estufa.middleware import Middleware, ErroQuorum
from estufa import config


class MiddlewareService:
    """Adaptador XML-RPC que delega as operações ao motor de votação do Middleware."""

    def __init__(self):
        self._mw = Middleware()

    def obter_estado(self) -> dict:
        """Retorna o estado da estufa aprovado por maioria."""
        try:
            return self._mw.obter_estado()
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_bomba(self, acao: str) -> dict:
        """Repassa o comando da bomba às réplicas e valida o quórum da resposta."""
        try:
            return self._mw.comandar_bomba(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_exaustor(self, acao: str) -> dict:
        """Repassa o comando do exaustor às réplicas e valida o quórum da resposta."""
        try:
            return self._mw.comandar_exaustor(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def verificar_saude(self) -> dict:
        """Retorna o status de disponibilidade de cada réplica de controlador."""
        return self._mw.verificar_saude()

    def ping(self) -> str:
        """Verificação simples de atividade do servidor de Middleware."""
        return "pong:middleware_server"


def iniciar_servidor(host: str = None, port: int = None) -> None:
    """Inicializa e mantém o servidor XML-RPC do Middleware em execução."""
    host = host or config.MIDDLEWARE_HOST
    port = port or config.MIDDLEWARE_PORT

    class SilentHandler(SimpleXMLRPCRequestHandler):
        def log_message(self, fmt, *args):
            pass

    server = SimpleXMLRPCServer(
        (host, port),
        requestHandler=SilentHandler,
        allow_none=True,
        logRequests=False,
    )

    service = MiddlewareService()
    server.register_instance(service)
    server.register_introspection_functions()

    print(f"[MIDDLEWARE SERVER] Iniciando em {host}:{port}")
    print(f"[MIDDLEWARE SERVER] Controladores configurados ({len(config.CONTROLADORES)}):")
    for ctrl in config.CONTROLADORES:
        print(f"  - {ctrl['id']} @ {ctrl['host']}:{ctrl['port']}")
    print(f"[MIDDLEWARE SERVER] Aguardando conexões em http://{host}:{port} (Ctrl+C para encerrar)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MIDDLEWARE SERVER] Encerrando servidor.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor XML-RPC do Middleware — Estufa Agrícola")
    parser.add_argument("--host", default=config.MIDDLEWARE_HOST, help="Endereço do servidor")
    parser.add_argument("--port", default=config.MIDDLEWARE_PORT, type=int, help="Porta do servidor")
    args = parser.parse_args()

    iniciar_servidor(host=args.host, port=args.port)
