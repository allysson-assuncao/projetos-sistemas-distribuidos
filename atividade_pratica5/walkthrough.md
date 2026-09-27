# AP5 — Walkthrough de Execução

**Disciplina:** Sistemas Distribuídos  
**Atividade:** AP5 — Experimentos com Interação, Falhas e Segurança  
**Data de execução:** 2026-09-27  
**Base arquitetural:** AP2 — API REST Flask (Gerenciador de Projetos e Tarefas)

---

## Visão Geral do Processo

Esta atividade foi conduzida em 5 etapas definidas pelo `prompt.md` de diretiva:

```
ETAPA 1 → Leitura crítica do enunciado (PDF)
ETAPA 2 → Análise comparativa das atividades anteriores (AP1–AP4)
ETAPA 3 → Sessão /grill-me — alinhamento interativo de design
ETAPA 4 → Elaboração do plano de implementação
ETAPA 5 → Implementação, validação e commit
```

---

## ETAPA 1 — Análise do Enunciado

**Fonte:** `Enunciado Atividade Prática 5 - SD.pdf`

Requisitos mapeados:

| Requisito | Atendido por |
|---|---|
| ≥ 4 cenários de falha distintos | C1–C6 (6 cenários obrigatórios) |
| Coleta de duração, resultado e tipo de erro por tentativa | `retry.py` + `ap5.log` |
| Cenário com retry limitado e backoff | C4 (backoff exponencial + jitter) |
| Efeito adverso de retry / não idempotência | C5 (POST duplicado) |
| Controle de segurança | C6 (Bearer Token, auth.py) |
| Hipóteses definidas por cenário | Seção 3 do `implementation_plan.md` |
| Tabela de resultados | `resultados.md` (gerado em runtime) |
| Análise de segurança | Seção "Análise de Segurança" do README |
| 5 questões conceituais respondidas | Seção "Questões para Análise" do README |

---

## ETAPA 2 — Análise Comparativa das Bases

| Base | Pontuação | Justificativa |
|---|---|---|
| **AP2 — Flask REST** | ⭐⭐⭐⭐⭐ | Alinhado com exemplos do PDF; operações POST não idempotentes; HTTP status codes legíveis; setup mínimo |
| AP4 — gRPC | ⭐⭐⭐ | Tem `--delay` para deadline, mas protocolo binário dificulta observabilidade |
| AP1 — Sockets TCP | ⭐⭐ | Base simples, mas sem abstração de segurança ou status codes |
| AP3 — MQTT | ⭐ | Exige broker Docker; paradigma pub/sub menos adequado para cenários de falha HTTP |

**Decisão:** AP2 escolhida.

---

## ETAPA 3 — Sessão /grill-me (Decisões de Design)

| Pergunta | Resposta acordada |
|---|---|
| Base arquitetural | AP2 — Flask REST |
| Cenários | C1 Baseline, C2 Timeout, C3 Crash, C4 503+Retry, C5 POST duplicado, C6 Auth 401, C7 Idempotency-Key (bônus) |
| Fórmula de retry | `espera = (2^n) * 0.2 + random.uniform(0, 0.1)` · máx 4 tentativas |
| Controle de segurança | Bearer Token via `Authorization` header → 401 se ausente/inválido |
| Bônus | C7 — `Idempotency-Key` mitiga duplicação do C5 |
| Formato de evidências | `ap5.log` estruturado + `resultados.md` gerado automaticamente |

---

## ETAPA 4 — Plano de Implementação

Plano detalhado em: [`implementation_plan.md`](implementation_plan.md)

Arquivos planejados:

```
server_lab.py          — Servidor Flask com injeção de falhas e segurança
retry.py               — Módulo reutilizável de retry com backoff/jitter
auth.py                — Decorator @requer_token (Bearer Token)
experiment_runner.py   — Orquestrador dos 7 cenários + gerador de outputs
README.md              — Documentação, instruções de execução + questões respondidas
```

---

## ETAPA 5 — Implementação e Validação

### Arquivos criados

| Arquivo | Responsabilidade |
|---|---|
| [`server_lab.py`](server_lab.py) | Flask com `/projetos`, `/slow`, `/experimento/instavel`, `/experimento/projetos-lab` |
| [`auth.py`](auth.py) | Decorator `@requer_token`; lê token de `$AP5_TOKEN` |
| [`retry.py`](retry.py) | `requisicao_com_retry()`: retry 5xx + network, sem retry 4xx |
| [`experiment_runner.py`](experiment_runner.py) | Executa C1–C7, grava `ap5.log` e `resultados.md` |
| [`README.md`](README.md) | Instalação, execução, análise de segurança, 5 questões respondidas |
| [`requirements.txt`](requirements.txt) | `flask>=3.0.0`, `requests>=2.31.0` |

### Evidências de execução (run de validação — 2026-09-27 09:55)

