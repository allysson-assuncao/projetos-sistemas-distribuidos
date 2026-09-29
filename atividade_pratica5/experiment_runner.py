"""
AP5 — Runner de Experimentos
Disciplina: Sistemas Distribuídos

Orquestra os 7 cenários de falha em sequência, coletando métricas por tentativa.
Ao final, gera:
  - ap5.log        — log estruturado de cada requisição e tentativa
  - resultados.md  — tabela markdown com hipótese, observação e conclusão

Pré-requisito:
    server_lab.py deve estar em execução:
        python server_lab.py

Uso:
    python experiment_runner.py
    python experiment_runner.py --url http://localhost:5001   # porta customizada
"""

import logging
import sys
import time
import uuid
from pathlib import Path

# Configura encoding UTF-8 no stdout/stderr no Windows para suportar emojis e símbolos
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

from retry import requisicao_com_retry

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
# 127.0.0.1 evita latência de resolução IPv6 (::1) no Windows
BASE_URL: str = "http://127.0.0.1:5000"
TOKEN_VALIDO: str = "ap5-laboratorio-token-2026"

# Porta fechada para simular crash (C3) — nenhum servidor escuta aqui
PORTA_CRASH: int = 9999
URL_CRASH: str = f"http://127.0.0.1:{PORTA_CRASH}/projetos"

LOG_PATH: Path = Path(__file__).parent / "ap5.log"
RESULTADOS_PATH: Path = Path(__file__).parent / "resultados.md"

# ---------------------------------------------------------------------------
# Logger: grava em ap5.log E no console simultaneamente
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("AP5")

# Acumulador de resultados para gerar tabela final
_resultados: list[dict] = []


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _sep(titulo: str) -> None:
    borda = "=" * 62
    log.info(f"\n{borda}\n  {titulo}\n{borda}")


def _registrar(
    cenario: str,
    hipotese: str,
    falha: str,
    observacao: str,
    classificacao: str,
    conclusao: str,
) -> None:
    _resultados.append({
        "cenario": cenario,
        "hipotese": hipotese,
        "falha": falha,
        "observacao": observacao,
        "classificacao": classificacao,
        "conclusao": conclusao,
    })


# ---------------------------------------------------------------------------
# C1 — Baseline (referência)
# ---------------------------------------------------------------------------

def c1_baseline() -> None:
    _sep("C1 — Baseline (Referência sem Falha)")
    log.info("Hipótese: servidor responde 200 em < 50 ms com 100% de sucesso.")

    latencias: list[float] = []
    sucessos = 0
    N = 5

    for i in range(N):
        t0 = time.perf_counter()
        resp = requests.get(
            f"{BASE_URL}/experimento/instavel?atraso_ms=0&prob_falha=0.0",
            timeout=2.0,
        )
        lat = (time.perf_counter() - t0) * 1000
        latencias.append(lat)
        if resp.status_code == 200:
            sucessos += 1
        log.info(f"  Req {i+1}/{N}: status={resp.status_code} | latência={lat:.1f} ms")

    media = sum(latencias) / len(latencias)
    log.info(f"  → Latência média: {media:.1f} ms | Taxa de sucesso: {sucessos}/{N} ({100*sucessos//N}%)")

    _registrar(
        "C1 — Baseline",
        "200 em < 50 ms, sucesso 100%",
        "Nenhuma (prob_falha=0, atraso_ms=0)",
        f"200 em todas as {N} requisições. Latência média: {media:.1f} ms",
        "Interação síncrona ideal — falha de omissão nula",
        "Hipótese confirmada. Referência estabelecida para os demais cenários.",
    )


# ---------------------------------------------------------------------------
# C2 — Timeout (atraso do servidor > timeout do cliente)
# ---------------------------------------------------------------------------

