# Atividade Prática 9 — Observabilidade, Métricas e Injeção Controlada de Falhas

Implementação de um serviço HTTP de ingestão de telemetria e um executor concorrente de benchmark para avaliação de métricas de latência (`média`, `p50`, `p95`, `p99`), vazão (*throughput*), taxa de erros, logs estruturados (`.jsonl`) e correlação distribuída (`X-Correlation-ID`) sob cenários controlados de falha.

---

## 1. Arquitetura e Estrutura do Projeto

O projeto utiliza exclusivamente a **biblioteca padrão do Python 3** (`http.server`, `urllib.request`, `concurrent.futures`, `threading`, `json`, `time`, `uuid`, `random`, `socket`), dispensando pacotes externos ou ambientes virtuais.

```text
atividade_pratica9/
├── server.py                  # Servidor HTTP concorrente (ThreadingHTTPServer) + injeção determinística de falhas
├── experiment.py              # Orquestrador de carga, cálculo de percentis (p50/p95/p99) e exportação de resultados
├── README.md                  # Instruções de execução, metodologia e análise dos resultados
├── logs/
│   └── telemetry.jsonl        # Logs estruturados em JSON Lines (eventos de cliente e servidor correlacionados)
└── results/
    └── metrics.json           # Métricas consolidadas por cenário (latência, throughput e contagem de falhas)
```

---

## 2. Instruções de Execução

### Pré-requisitos
- Python 3.9+ instalado no sistema.

### Executar o Experimento Completo
A partir da raiz do repositório (ou de dentro da pasta `atividade_pratica9`), execute:

```powershell
python atividade_pratica9/experiment.py
```

O script:
1. Inicia o `ThreadingHTTPServer` em uma thread de background em uma porta local livre (`127.0.0.1:0`).
2. Executa sequencialmente os 3 cenários (`nominal`, `latency_spike` e `intermittent_error`), disparando `100` requisições por cenário com `10` workers concorrentes e timeout de cliente configurado em `200 ms`.
3. Registra `600` eventos estruturados (`300` de cliente e `300` de servidor) em `atividade_pratica9/logs/telemetry.jsonl`.
4. Exporta as métricas agregadas em `atividade_pratica9/results/metrics.json` e imprime a tabela comparativa no terminal.

### Validar Integridade dos Logs Gerados
Para verificar que todos os registros JSONL foram gravados e correlacionados corretamente:

```powershell
python -c "import json, pathlib; p = pathlib.Path('atividade_pratica9/logs/telemetry.jsonl'); lines = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]; print(f'Total: {len(lines)} | Client: {sum(r[\"component\"]==\"client\" for r in lines)} | Server: {sum(r[\"component\"]==\"server\" for r in lines)} | Correlation IDs únicos: {len({r[\"correlation_id\"] for r in lines})}')"
```

---

## 3. Metodologia e Cenários de Injeção de Falhas

A injeção de falhas no endpoint `POST /api/v1/telemetry` é controlada pelo cabeçalho `X-Fault-Mode` combinado ao número sequencial da requisição (`X-Request-Seq`), inicializando um gerador pseudoaleatório determinístico por chamada (`seed = 42000 + offset + seq`). Isso garante reprodutibilidade mesmo sob execução multithread.

| Cenário | Comportamento no Servidor | Objetivo de Observação |
| :--- | :--- | :--- |
| `nominal` | Latência de processamento uniforme entre `5 ms` e `20 ms`; `100%` `HTTP 200 OK`. | Linha de base (*baseline*) de latência e vazão. |
| `latency_spike` | `70%` normal (`5–20 ms`), `20%` cauda degradada (`90–160 ms`), `10%` estol severo (`260–340 ms`). | Degradação dos percentis `p95`/`p99`, disparo do timeout no cliente (`200 ms`) e trabalho órfão no servidor. |
| `intermittent_error` | Latência normal (`5–25 ms`), com probabilidade configurada de falha retornando `HTTP 503 Service Unavailable`. | Impacto de falhas rápidas de serviço na taxa de erro sem degradação de latência de cauda. |

---

## 4. Resultados Experimentais

### 4.1. Tabela Comparativa Global (Visão do Cliente)

