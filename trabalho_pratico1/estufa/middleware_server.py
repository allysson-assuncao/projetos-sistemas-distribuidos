"""
middleware_server.py — Standalone Middleware XML-RPC Server.

This is the MAIN ENTRY POINT for the Middleware layer.
It exposes a single XML-RPC interface on MIDDLEWARE_PORT (default: 9000).

Architecture:
  - Clients connect to THIS server via XML-RPC (never to controllers directly)
  - This server uses the internal Middleware voting engine to orchestrate
    parallel calls to all 3 controllers and returns the quorum result

  [Client] --XML-RPC:9000--> [MiddlewareServer] --XML-RPC:8001/8002/8003--> [Controllers]

Usage:
    python -m estufa.middleware_server
    python -m estufa.middleware_server --host localhost --port 9000
"""

import argparse
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from estufa.middleware import Middleware, ErroQuorum
from estufa import config


class MiddlewareService:
    """
    XML-RPC service class that wraps the internal Middleware voting engine.

    All methods exposed here are callable by clients via XML-RPC.
    Exceptions (ErroQuorum) are automatically serialized by the XML-RPC protocol
    as Fault objects, which the client's xmlrpc.client will raise as exceptions.
    """

    def __init__(self):
        self._mw = Middleware()

    def obter_estado(self) -> dict:
        """
        [XML-RPC] Queries the majority-approved greenhouse state.

        Returns:
            dict: Quorum-approved state with temperatura, umidade_solo,
                  bomba_ligada, exaustor_ligado fields.

        Raises:
            xmlrpc.client.Fault: If quorum cannot be reached.
        """
        try:
            return self._mw.obter_estado()
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_bomba(self, acao: str) -> dict:
        """
        [XML-RPC] Sends pump command to all controllers with deduplication ID.

        Args:
            acao: 'ligar' or 'desligar'

        Returns:
            dict: Quorum-approved response with 'sucesso' and 'mensagem'.
        """
        try:
            return self._mw.comandar_bomba(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_exaustor(self, acao: str) -> dict:
        """
        [XML-RPC] Sends exhaust fan command to all controllers with deduplication ID.

        Args:
            acao: 'ligar' or 'desligar'

        Returns:
            dict: Quorum-approved response with 'sucesso' and 'mensagem'.
        """
        try:
            return self._mw.comandar_exaustor(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def verificar_saude(self) -> dict:
        """
        [XML-RPC] Health-check: returns status of each controller replica.

        Returns:
            dict: Maps controller_id -> 'ok' or error message.
        """
        return self._mw.verificar_saude()

    def ping(self) -> str:
        """[XML-RPC] Health-check for the Middleware Server itself."""
        return "pong:middleware_server"


def iniciar_servidor(host: str = None, port: int = None) -> None:
    """
    Starts the Middleware XML-RPC server.

    Args:
        host: Host to bind. Defaults to config.MIDDLEWARE_HOST.
        port: Port to bind. Defaults to config.MIDDLEWARE_PORT.
    """
    host = host or config.MIDDLEWARE_HOST
    port = port or config.MIDDLEWARE_PORT

    class SilentHandler(SimpleXMLRPCRequestHandler):
        """Suppresses HTTP access logs."""
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

    print(f"[MIDDLEWARE SERVER] 🚀 Iniciando em {host}:{port}")
    print(f"[MIDDLEWARE SERVER] Orquestrando {len(config.CONTROLADORES)} controladores:")
    for ctrl in config.CONTROLADORES:
        print(f"  - {ctrl['id']} @ {ctrl['host']}:{ctrl['port']}")
    print(f"[MIDDLEWARE SERVER] Aguardando conexões de clientes em http://{host}:{port}")
    print(f"[MIDDLEWARE SERVER] Ctrl+C para encerrar.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MIDDLEWARE SERVER] 🛑 Encerrando servidor.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Middleware XML-RPC Server — Estufa Agrícola")
    parser.add_argument("--host", default=config.MIDDLEWARE_HOST, help="Server host")
    parser.add_argument("--port", default=config.MIDDLEWARE_PORT, type=int, help="Server port")
    args = parser.parse_args()

    iniciar_servidor(host=args.host, port=args.port)