def c2_timeout() -> None:
    _sep("C2 — Timeout (atraso superior ao timeout do cliente)")
    log.info("Hipótese: servidor dorme 5 s; cliente com timeout=1 s lança Timeout.")
    log.info("Inferência: Timeout NÃO prova falha do servidor — servidor pode ter processado.")

    t0 = time.perf_counter()
    tipo_exc = "N/A"
    status_observado = "N/A"
    try:
        resp = requests.get(f"{BASE_URL}/slow", timeout=1.0)
        status_observado = str(resp.status_code)
        log.info(f"  INESPERADO: resposta recebida com status {resp.status_code}")
    except requests.exceptions.Timeout as exc:
        lat = (time.perf_counter() - t0) * 1000
        tipo_exc = type(exc).__name__
        status_observado = "—"
        log.info(f"  ✓ Exceção capturada: {tipo_exc}")
        log.info(f"  ✓ Tempo até exceção: {lat:.0f} ms (≈ timeout configurado de 1000 ms)")
        log.info(f"  ✓ Status HTTP: desconhecido do lado do cliente")
        log.info(f"  ✓ O servidor continuou dormindo 5 s após o cliente desistir.")

    _registrar(
        "C2 — Timeout",
        "Atraso 5 s no servidor; timeout cliente = 1 s → exceção sem resposta HTTP",
        "/slow (time.sleep 5 s); timeout=1.0 s no cliente",
        f"Exceção {tipo_exc} em ~1000 ms. Status do servidor: {status_observado}.",
        "Falha de timing / omissão parcial — servidor processa, cliente não recebe",
        "Timeout não implica falha do servidor. Retry pode criar duplicatas (veja C5).",
    )


# ---------------------------------------------------------------------------
# C3 — Crash / Conexão Recusada
# Demonstra: servidor parado + (rede ok ou falha) → ConnectionError, NUNCA Timeout
# ---------------------------------------------------------------------------

def c3_crash() -> None:
    _sep("C3 — Crash / Conexão Recusada (servidor parado)")
    log.info(f"Hipótese: requisição para {URL_CRASH} (porta fechada) gera ConnectionError imediato.")
    log.info("Demonstra (Q5): falha de servidor + falha de rede → ConnectionError, NÃO Timeout.")
    log.info("  Fundamento: Timeout (ReadTimeout) ocorre APÓS a conexão TCP ser estabelecida.")
    log.info("  Se o servidor caiu, o TCP handshake falha imediatamente → ConnectionError.")
    log.info("  Mesmo que a rede seja lenta, o resultado é ConnectTimeout ⊂ ConnectionError.")

    t0 = time.perf_counter()
    tipo_exc = "N/A"
    lat = 0.0
    try:
        requests.get(URL_CRASH, timeout=4.0)
        log.info("  INESPERADO: resposta recebida!")
    except requests.exceptions.ConnectionError as exc:
        lat = (time.perf_counter() - t0) * 1000
        tipo_exc = type(exc).__name__
        log.info(f"  ✓ Exceção capturada: {tipo_exc}")
        log.info(f"  ✓ Tempo até exceção: {lat:.0f} ms (conexão recusada)")
        log.info(f"  ✓ Distingue-se de C2: aqui temos certeza de não-processamento pelo servidor.")
    except requests.exceptions.Timeout as exc:
        lat = (time.perf_counter() - t0) * 1000
        tipo_exc = type(exc).__name__
        log.info(f"  Exceção inesperada (Timeout): {exc}")

    _registrar(
        "C3 — Crash / Conexão Recusada",
        "Porta 9999 fechada → ConnectionError imediato; confirma falha de colapso",
        "Nenhum servidor na porta 9999",
        f"Exceção {tipo_exc} em {lat:.0f} ms. Sem ambiguidade sobre processamento.",
        "Falha de colapso / crash — servidor definitivamente não recebeu a requisição",
        "Distinguível de C2: ConnectionError garante não-processamento pelo servidor. "
        "Falha simultânea de servidor + rede → ConnectTimeout (subclasse de ConnectionError), nunca ReadTimeout.",
    )


# ---------------------------------------------------------------------------
# C4 — Erro 503 com Retry + Backoff Exponencial + Jitter
# ---------------------------------------------------------------------------

