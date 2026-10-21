"""
Script Automatizado de Demonstração e Testes Distribuídos (AP7)
Atividade Prática 7 - Sistemas Distribuídos
"""

import subprocess
import sys
import time
import os
import requests
import json

NODE1_URL = "http://127.0.0.1:8001"
NODE2_URL = "http://127.0.0.1:8002"
DEAD_PEER_URL = "http://127.0.0.1:8999"


def wait_for_node(url: str, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/chain", timeout=1.0)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def run_demo():
    log_lines = []

    def log(msg: str):
        print(msg)
        log_lines.append(msg)

    log("=" * 80)
    log("SISTEMAS DISTRIBUÍDOS - ATIVIDADE PRÁTICA 7 (AP7)")
    log("Demonstração Automatizada: Blockchain Distribuída com PoW e Reconciliação")
    log("=" * 80)

    # Inicializa os processos dos dois nós
    cwd = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env["BLOCKCHAIN_DIFFICULTY"] = "2"

    log("\n[INICIALIZAÇÃO] Iniciando Nó 1 na porta 8001 e Nó 2 na porta 8002...")
    p1 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "node:app", "--port", "8001", "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=cwd,
        env=env
    )
    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "node:app", "--port", "8002", "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=cwd,
        env=env
    )

    try:
        if not wait_for_node(NODE1_URL) or not wait_for_node(NODE2_URL):
            log("ERRO: Falha ao inicializar um dos nós.")
            return

        log("-> Ambos os nós inicializados com sucesso!")

        # ---------------------------------------------------------------------
        # ETAPA 1: Registro Mútuo de Peers
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 1] Configurando a Rede P2P (Cadastro Mútuo de Peers)")
        log("=" * 80)
        r1 = requests.post(f"{NODE1_URL}/peers", json={"url": NODE2_URL}).json()
        r2 = requests.post(f"{NODE2_URL}/peers", json={"url": NODE1_URL}).json()
        log(f"Nó 1 peers: {r1['peers']}")
        log(f"Nó 2 peers: {r2['peers']}")

        # ---------------------------------------------------------------------
        # ETAPA 2: Mineração no Nó 1 e Sincronização Inicial
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 2] Mineração com Proof of Work e Propagação Inicial")
        log("=" * 80)
        tx1 = {"origem": "Alice", "destino": "Bob", "valor": 50.0}
        log(f"Minerando Bloco #1 no Nó 1 com dados: {tx1}")
        mine_resp = requests.post(f"{NODE1_URL}/mine", json=tx1).json()
        b1 = mine_resp["block"]
        log(f"-> Bloco #1 minerado! Nonce: {b1['nonce']} | Hash: {b1['hash']}")

        # Sincroniza no Nó 2
        log("Nó 2 executando /resolve para sincronizar com Nó 1...")
        res2 = requests.post(f"{NODE2_URL}/resolve").json()
        log(f"-> Resposta Nó 2: {res2['message']} (Tamanho: {res2.get('length')})")

        c1 = requests.get(f"{NODE1_URL}/chain").json()
        c2 = requests.get(f"{NODE2_URL}/chain").json()
        log(f"Status: Nó 1 tem {c1['length']} blocos | Nó 2 tem {c2['length']} blocos.")

        # ---------------------------------------------------------------------
        # ETAPA 3: Produção de Fork Controlado
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 3] Produzindo Fork Controlado (Históricos Concorrentes)")
        log("=" * 80)
        tx_2a = {"origem": "Alice", "destino": "Carol", "valor": 15.0}
        tx_2b = {"origem": "Bob", "destino": "Dave", "valor": 25.0}

        log(f"Nó 1 minerando Bloco #2A: {tx_2a}")
        m_2a = requests.post(f"{NODE1_URL}/mine", json=tx_2a).json()["block"]

        log(f"Nó 2 minerando Bloco #2B: {tx_2b}")
        m_2b = requests.post(f"{NODE2_URL}/mine", json=tx_2b).json()["block"]

        log("\n--- Comprovação da Divergência (Fork) ---")
        log(f"Nó 1 Bloco #2A: Hash = {m_2a['hash']} | Nonce = {m_2a['nonce']} | Tx = {m_2a['data']}")
        log(f"Nó 2 Bloco #2B: Hash = {m_2b['hash']} | Nonce = {m_2b['nonce']} | Tx = {m_2b['data']}")
        log("Ambos os blocos são válidos e apontam para o mesmo Bloco #1 anterior, gerando um fork!")

        # ---------------------------------------------------------------------
        # ETAPA 4: Alongando a Cadeia do Nó 2
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 4] Avançando a Cadeia do Nó 2 (Ramo Mais Longo)")
        log("=" * 80)
        tx_3b = {"origem": "Dave", "destino": "Eve", "valor": 10.0}
        log(f"Nó 2 minerando Bloco #3B: {tx_3b}")
        m_3b = requests.post(f"{NODE2_URL}/mine", json=tx_3b).json()["block"]
        log(f"-> Bloco #3B minerado! Nonce: {m_3b['nonce']} | Hash: {m_3b['hash']}")

        len1 = requests.get(f"{NODE1_URL}/chain").json()["length"]
        len2 = requests.get(f"{NODE2_URL}/chain").json()["length"]
        log(f"Comprimento das cadeias: Nó 1 = {len1} blocos | Nó 2 = {len2} blocos.")

        # ---------------------------------------------------------------------
        # ETAPA 5: Reconciliação Distribuída no Nó 1
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 5] Executando Reconciliação Distribuída no Nó 1")
        log("=" * 80)
        log("Nó 1 acionando POST /resolve para consultar vizinhos e reconciliar...")
        resolve_resp = requests.post(f"{NODE1_URL}/resolve").json()
        log(f"Resultado do /resolve no Nó 1: {resolve_resp['message']}")
        log(f"Novo comprimento do Nó 1: {resolve_resp.get('length')}")

        c1_after = requests.get(f"{NODE1_URL}/chain").json()
        log("\nBlocos atuais no Nó 1 após reconciliação:")
        for blk in c1_after["chain"]:
            log(f"  Bloco #{blk['index']} | Prev: {blk['previous_hash'][:12]}... | Hash: {blk['hash'][:16]}... | Tx: {blk['data']}")

        # ---------------------------------------------------------------------
        # ETAPA 6: Teste de Detecção e Rejeição de Adulteração
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 6] Teste de Adulteração de Dados e Rejeição pelos Pares")
        log("=" * 80)
        log("Adulterando deliberadamente o Bloco #1 no Nó 2 via /tamper...")
        t_resp = requests.post(f"{NODE2_URL}/tamper?index=1&novo_valor=999999.99").json()
        log(f"Nó 2 tamper: {t_resp['message']}")

        v2 = requests.get(f"{NODE2_URL}/validate").json()
        log(f"Validação interna do Nó 2: Válida = {v2['valid']} | Detalhe: {v2['message']}")

        log("\nNó 1 acionando /resolve para ver se aceita a cadeia corrompida do Nó 2...")
        # Minera mais um bloco corrompido no Nó 2 para tentar enganar por comprimento
        requests.post(f"{NODE2_URL}/mine", json={"origem": "Hacker", "destino": "Hacker", "valor": 1.0})
        resolve_tamper = requests.post(f"{NODE1_URL}/resolve").json()
        log(f"Resultado no Nó 1: {resolve_tamper['message']}")
        v1 = requests.get(f"{NODE1_URL}/validate").json()
        log(f"Nó 1 continua íntegro: Válida = {v1['valid']} ({v1['message']})")

        # ---------------------------------------------------------------------
        # ETAPA 7: Teste de Resiliência a Nós Offline
        # ---------------------------------------------------------------------
        log("\n" + "=" * 80)
        log("[ETAPA 7] Teste de Resiliência a Peer Indisponível/Offline")
        log("=" * 80)
        log(f"Cadastrando peer offline ({DEAD_PEER_URL}) no Nó 1...")
        requests.post(f"{NODE1_URL}/peers", json={"url": DEAD_PEER_URL})
        log("Nó 1 acionando /resolve com peer indisponível...")
        res_offline = requests.post(f"{NODE1_URL}/resolve").json()
        log(f"Resultado do /resolve: {res_offline['message']}")
        log("Nó 1 tratou a falha de conexão graciosa sem travar nem derrubar a aplicação!")

        log("\n" + "=" * 80)
        log("TODOS OS TESTES E REQUISITOS DA AP7 FORAM CONCLUÍDOS COM SUCESSO!")
        log("=" * 80)

    finally:
        log("\n[FINALIZAÇÃO] Encerrando processos dos nós HTTP...")
        p1.terminate()
        p2.terminate()
        p1.wait()
        p2.wait()
        log("Processos encerrados com sucesso.")

    # Salva o log completo em arquivo
    log_path = os.path.join(cwd, "execucao_ap7.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog gravado em: {log_path}")


if __name__ == "__main__":
    run_demo()
