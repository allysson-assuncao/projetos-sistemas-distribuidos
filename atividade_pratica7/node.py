"""
Nó HTTP da Blockchain Distribuída (FastAPI)
Atividade Prática 7 - Sistemas Distribuídos
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from blockchain import Block, Blockchain

app = FastAPI(title="Nó Blockchain Didática - AP7")

# Dificuldade configurável via variável de ambiente (padrão: 2 para testes rápidos e consistentes)
difficulty = int(os.environ.get("BLOCKCHAIN_DIFFICULTY", "2"))
bc = Blockchain(difficulty=difficulty)
peers: set[str] = set()


class Data(BaseModel):
    origem: str
    destino: str
    valor: float


class Peer(BaseModel):
    url: str


@app.get("/chain")
def get_chain():
    """Retorna a cadeia atual e seu comprimento."""
    return {
        "length": len(bc.chain),
        "difficulty": bc.difficulty,
        "chain": [b.to_dict() for b in bc.chain]
    }


@app.post("/mine")
def mine_block(data: Data):
    """Minera um novo bloco com Proof of Work e transação informada."""
    block = bc.mine(data.model_dump())
    return {
        "message": f"Bloco #{block.index} minerado com sucesso!",
        "block": block.to_dict()
    }


@app.post("/peers")
def add_peer(peer: Peer):
    """Registra uma URL de peer vizinho."""
    peers.add(peer.url.rstrip("/"))
    return {"peers": sorted(peers)}


@app.get("/peers")
def list_peers():
    """Lista todos os peers cadastrados."""
    return {"peers": sorted(peers)}


@app.get("/validate")
def validate_chain():
    """Verifica a integridade da cadeia local."""
    is_valid, msg = bc.valid()
    return {
        "valid": is_valid,
        "message": msg,
        "length": len(bc.chain)
    }


@app.post("/tamper")
def tamper_block(index: int = 1, novo_valor: float = 999999.99):
    """Endpoint didático para adulteração proposital de dados e teste de rejeição."""
    if index <= 0 or index >= len(bc.chain):
        raise HTTPException(status_code=400, detail="Índice de bloco inválido para adulteração")
    bc.chain[index].data["valor"] = novo_valor
    return {
        "message": f"Bloco #{index} adulterado com sucesso!",
        "block": bc.chain[index].to_dict()
    }


@app.post("/resolve")
def resolve():
    """
    Algoritmo de Reconciliação Distribuída:
    1. Consulta os peers cadastrados.
    2. Trata nós offline/indisponíveis sem interromper a execução.
    3. Para cada cadeia remota com comprimento maior que a local:
       - Reconstrói os blocos recebidos.
       - Valida hashes, encadeamento e Proof of Work.
       - Se válida e maior, adota o histórico canônico.
    """
    global bc
    replaced = False
    longest_len = len(bc.chain)
    best_chain = None

    for peer in list(peers):
        try:
            resp = requests.get(f"{peer}/chain", timeout=2.0)
            if resp.status_code != 200:
                continue
            payload = resp.json()
        except requests.RequestException:
            # Tratamento gracioso de nós offline
            continue

        remote_len = payload.get("length", 0)
        if remote_len <= longest_len:
            continue

        raw_chain = payload.get("chain", [])
        try:
            reconstructed = [Block.from_dict(b) for b in raw_chain]
        except (KeyError, TypeError):
            continue

        # Validação estrita da cadeia remota antes de adotar
        is_valid, _ = Blockchain.valid_chain(reconstructed, difficulty=bc.difficulty)
        if is_valid:
            longest_len = remote_len
            best_chain = reconstructed
            replaced = True

    if replaced and best_chain is not None:
        bc.chain = best_chain
        return {
            "message": "Cadeia local substituída pela cadeia mais longa do peer",
            "length": len(bc.chain),
            "chain": [b.to_dict() for b in bc.chain]
        }

    return {
        "message": "Cadeia local mantida (maior ou peers inválidos/iguais)",
        "length": len(bc.chain)
    }