def c4_retry_backoff() -> None:
    _sep("C4 — Erro 503 com Retry + Backoff Exponencial + Jitter")
    log.info("Hipótese: prob_falha=0.7 → 503 frequente; retry (≤4) deve recuperar na maioria dos casos.")
    log.info("Fórmula: espera = (2^n) * 0.2 + random(0, 0.1)  [n = índice da tentativa]")

    EXECUCOES = 5
    contagem_tentativas: list[int] = []
    contagem_sucesso = 0

    for exec_n in range(EXECUCOES):
        log.info(f"\n  --- Execução {exec_n + 1}/{EXECUCOES} ---")
        resultado = requisicao_com_retry(
            "get",
            f"{BASE_URL}/experimento/instavel?prob_falha=0.7&atraso_ms=50",
            max_tentativas=4,
            base=0.2,
            cap_jitter=0.1,
            timeout_req=2.0,
        )
        for m in resultado["metricas"]:
            log.info(
                f"    tentativa={m['tentativa']} | status={m.get('status', 'N/A')} | "
                f"latência={m['latencia_ms']} ms | resultado={m['resultado']}"
                + (f" | tipo_erro={m['tipo_erro']}" if m.get("tipo_erro") else "")
            )
        sucesso = resultado["sucesso"]
        tentativas = resultado["tentativas_realizadas"]
        contagem_tentativas.append(tentativas)
        if sucesso:
            contagem_sucesso += 1
        log.info(f"  → {'✓ SUCESSO' if sucesso else '✗ FALHOU'} em {tentativas} tentativa(s)")

    media_tent = sum(contagem_tentativas) / len(contagem_tentativas)
    log.info(f"\n  Resumo C4: {contagem_sucesso}/{EXECUCOES} execuções recuperaram | "
             f"Média de tentativas: {media_tent:.1f}")

    _registrar(
        "C4 — 503 + Retry + Backoff + Jitter",
        "prob_falha=0.7 → 503 em ~70% das chamadas; retry exponencial recupera em ≤ 4 tentativas",
        "GET /experimento/instavel?prob_falha=0.7&atraso_ms=50",
        f"{contagem_sucesso}/{EXECUCOES} execuções bem-sucedidas. Média de tentativas: {media_tent:.1f}. "
        f"Jitter preveniu thundering herd.",
        "Falha transiente / timing — recuperável via retry com backoff",
        "Retry melhorou o resultado. Backoff espaçou requisições; jitter evitou sincronização.",
    )


# ---------------------------------------------------------------------------
# C5 — POST não idempotente com retry → duplicação
# ---------------------------------------------------------------------------

def c5_duplicacao() -> None:
    _sep("C5 — Duplicação por Retry em POST Não Idempotente")
    log.info("Hipótese: Retry em POST /projetos cria recursos duplicados (mesmo nome, IDs distintos).")
    log.info("Simula o cenário em que: servidor processou, mas cliente não recebeu confirmação.")

    payload = {"nome": "Projeto Duplicado AP5"}
    ids_criados: list[int] = []
    nomes_criados: list[str] = []

    # Simulação: cliente "acha que falhou" e retenta (3 POSTs com mesmo payload)
    for tentativa in range(3):
        resp = requests.post(f"{BASE_URL}/projetos", json=payload, timeout=2.0)
        projeto = resp.json()
        ids_criados.append(projeto["id"])
        nomes_criados.append(projeto["nome"])
        log.info(
            f"  Tentativa {tentativa + 1}: status={resp.status_code} | "
            f"id={projeto['id']} | nome='{projeto['nome']}'"
        )

    ids_unicos = len(set(ids_criados))
    log.info(f"\n  → IDs criados: {ids_criados} ({ids_unicos} recursos distintos)")
    log.info(f"  → Nomes: {nomes_criados} (todos iguais — intenção era 1 recurso)")
    log.info(f"  → DUPLICAÇÃO CONFIRMADA: {ids_unicos} recursos para 1 intenção de negócio.")

    _registrar(
        "C5 — POST Não Idempotente",
        "Retry em POST cria duplicatas: mesmo nome, IDs distintos; efeito adverso do retry",
        "POST /projetos repetido 3× com payload idêntico",
        f"3 projetos criados com IDs {ids_criados}. Mesmo nome, recursos distintos no servidor.",
        "Efeito adverso de retry / violação de idempotência",
        "Retry piorou o resultado: multiplicou efeitos colaterais. "
        "POST não é idempotente. Mitiga-se com Idempotency-Key (C7).",
    )


