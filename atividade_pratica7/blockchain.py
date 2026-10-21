"""
Módulo Blockchain com Proof of Work (PoW) e Validação de Cadeia
Atividade Prática 7 - Sistemas Distribuídos
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import time


@dataclass
class Block:
    index: int
    timestamp: str
    data: dict
    previous_hash: str
    nonce: int = 0
    hash: str = ""

    def calculate_hash(self) -> str:
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            data=data["data"],
            previous_hash=data["previous_hash"],
            nonce=data.get("nonce", 0),
            hash=data.get("hash", "")
        )


class Blockchain:
    def __init__(self, difficulty: int = 2):
        self.difficulty = difficulty
        self.chain: list[Block] = [self._genesis()]

    def _genesis(self) -> Block:
        b = Block(
            index=0,
            timestamp="2026-10-21T00:00:00Z",
            data={"msg": "genesis"},
            previous_hash="0" * 64,
            nonce=0
        )
        b.hash = b.calculate_hash()
        return b

    def mine(self, data: dict) -> Block:
        b = Block(
            index=len(self.chain),
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=data,
            previous_hash=self.chain[-1].hash
        )
        target = "0" * self.difficulty
        start_time = time.time()
        while True:
            b.hash = b.calculate_hash()
            if b.hash.startswith(target):
                break
            b.nonce += 1
        elapsed = time.time() - start_time
        self.chain.append(b)
        return b

    @staticmethod
    def valid_chain(chain: list[Block], difficulty: int = 2) -> tuple[bool, str]:
        target = "0" * difficulty
        for i, b in enumerate(chain):
            calc = b.calculate_hash()
            if b.hash != calc:
                return False, f"Bloco #{i}: hash armazenado ({b.hash[:10]}...) difere do recalculado ({calc[:10]}...)"
            
            # Blocos minerados (exceto gênesis se não tiver zeros) devem satisfazer a dificuldade
            if i > 0 and not b.hash.startswith(target):
                return False, f"Bloco #{i}: hash ({b.hash[:10]}...) nao atende a dificuldade ({target})"

            if i > 0:
                prev_b = chain[i - 1]
                if b.previous_hash != prev_b.hash:
                    return False, f"Bloco #{i}: previous_hash ({b.previous_hash[:10]}...) nao aponta para o bloco #{i-1} ({prev_b.hash[:10]}...)"
        return True, "Cadeia integra e valida"

    def valid(self) -> tuple[bool, str]:
        return self.valid_chain(self.chain, self.difficulty)
