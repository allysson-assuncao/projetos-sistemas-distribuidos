"""
Atividade Prática 2 — Sistemas Distribuídos
Cliente de Testes da API REST: Gerenciador de Projetos e Tarefas

Executa um conjunto de testes sequenciais no servidor Flask.
O servidor deve estar rodando em http://127.0.0.1:5000 antes de iniciar.

Uso:
    python client.py
"""

import requests

BASE_URL = "http://127.0.0.1:5000"
TIMEOUT_PADRAO = 5  # segundos — timeout para todas as requisições normais

# ─────────────────────────────────────────────────
# UTILITÁRIOS DE IMPRESSÃO
# ─────────────────────────────────────────────────

VERDE   = "\033[92m"
VERMELHO = "\033[91m"
AMARELO = "\033[93m"
AZUL    = "\033[94m"
NEGRITO = "\033[1m"
RESET   = "\033[0m"
CIANO   = "\033[96m"


def secao(titulo: str):
    print(f"\n{NEGRITO}{AZUL}{'=' * 60}{RESET}")
    print(f"{NEGRITO}{AZUL}  {titulo}{RESET}")
    print(f"{NEGRITO}{AZUL}{'=' * 60}{RESET}")


def resultado(metodo: str, url: str, status: int, esperado: int, corpo):
    ok = status == esperado
    cor = VERDE if ok else VERMELHO
    simbolo = "✔" if ok else "✘"
    print(f"\n  {cor}{NEGRITO}{simbolo} {metodo} {url}{RESET}")
    print(f"  Status obtido:   {cor}{status}{RESET}  |  Esperado: {esperado}")
    print(f"  Resposta: {corpo}")


def erro_conexao(metodo: str, url: str, exc: Exception):
    print(f"\n  {VERMELHO}{NEGRITO}✘ {metodo} {url}{RESET}")
    print(f"  {VERMELHO}Erro de conexão/timeout: {type(exc).__name__}: {exc}{RESET}")


# CENÁRIOS DE TESTE
def cenario_1_listar_projetos_vazio():
    """GET /projetos — lista vazia inicial."""
    secao("CENÁRIO 1: Listar projetos (lista vazia inicial)")
    url = f"{BASE_URL}/projetos"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_2_criar_projetos():
    """POST /projetos — cria dois projetos válidos."""
    secao("CENÁRIO 2: Criar projetos válidos")
    url = f"{BASE_URL}/projetos"

    payloads = [
        {"nome": "Sistema de Vendas", "descricao": "Projeto de e-commerce completo"},
        {"nome": "App Mobile", "descricao": "Aplicativo Android e iOS", "status": "ativo"},
    ]
    ids = []
    for payload in payloads:
        r = requests.post(url, json=payload, timeout=TIMEOUT_PADRAO)
        resultado("POST", url, r.status_code, 201, r.json())
        ids.append(r.json()["id"])
    return ids