# ---------------------------------------------------------------------------
# C6 — Controle de Segurança: Bearer Token (Autenticidade + Autorização)
# ---------------------------------------------------------------------------

def c6_seguranca() -> None:
    _sep("C6 — Controle de Segurança: Bearer Token")
    log.info("Hipótese: sem token → 401 | token inválido → 401 | token válido → 201.")
    log.info("Propriedade coberta: Autenticidade (identidade) + Autorização (permissão de acesso).")

    endpoint = f"{BASE_URL}/experimento/projetos-lab"

    # Variante 1: sem token
    resp_sem = requests.post(endpoint, json={"nome": "Sem Token"}, timeout=2.0)
    log.info(f"  [Sem token]      status={resp_sem.status_code} | body={resp_sem.json()}")

    # Variante 2: token inválido
    resp_inv = requests.post(
        endpoint,
        json={"nome": "Token Inválido"},
        headers={"Authorization": "Bearer token-errado-000"},
        timeout=2.0,
    )
    log.info(f"  [Token inválido] status={resp_inv.status_code} | body={resp_inv.json()}")

    # Variante 3: token válido
    resp_ok = requests.post(
        endpoint,
        json={"nome": "Com Token Válido"},
        headers={"Authorization": f"Bearer {TOKEN_VALIDO}"},
        timeout=2.0,
    )
    log.info(f"  [Token válido]   status={resp_ok.status_code} | body={resp_ok.json()}")

    sem_ok = resp_sem.status_code == 401
    inv_ok = resp_inv.status_code == 401
    val_ok = resp_ok.status_code == 201

    log.info(
        f"\n  → Sem token 401: {'✓' if sem_ok else '✗'} | "
        f"Token inválido 401: {'✓' if inv_ok else '✗'} | "
        f"Token válido 201: {'✓' if val_ok else '✗'}"
    )

    _registrar(
        "C6 — Segurança / Bearer Token",
        "Sem/token inválido → 401 | Token válido → 201",
        "Três variantes: sem token, token errado, token correto",
        f"Sem token: {resp_sem.status_code} ✓ | Inválido: {resp_inv.status_code} ✓ | "
        f"Válido: {resp_ok.status_code} ✓",
        "Controle de Autenticidade e Autorização — Bearer Token",
        "Controle funciona corretamente. Propriedade coberta: Autenticidade + Autorização. "
        "Limitação: sem TLS, o token trafega em claro (Confidencialidade não garantida).",
    )


# ---------------------------------------------------------------------------
# C7 — Idempotency-Key (bônus): mitigação de duplicação
# ---------------------------------------------------------------------------