| Cenário | Exceção / Status observado | Resultado | Evidência-chave |
|---|---|---|---|
| **C1 Baseline** | HTTP 200 | ✅ Hipótese confirmada | Latência média ~2 ms, 5/5 sucesso |
| **C2 Timeout** | `ReadTimeout` em 1002 ms | ✅ Hipótese confirmada | Cliente lança exceção; servidor seguiu dormindo |
| **C3 Crash** | `ConnectionError` em **1 ms** | ✅ Hipótese confirmada + Q5 verificada | Imediato — não há ambiguidade de processamento |
| **C4 Retry + Backoff** | HTTP 503 → recuperação | ✅ 4/5 execuções recuperaram | Média 2,4 tentativas; esperas escalonadas visíveis no log |
| **C5 POST duplicado** | HTTP 201 × 3 | ✅ Duplicação demonstrada | IDs [1, 2, 3] para 1 intenção de negócio |
| **C6 Auth 401** | 401 / 401 / 201 | ✅ Controle funcionou | `propriedade_violada` no corpo do erro |
| **C7 Idempotency-Key** | 201 → 200 → 200 | ✅ IDs [5, 5, 5] — sem duplicata | `_idempotente: true` na 2ª e 3ª resposta |

> **Nota C4:** A execução 5/5 esgotou as 4 tentativas com `prob_falha=0.7`. Isso é **comportamento esperado** — probabilidade de falhar 4 vezes consecutivas é `0.7⁴ ≈ 8,2%`. O runner registra o caso no log e na tabela.

### Verificação técnica — Q5 (servidor + rede falham simultaneamente)

```
C3 log: "Exceção ConnectionError em 1 ms (imediato — conexão recusada)"
```

**Fundamento:** `ReadTimeout` (subclasse de `Timeout`) ocorre apenas *após* a conexão TCP ser estabelecida. Se o servidor caiu, o handshake TCP falha → `ConnectionError` (ou `ConnectTimeout` ⊂ `ConnectionError` se a rede também for lenta). Em nenhum cenário de crash o resultado é um `ReadTimeout` isolado.

---

## Como Executar

```bash
# 1. Ambiente virtual
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Terminal 1 — Servidor
python server_lab.py

# 3. Terminal 2 — Experimentos
python experiment_runner.py

# 4. Verificar outputs
cat ap5.log
cat resultados.md
```

---

## Checklist de Entregáveis do Enunciado

- [x] Código de injeção de falhas → `server_lab.py` (`/experimento/instavel`, `/slow`)
- [x] Tabela com hipótese, falha, observação, classificação e conclusão → `resultados.md`
- [x] Logs ou métricas → `ap5.log` (gerado em runtime)
- [x] Breve análise de segurança → seção "Análise de Segurança" no `README.md`
- [x] Demonstração de cenário selecionado → `experiment_runner.py` (qualquer cenário é executável isoladamente)
- [x] 5 questões conceituais respondidas → seção "Questões para Análise" no `README.md`

---

## Próximos Passos (Desafios Opcionais do Enunciado)

O enunciado lista três desafios opcionais que **não foram implementados** nesta entrega. Eles representam extensões naturais caso haja interesse em aprofundamento:

### 1. Toxiproxy (ou equivalente) para atraso/perda de pacotes na camada de rede
- **O que é:** Toxiproxy é um proxy TCP configurável que permite injetar latência, jitter e perda de pacotes *na camada de rede*, de forma independente da aplicação.
- **Valor adicionado:** Os experimentos atuais injetam falhas *dentro do código Python do servidor*. Com Toxiproxy, seria possível simular falhas de rede reais (ex.: pacotes perdidos, atraso assimétrico) sem modificar o servidor — validando a resiliência em um cenário mais próximo da produção.
- **Como implementar:** Subir container `ghcr.io/shopify/toxiproxy` e configurar um proxy `localhost:5001 → localhost:5000` com toxic de `latency` ou `timeout`.

### 2. Métricas de percentis de latência (P50, P95, P99)
- **O que é:** Em vez de reportar apenas a latência média, calcular os percentis P50 (mediana), P95 e P99 das 5 execuções de cada cenário.
- **Valor adicionado:** Média mascara outliers. Em sistemas distribuídos, o P99 ("cauda longa") é o que define a experiência do usuário em pior caso e é a métrica relevante para SLAs.
- **Como implementar:** Coletar todas as latências por cenário em `experiment_runner.py` e usar `statistics.quantiles()` para calcular os percentis. Adicionar coluna "P95 (ms)" na tabela de `resultados.md`.

### 3. Circuit Breaker simples
- **O que é:** Padrão de resiliência que interrompe chamadas a um serviço degradado após um número configurável de falhas consecutivas, "abrindo o circuito" por um período de recuperação antes de tentar novamente.
- **Valor adicionado:** Complementa o retry do C4. Com o circuit breaker, após 3 falhas seguidas o cliente para de tentar por 5 s (estado "aberto"), evitando pressionar o servidor durante sua recuperação. Isso resolve o problema de thundering herd que o jitter apenas mitiga.
- **Como implementar:** Adicionar classe `CircuitBreaker` em `retry.py` com estados `FECHADO → ABERTO → SEMI_ABERTO` e integrar ao `experiment_runner.py` como C8 opcional.

---

*Gerado por Antigravity CLI — Sessão AP5 — 2026-09-27*