def cenario_3_obter_projeto(pid: int):
    """GET /projetos/<id> — obtém projeto existente."""
    secao(f"CENÁRIO 3: Obter projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_4_criar_tarefas(pid: int):
    """POST /projetos/<id>/tarefas — cria tarefas no projeto."""
    secao(f"CENÁRIO 4: Criar tarefas no projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}/tarefas"

    payloads = [
        {"titulo": "Modelagem do banco de dados", "descricao": "Definir esquema ER", "prioridade": "alta"},
        {"titulo": "Implementar autenticação", "descricao": "JWT com refresh token", "prioridade": "alta"},
        {"titulo": "Criar tela de login", "descricao": "Design responsivo", "prioridade": "media"},
    ]
    ids = []
    for payload in payloads:
        r = requests.post(url, json=payload, timeout=TIMEOUT_PADRAO)
        resultado("POST", url, r.status_code, 201, r.json())
        ids.append(r.json()["id"])
    return ids


def cenario_5_listar_tarefas(pid: int):
    """GET /projetos/<id>/tarefas — lista tarefas do projeto."""
    secao(f"CENÁRIO 5: Listar tarefas do projeto id={pid}")
    url = f"{BASE_URL}/projetos/{pid}/tarefas"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 200, r.json())


def cenario_6_atualizar_tarefa(tid: int):
    """PATCH /tarefas/<id> — marcar tarefa como concluída (idempotente)."""
    secao(f"CENÁRIO 6: Marcar tarefa id={tid} como concluída (PATCH idempotente)")
    url = f"{BASE_URL}/tarefas/{tid}"

    print(f"\n  {CIANO}Aplicando PATCH duas vezes com os mesmos dados para demonstrar idempotência:{RESET}")
    for i in range(2):
        r = requests.patch(url, json={"status": "concluida"}, timeout=TIMEOUT_PADRAO)
        print(f"\n  Chamada {i + 1}/2:")
        resultado("PATCH", url, r.status_code, 200, r.json())


def cenario_7_atualizar_projeto(pid: int):
    """PATCH /projetos/<id> — atualizar status do projeto."""
    secao(f"CENÁRIO 7: Arquivar projeto id={pid} (PATCH)")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.patch(url, json={"status": "arquivado"}, timeout=TIMEOUT_PADRAO)
    resultado("PATCH", url, r.status_code, 200, r.json())


# ── ERROS DE APLICAÇÃO ─────────────────────────────────────────────────────────
def cenario_8_erro_projeto_nao_encontrado():
    """ERRO 1: GET /projetos/9999 — projeto inexistente (404)."""
    secao("CENÁRIO 8 [ERRO DE APLICAÇÃO 1]: Buscar projeto inexistente → 404")
    url = f"{BASE_URL}/projetos/9999"
    r = requests.get(url, timeout=TIMEOUT_PADRAO)
    resultado("GET", url, r.status_code, 404, r.json())


def cenario_9_erro_dados_invalidos():
    """ERRO 2: POST /projetos — corpo sem campos obrigatórios (400)."""
    secao("CENÁRIO 9 [ERRO DE APLICAÇÃO 2]: Criar projeto sem campos obrigatórios → 400")
    url = f"{BASE_URL}/projetos"
    payload_invalido = {"status": "invalido_mesmo"}  # sem nome, sem descricao, status inválido
    r = requests.post(url, json=payload_invalido, timeout=TIMEOUT_PADRAO)
    resultado("POST", url, r.status_code, 400, r.json())


def cenario_10_erro_delete_projeto_com_tarefas(pid: int):
    """ERRO 3 (bônus): DELETE /projetos/<id> com tarefas existentes → 409."""
    secao(f"CENÁRIO 10 [CONFLITO]: Deletar projeto id={pid} com tarefas → 409")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    resultado("DELETE", url, r.status_code, 409, r.json())


# ── TIMEOUT ────────────────────────────────────────────────────────────────────
def cenario_11_timeout():
    """TIMEOUT: GET /slow com timeout=3s — servidor demora 10s → Timeout."""
    secao("CENÁRIO 11 [FALHA DE CONECTIVIDADE]: Requisição com timeout → requests.Timeout")
    url = f"{BASE_URL}/slow"
    print(f"\n  {AMARELO}Enviando GET /slow com timeout=3s (servidor dormirá 10s)...{RESET}")
    try:
        r = requests.get(url, timeout=3)
        resultado("GET", url, r.status_code, 200, r.json())
    except requests.exceptions.Timeout as e:
        erro_conexao("GET", url, e)
        print(f"  {VERDE}✔ Timeout capturado corretamente pelo cliente!{RESET}")


# ── LIMPEZA FINAL ──────────────────────────────────────────────────────────────
def cenario_12_deletar_tarefa(tid: int):
    """DELETE /tarefas/<id> — remove uma tarefa."""
    secao(f"CENÁRIO 12: Deletar tarefa id={tid}")
    url = f"{BASE_URL}/tarefas/{tid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    # 204 No Content não tem corpo
    print(f"\n  {'✔' if r.status_code == 204 else '✘'} DELETE {url}")
    print(f"  Status obtido: {r.status_code} | Esperado: 204")


def cenario_13_deletar_projeto_apos_remover_tarefas(pid: int):
    """DELETE /projetos/<id> — deleta o projeto após remover suas tarefas."""
    secao(f"CENÁRIO 13: Deletar projeto id={pid} (após tarefas removidas)")
    url = f"{BASE_URL}/projetos/{pid}"
    r = requests.delete(url, timeout=TIMEOUT_PADRAO)
    print(f"\n  {'✔' if r.status_code == 204 else '✘'} DELETE {url}")
    print(f"  Status obtido: {r.status_code} | Esperado: 204")


# EXECUÇÃO PRINCIPAL
def main():
    print("\n" + "=" * 60)
    print("  CLIENTE DE TESTES — API REST Projetos e Tarefas")
    print("  Atividade Prática 2 — Sistemas Distribuídos")
    print("=" * 60)
    print(f"\n  Base URL : {BASE_URL}")
    print(f"  Timeout padrão: {TIMEOUT_PADRAO}s\n")

    # CENÁRIOS DE SUCESSO
    cenario_1_listar_projetos_vazio()

    projeto_ids = cenario_2_criar_projetos()
    pid_principal = projeto_ids[0]  # Projeto "Sistema de Vendas"
    pid_secundario = projeto_ids[1]  # Projeto "App Mobile"

    cenario_3_obter_projeto(pid_principal)

    tarefa_ids = cenario_4_criar_tarefas(pid_principal)
    tid_principal = tarefa_ids[0]

    cenario_5_listar_tarefas(pid_principal)

    cenario_6_atualizar_tarefa(tid_principal)

    cenario_7_atualizar_projeto(pid_secundario)

    # CENÁRIOS DE ERRO
    cenario_8_erro_projeto_nao_encontrado()

    cenario_9_erro_dados_invalidos()

    cenario_10_erro_delete_projeto_com_tarefas(pid_principal)

    # CENÁRIO DE TIMEOUT
    cenario_11_timeout()

    # LIMPEZA / DEMONSTRAÇÃO DO DELETE
    # Remove todas as tarefas do projeto principal para então deletá-lo
    for tid in tarefa_ids:
        cenario_12_deletar_tarefa(tid)

    cenario_13_deletar_projeto_apos_remover_tarefas(pid_principal)

    print(f"\n\n{NEGRITO}{VERDE}{'=' * 60}")
    print("  TODOS OS CENÁRIOS EXECUTADOS COM SUCESSO!")
    print(f"{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