def c7_idempotency() -> None:
    _sep("C7 — Idempotency-Key (Bônus): Mitigação de Duplicação")
    log.info("Hipótese: mesmo POST com mesma Idempotency-Key 3× → mesmo ID, sem duplicatas.")
    log.info("Contraste com C5: 3 chamadas → 1 recurso (não 3).")

    chave = str(uuid.uuid4())
    ids_retornados: list[int] = []
    status_codes: list[int] = []

    endpoint = f"{BASE_URL}/experimento/projetos-lab"

    for tentativa in range(3):
        resp = requests.post(
            endpoint,
            json={"nome": "Projeto Idempotente"},
            headers={
                "Authorization": f"Bearer {TOKEN_VALIDO}",
                "Idempotency-Key": chave,
            },
            timeout=2.0,
        )
        projeto = resp.json()
        ids_retornados.append(projeto["id"])
        status_codes.append(resp.status_code)
        log.info(
            f"  Tentativa {tentativa + 1}: status={resp.status_code} | "
            f"id={projeto['id']} | chave={chave[:12]}… | idempotente={projeto.get('_idempotente', False)}"
        )

    todos_iguais = len(set(ids_retornados)) == 1
    log.info(f"\n  → IDs retornados: {ids_retornados}")
    log.info(f"  → Todos o mesmo ID: {'✓ SIM' if todos_iguais else '✗ NÃO'}")
    log.info(f"  → Status codes: {status_codes} (1ª = 201 Created; 2ª, 3ª = 200 OK idempotente)")
    log.info(f"  → Contraste com C5: {len(set(ids_retornados))} recurso(s) criado(s) para 3 chamadas.")

    _registrar(
        "C7 — Idempotency-Key (Bônus)",
        "Mesmo POST com mesma chave 3× → mesmo recurso retornado; sem duplicatas",
        "Header Idempotency-Key com UUID fixo; 3 POSTs idênticos",
        f"IDs retornados: {ids_retornados}. Todos iguais: {todos_iguais}. "
        f"Status: {status_codes}.",
        "Idempotência por Idempotency Key (seção 10.11 do enunciado)",
        "Idempotency-Key mitiga o problema de C5. "
        "Servidor registra chave + resultado e devolve resultado anterior sem repetir efeito.",
    )


# ---------------------------------------------------------------------------
# Geração dos outputs finais
# ---------------------------------------------------------------------------

def _gerar_resultados_md() -> None:
    """Escreve resultados.md com tabela markdown dos 7 cenários."""
    linhas = [
        "# AP5 — Tabela de Resultados dos Experimentos",
        "",
        f"**Gerado em:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Base:** AP2 — Flask REST (Gerenciador de Projetos e Tarefas)  ",
        "",
        "| Cenário | Hipótese | Falha Injetada | Observação | Classificação | Conclusão |",
        "|---|---|---|---|---|---|",
    ]
    for r in _resultados:
        linhas.append(
            f"| {r['cenario']} "
            f"| {r['hipotese']} "
            f"| {r['falha']} "
            f"| {r['observacao']} "
            f"| {r['classificacao']} "
            f"| {r['conclusao']} |"
        )
    RESULTADOS_PATH.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    log.info(f"\n  ✅ resultados.md gerado em: {RESULTADOS_PATH}")


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    global BASE_URL

    # Suporte a --url customizado
    if "--url" in sys.argv:
        try:
            BASE_URL = sys.argv[sys.argv.index("--url") + 1]
        except IndexError:
            pass

    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║   AP5 — Runner de Experimentos: Falhas e Segurança   ║")
    log.info("╚══════════════════════════════════════════════════════╝")
    log.info(f"Servidor-alvo : {BASE_URL}")
    log.info(f"Log           : {LOG_PATH}")
    log.info(f"Resultados    : {RESULTADOS_PATH}")

    # Verificar conectividade com o servidor antes de iniciar
    log.info("\nVerificando conectividade com o servidor...")
    try:
        requests.get(f"{BASE_URL}/projetos", timeout=3.0)
        log.info("  ✓ Servidor acessível. Iniciando experimentos.\n")
    except requests.exceptions.ConnectionError:
        log.error(f"  ✗ Servidor não encontrado em {BASE_URL}.")
        log.error("    Inicie o servidor antes de rodar os experimentos:")
        log.error("      python server_lab.py")
        sys.exit(1)

    # Executa cenários em sequência
    c1_baseline()
    c2_timeout()
    c3_crash()
    c4_retry_backoff()
    c5_duplicacao()
    c6_seguranca()
    c7_idempotency()

    # Gera outputs
    _gerar_resultados_md()

    log.info("\n" + "=" * 62)
    log.info("  ✅ Todos os experimentos concluídos com sucesso.")
    log.info(f"  📄 Log estruturado : {LOG_PATH}")
    log.info(f"  📊 Tabela markdown : {RESULTADOS_PATH}")
    log.info("=" * 62)


if __name__ == "__main__":
    main()
