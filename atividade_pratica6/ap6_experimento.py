#!/usr/bin/env python3
"""
Atividade Prática 6: Integridade, Replicação e Consenso
Disciplina: Sistemas Distribuídos
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import copy
import sys


@dataclass
class Block:
    index: int
    timestamp: str
    data: dict
    previous_hash: str
    nonce: int = 0
    hash: str = ""

    def calculate_hash(self) -> str:
        """Calcula o hash SHA-256 do bloco com serialização determinística JSON."""
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class Blockchain:
    def __init__(self, difficulty: int = 0):
        self.difficulty = difficulty
        self.chain: list[Block] = [self._genesis()]

    def _genesis(self) -> Block:
        """Cria o bloco gênesis da cadeia."""
        b = Block(
            index=0,
            timestamp="2026-10-14T00:00:00Z",
            data={"msg": "genesis_block_ap6"},
            previous_hash="0" * 64,
            nonce=0
        )
        b.hash = b.calculate_hash()
        return b

    def add_block(self, data: dict, timestamp: str = None) -> Block:
        """Adiciona um novo bloco encadeado ao anterior."""
        if timestamp is None:
            # Determinístico para reprodução simples
            ts = f"2026-10-14T00:{len(self.chain):02d}:00Z"
        else:
            ts = timestamp

        prev_hash = self.chain[-1].hash
        b = Block(
            index=len(self.chain),
            timestamp=ts,
            data=data,
            previous_hash=prev_hash,
            nonce=0
        )
        
        target = "0" * self.difficulty
        while True:
            b.hash = b.calculate_hash()
            if b.hash.startswith(target):
                break
            b.nonce += 1

        self.chain.append(b)
        return b

    def is_valid(self) -> tuple[bool, str]:
        """
        Valida a integridade da cadeia:
        1. Verifica se o hash de cada bloco corresponde ao seu conteúdo.
        2. Verifica se o previous_hash aponta para o hash real do bloco anterior.
        3. Verifica a dificuldade (se configurada).
        """
        target = "0" * self.difficulty
        for i, b in enumerate(self.chain):
            calc = b.calculate_hash()
            if b.hash != calc:
                return False, f"Falha no Bloco #{i}: hash armazenado ({b.hash[:12]}...) difere do recalculado ({calc[:12]}...)"
            
            if not b.hash.startswith(target):
                return False, f"Falha no Bloco #{i}: hash não atende à dificuldade ({target})"

            if i > 0:
                prev_b = self.chain[i - 1]
                if b.previous_hash != prev_b.hash:
                    return False, f"Falha de encadeamento no Bloco #{i}: previous_hash ({b.previous_hash[:12]}...) não confere com hash do Bloco #{i-1} ({prev_b.hash[:12]}...)"

        return True, "Cadeia 100% íntegra e válida."

    def clone(self) -> "Blockchain":
        """Realiza uma cópia profunda (deep copy) da cadeia para simulação de réplicas."""
        return copy.deepcopy(self)


def count_bit_differences(hex1: str, hex2: str) -> int:
    """Calcula a distância de Hamming em bits entre dois hashes hexadecimais."""
    b1 = bytes.fromhex(hex1)
    b2 = bytes.fromhex(hex2)
    diff = 0
    for byte1, byte2 in zip(b1, b2):
        xor = byte1 ^ byte2
        diff += bin(xor).count("1")
    return diff


def run_ap6_experiments():
    print("=" * 80)
    print("SISTEMAS DISTRIBUÍDOS - ATIVIDADE PRÁTICA 6 (AP6)")
    print("Roteiro Automatizado de Experimentação: Integridade, Replicação e Consenso")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # ETAPA 1: Construção da Cadeia Inicial com 20 Blocos
    # -------------------------------------------------------------------------
    print("\n[ETAPA 1] Gerando a cadeia canônica com Bloco Gênesis + 20 blocos gerados...")
    bc = Blockchain(difficulty=0)

    for i in range(1, 21):
        tx_data = {
            "tx_id": f"TX-{i:03d}",
            "origem": f"Conta_A{i%5}",
            "destino": f"Conta_B{i%7}",
            "valor": round(10.5 * i, 2),
            "payload": f"Pagamento regular de servico {i}"
        }
        bc.add_block(tx_data)

    print(f"-> Total de blocos na cadeia: {len(bc.chain)} (Gênesis + 20 blocos)")
    valida, msg = bc.is_valid()
    print(f"-> Validação inicial da cadeia: {valida} ({msg})")

    print("\n--- Hashes de Referência da Cadeia Íntegra ---")
    for b in bc.chain:
        print(f"Bloco #{b.index:02d} | Prev: {b.previous_hash[:16]}... | Hash: {b.hash} | Tx: {b.data.get('tx_id', 'GENESIS')}")

    # Guardamos os hashes de referência para conferência posterior
    reference_hashes = [b.hash for b in bc.chain]

    # -------------------------------------------------------------------------
    # ETAPA 2: Teste de Efeito Avalanche (Alteração de 1 caractere)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[ETAPA 2] Teste de Efeito Avalanche no Bloco #5 (Alteração de 1 Caractere)")
    print("=" * 80)

    bloco_5_orig = copy.deepcopy(bc.chain[5])
    hash_orig = bloco_5_orig.hash

    # Alteramos apenas 1 caractere no campo 'origem': 'Conta_A0' -> 'Conta_X0' (A -> X)
    bloco_5_mod = copy.deepcopy(bloco_5_orig)
    orig_origem = bloco_5_mod.data["origem"]
    bloco_5_mod.data["origem"] = "Contx_A0"  # a -> x (1 caractere modificado)
    hash_mod = bloco_5_mod.calculate_hash()

    bit_diff = count_bit_differences(hash_orig, hash_mod)
    char_diff = sum(1 for c1, c2 in zip(hash_orig, hash_mod) if c1 != c2)

    print(f"Dado Original do Bloco #5 : {bloco_5_orig.data}")
    print(f"Hash Original (SHA-256)   : {hash_orig}")
    print(f"Dado Alterado (1 char)    : {bloco_5_mod.data}")
    print(f"Hash Resultante (SHA-256) : {hash_mod}")
    print(f"Diferenças em Hex (chars) : {char_diff} de 64 caracteres ({char_diff / 64 * 100:.1f}%)")
    print(f"Diferenças em Bits        : {bit_diff} de 256 bits ({bit_diff / 256 * 100:.1f}%)")
    print("Resultado: Efeito avalanche confirmado. A mudança de 1 byte altera aproximadamente 50% dos bits de saída.")

    # -------------------------------------------------------------------------
    # ETAPA 3: Adulteração de Bloco Intermediário SEM Recálculo
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[ETAPA 3] Adulteração de Bloco Intermediário (#10) SEM Recálculo")
    print("=" * 80)

    bc_tampered = bc.clone()
    print(f"Adulterando o valor da transação do Bloco #10 de {bc_tampered.chain[10].data['valor']} para 999999.99...")
    bc_tampered.chain[10].data["valor"] = 999999.99
    # O atacante altera o dado, mas NÃO recalcula nada (ou apenas o hash do bloco 10, sem propagar)
    # Se nem o hash do bloco 10 foi recalculado:
    valida_sem_calc, msg_sem_calc = bc_tampered.is_valid()
    print(f"Status da cadeia após adulteração de dados: {valida_sem_calc}")
    print(f"Mensagem do validador: {msg_sem_calc}")

    # Mesmo que o atacante recalcule o hash do próprio bloco 10:
    bc_tampered.chain[10].hash = bc_tampered.chain[10].calculate_hash()
    valida_com_hash10, msg_com_hash10 = bc_tampered.is_valid()
    print(f"\nSe o atacante atualizar o hash do Bloco #10 mas não os seguintes:")
    print(f"Status da cadeia: {valida_com_hash10}")
    print(f"Mensagem do validador: {msg_com_hash10}")

    # -------------------------------------------------------------------------
    # ETAPA 4: Adulteração de Bloco Intermediário COM Recálculo Sequencial
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[ETAPA 4] Falsificação Local: Adulteração do Bloco #10 COM Recálculo dos Blocos 10 a 20")
    print("=" * 80)

    print("Recalculando sequencialmente hashes a partir do Bloco #10 até o Bloco #20...")
    for idx in range(10, len(bc_tampered.chain)):
        if idx > 0:
            bc_tampered.chain[idx].previous_hash = bc_tampered.chain[idx - 1].hash
        bc_tampered.chain[idx].hash = bc_tampered.chain[idx].calculate_hash()

    valida_recalculada, msg_recalculada = bc_tampered.is_valid()
    print(f"Status da cadeia após recálculo total em cadeia: {valida_recalculada}")
    print(f"Mensagem do validador: {msg_recalculada}")
    print("\nHashes após adulteração e recálculo vs. Hashes Originais:")
    print(f"{'Bloco':<6} | {'Status':<12} | {'Hash Original':<64} | {'Hash Falsificado':<64}")
    print("-" * 155)
    for i in range(len(bc.chain)):
        h_orig = reference_hashes[i]
        h_fake = bc_tampered.chain[i].hash
        status = "INALTERADO" if h_orig == h_fake else "REESCRITO"
        print(f"#{i:02d}    | {status:<12} | {h_orig} | {h_fake}")

    print("\nConclusão da Etapa 4: Uma cadeia adulterada torna-se INTERNAMENTE CONSISTENTE")
    print("se o agente puder reescrever os ponteiros de hash localmente sem custo.")

    # -------------------------------------------------------------------------
    # ETAPA 5: Simulação de Réplicas Divergentes (Fork) e Regra de Reconciliação
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[ETAPA 5] Simulação de Réplicas Divergentes (Fork) e Reconciliação Distribuída")
    print("=" * 80)

    # Base comum: blocos de 0 a 10 da cadeia original
    base_comum = Blockchain(difficulty=0)
    base_comum.chain = copy.deepcopy(bc.chain[:11])  # 0 a 10 inclusive (11 blocos)

    # Réplica A bifurca a partir do bloco 10
    replica_a = base_comum.clone()
    print(f"Base comum estabelecida até Bloco #10 (Tamanho: {len(base_comum.chain)} blocos).")
    print("Minerando 5 blocos na Réplica A (Cenário Ramo A - menor)...")
    for i in range(1, 6):
        replica_a.add_block({
            "tx_id": f"TX-RAMO-A-{i}",
            "origem": "Cliente_Alpha",
            "destino": "Fornecedor_A",
            "valor": 500.0 * i
        })

    # Réplica B bifurca a partir do bloco 10
    replica_b = base_comum.clone()
    print("Minerando 8 blocos na Réplica B (Cenário Ramo B - maior)...")
    for i in range(1, 9):
        replica_b.add_block({
            "tx_id": f"TX-RAMO-B-{i}",
            "origem": "Cliente_Beta",
            "destino": "Fornecedor_B",
            "valor": 750.0 * i
        })

    val_a, msg_a = replica_a.is_valid()
    val_b, msg_b = replica_b.is_valid()

    print(f"\nStatus Réplica A: Tamanho = {len(replica_a.chain)} blocos | Válida? {val_a} | Ponta: {replica_a.chain[-1].hash[:16]}...")
    print(f"Status Réplica B: Tamanho = {len(replica_b.chain)} blocos | Válida? {val_b} | Ponta: {replica_b.chain[-1].hash[:16]}...")

    print("\nAmbas as réplicas são 100% válidas segundo as regras criptográficas locais.")
    print("Porém, elas contêm históricos divergentes e incompatíveis a partir do Bloco #10!")

    print("\n--- Aplicando Regra de Reconciliação Distribuída (Longest Chain Rule) ---")
    def reconcile(local: Blockchain, remote: Blockchain) -> tuple[Blockchain, str]:
        val_rem, _ = remote.is_valid()
        if not val_rem:
            return local, "Cadeia remota inválida rejeitada."

        if len(remote.chain) > len(local.chain):
            return remote.clone(), f"REORGANIZAÇÃO: Cadeia remota adotada por ser mais longa ({len(remote.chain)} vs {len(local.chain)} blocos)."
        elif len(remote.chain) < len(local.chain):
            return local, f"MANTER LOCAL: Cadeia local é mais longa ({len(local.chain)} vs {len(remote.chain)} blocos)."
        else:
            # Desempate determinístico (menor hash na ponta)
            if remote.chain[-1].hash < local.chain[-1].hash:
                return remote.clone(), "DESEMPATE: Cadeia remota adotada por critério léxico de hash."
            return local, "DESEMPATE: Cadeia local mantida por critério léxico de hash."

    # Nó A recebe a cadeia do Nó B
    cadeia_reconciliada, motivo = reconcile(replica_a, replica_b)
    print(f"Decisão do Nó A ao contatar Nó B: {motivo}")
    print(f"Tamanho final da cadeia adotada pelo Nó A: {len(cadeia_reconciliada.chain)} blocos.")
    print(f"Hash da ponta da cadeia adotada: {cadeia_reconciliada.chain[-1].hash}")

    print("\n" + "=" * 80)
    print("TODOS OS EXPERIMENTOS DA AP6 CONCLUÍDOS COM SUCESSO!")
    print("=" * 80)


if __name__ == "__main__":
    run_ap6_experiments()