| Cenário | Req | Sucesso | HTTP 503 | Timeouts | Taxa de Erro (%) | Throughput (req/s) | Média (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `nominal` | 100 | 100 | 0 | 0 | 0.0% | 593.17 | 13.82 | 13.73 | 20.74 | 21.58 | 22.92 |
| `latency_spike` | 100 | 92 | 0 | 8 | 8.0% | 151.23 | 54.25 | 16.87 | 207.97 | 212.66 | 215.68 |
| `intermittent_error` | 100 | 84 | 16 | 0 | 16.0% | 512.29 | 16.47 | 15.09 | 25.64 | 31.19 | 36.07 |

### 4.2. Latência Apenas das Requisições com Sucesso (`HTTP 200`)

| Cenário | Sucesso | Média Sucesso (ms) | p50 Sucesso (ms) | p95 Sucesso (ms) | p99 Sucesso (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `nominal` | 100 | 13.82 | 13.73 | 20.74 | 21.58 |
| `latency_spike` | 92 | 40.85 | 16.16 | 153.43 | 160.26 |
| `intermittent_error` | 84 | 16.24 | 14.86 | 25.93 | 31.98 |

---

## 5. Rastreabilidade por `X-Correlation-ID` e Análise Técnica

Cada requisição recebe um UUIDv5 determinístico no cabeçalho `X-Correlation-ID`, registrado tanto pelo cliente quanto pelo servidor em `logs/telemetry.jsonl`.

### 5.1. Exemplos Extraídos de `logs/telemetry.jsonl`

**1. Operação Nominal (`nominal`, `request_seq: 2`):**
```json
{"component": "server", "scenario": "nominal", "correlation_id": "65f2b906-f197-57c4-9618-c917485d41d9", "request_seq": 2, "duration_ms": 7.62, "http_status": 200, "outcome": "SUCCESS", "fault_injected": "none", "client_disconnected": false}
{"component": "client", "scenario": "nominal", "correlation_id": "65f2b906-f197-57c4-9618-c917485d41d9", "request_seq": 2, "duration_ms": 10.17, "http_status": 200, "outcome": "SUCCESS", "error_detail": null}
```

**2. Estol de Latência e Timeout no Cliente (`latency_spike`, `request_seq: 27`):**
```json
{"component": "client", "scenario": "latency_spike", "correlation_id": "b786ad5a-d848-5d2d-81a0-b79eed3a1e8c", "request_seq": 27, "duration_ms": 204.15, "http_status": null, "outcome": "TIMEOUT", "error_detail": "ClientTimeout > 200ms"}
{"component": "server", "scenario": "latency_spike", "correlation_id": "b786ad5a-d848-5d2d-81a0-b79eed3a1e8c", "request_seq": 27, "duration_ms": 309.86, "http_status": 200, "outcome": "CLIENT_TIMEOUT_DISCONNECT", "fault_injected": "severe_stall_over_200ms", "client_disconnected": true}
```

**3. Falha Rápida de Serviço (`intermittent_error`, `request_seq: 3`):**
```json
{"component": "server", "scenario": "intermittent_error", "correlation_id": "b406bc68-c8fe-5cef-bde7-13fee3f5b05b", "request_seq": 3, "duration_ms": 6.62, "http_status": 503, "outcome": "HTTP_ERROR", "fault_injected": "http_503_service_unavailable", "client_disconnected": false}
{"component": "client", "scenario": "intermittent_error", "correlation_id": "b406bc68-c8fe-5cef-bde7-13fee3f5b05b", "request_seq": 3, "duration_ms": 10.3, "http_status": 503, "outcome": "HTTP_ERROR", "error_detail": "HTTPError 503"}
```

### 5.2. Principais Conclusões
1. **Média vs. Percentis de Cauda (`p50`, `p95`, `p99`):** No cenário `latency_spike`, a mediana (`p50 = 16.87 ms`) é praticamente idêntica ao cenário `nominal` (`p50 = 13.73 ms`), e a média (`54.25 ms`) mascara o problema. Somente os percentis `p95` (`207.97 ms`) e `p99` (`212.66 ms`) expõem a degradação severa sofrida pela fração afetada das requisições.
2. **Timeouts e Trabalho Órfão:** Quando a latência injetada no servidor (`260–340 ms`) excede o limite do cliente (`200 ms`), o cliente encerra a espera e registra `TIMEOUT`, preservando a disponibilidade das threads do pool. Contudo, os logs correlacionados mostram que o servidor continua ocupando recursos até tentar escrever a resposta (`outcome: CLIENT_TIMEOUT_DISCONNECT` aos `~310 ms`), caracterizando trabalho órfão.
3. **Falhas Rápidas vs. Lentidão:** No cenário `intermittent_error`, apesar da taxa de erro de `16%` (`HTTP 503`), a vazão permanece alta (`512.29 req/s`) porque as falhas retornam imediatamente (`p95 = 25.64 ms`). Já no cenário `latency_spike`, mesmo com metade da taxa de erro (`8%`), a retenção das threads reduz a vazão em quase `75%` (`151.23 req/s`).
