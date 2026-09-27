# Plano de Implementação — AP5: Experimentos com Interação, Falhas e Segurança

**Disciplina:** Sistemas Distribuídos  
**Base arquitetural:** Atividade Prática 2 — API REST Flask (Gerenciador de Projetos e Tarefas)  
**Data de elaboração:** 2026-09-27  

---

## 1. Arquitetura da Solução

```
atividade_pratica5/
│
│  ┌────────────────────────────────────────────────────────────────┐
│  │                    SERVIDOR DE LABORATÓRIO                     │
│  │   server_lab.py (Flask + middleware de falhas + segurança)     │
│  │                                                                │
│  │  Rotas originais (AP2)    +    Rota de experimento             │
│  │  GET  /projetos               GET /experimento/instavel        │
│  │  POST /projetos               POST /experimento/projetos-lab   │
│  │  GET  /slow (mantido)                                          │
│  │                                                                │
│  │  Middleware de Autenticação (Bearer Token via decorator)       │
│  └──────────────────────────────┬─────────────────────────────────┘
│                                 │ HTTP/1.1 (porta 5000)
│  ┌──────────────────────────────┼─────────────────────────────────┐
│  │                    CLIENTE DE EXPERIMENTOS                     │
│  │   experiment_runner.py                                         │
│  │                                                                │
│  │   - Executa cenários C1–C7 em sequência                       │
│  │   - Implementa retry com backoff exponencial + jitter          │
│  │   - Captura: latência, resultado, nº tentativas, tipo de erro  │
│  │   - Emite logs estruturados para ap5.log                       │
│  │   - Gera resultados.md ao final                                │
│  └──────────────────────────────┬─────────────────────────────────┘
│                                 │
│  ┌──────────────────────────────▼─────────────────────────────────┐
│  │                    OUTPUTS GERADOS                             │
│  │   ap5.log          — log estruturado por tentativa             │
│  │   resultados.md    — tabela de hipótese/observação/conclusão   │
│  └────────────────────────────────────────────────────────────────┘
```

**Fluxo de uma requisição com retry:**

```
experiment_runner
    │
    ├─[tentativa 0]──► POST /experimento/projetos-lab ──► 503 falha injetada
    │                       espera: (2^0)*0.2 + jitter ≈ 0.22s
    ├─[tentativa 1]──► POST /experimento/projetos-lab ──► 503 falha injetada
    │                       espera: (2^1)*0.2 + jitter ≈ 0.43s
    ├─[tentativa 2]──► POST /experimento/projetos-lab ──► 201 Created ✓
    └─ registra: tentativas=3, latência total, resultado=sucesso
```

---

## 2. Estrutura de Diretórios e Arquivos

```
atividade_pratica5/
│
├── server_lab.py              # Servidor Flask de laboratório (novo)
├── experiment_runner.py       # Runner de experimentos e telemetria (novo)
├── retry.py                   # Módulo de retry com backoff/jitter (novo)
├── auth.py                    # Módulo de autenticação Bearer Token (novo)
│
├── ap5.log                    # Log estruturado gerado em runtime (auto)
├── resultados.md              # Tabela de evidências gerada em runtime (auto)
│
├── implementation_plan.md     # Este arquivo
├── prompt.md                  # Diretiva de execução original
└── Enunciado Atividade Prática 5 - SD.pdf
```

### Responsabilidade de cada arquivo

| Arquivo | Responsabilidade |
|---|---|
| `server_lab.py` | Servidor Flask que herda rotas da AP2, adiciona `/experimento/instavel` (GET com `atraso_ms` e `prob_falha`) e `/experimento/projetos-lab` (POST com autenticação e suporte a `Idempotency-Key`). Expõe também endpoint para simular crash via `os._exit()` em um contexto de teste. |
| `retry.py` | Função `requisicao_com_retry(method, url, **kwargs)` com parâmetros configuráveis: `max_tentativas=4`, `base=0.2`, `cap_jitter=0.1`. Captura `Timeout`, `ConnectionError`, `HTTPError` (5xx). Retorna objeto com resultado, tentativas realizadas e métricas de latência por tentativa. |
| `auth.py` | Decorator `requer_token` e constante `TOKEN_VALIDO` (lido de variável de ambiente `AP5_TOKEN`, fallback hardcoded só para laboratório). Rejeita com `401 Unauthorized` e corpo JSON padronizado. |
| `experiment_runner.py` | Orquestra os 7 cenários em sequência. Para cada cenário: define hipótese, executa, mede, registra em log e acumula resultado para geração da tabela. Ao final, escreve `resultados.md` e `ap5.log`. |

---

## 3. Especificação dos Cenários de Teste

### C1 — Baseline (Referência)

| Campo | Valor |
|---|---|
| **Hipótese** | Sem falhas, o servidor responde com 200 em < 50ms com 100% de sucesso. |
| **Falha injetada** | Nenhuma. `prob_falha=0.0`, `atraso_ms=0`. |
| **Endpoint** | `GET /experimento/instavel?atraso_ms=0&prob_falha=0.0` |
| **Comportamento esperado** | Resposta 200, latência mínima, 0 retries. |
| **Modelo teórico** | Modelo de interação síncrono ideal. |
| **Métricas a capturar** | Latência (ms), status HTTP, nº tentativas. |

---

### C2 — Timeout (Atraso superior ao timeout do cliente)

| Campo | Valor |
|---|---|
| **Hipótese** | Com atraso de 5s no servidor e timeout do cliente de 1s, o cliente lança `Timeout` antes de receber resposta. O servidor pode ter processado a requisição mas o cliente não saberá. |
| **Falha injetada** | `atraso_ms=5000` no servidor (via `/slow` da AP2 ou `atraso_ms=5000` no endpoint lab). |
| **Endpoint** | `GET /slow` com `timeout=1` no cliente. |
| **Comportamento esperado** | `requests.exceptions.Timeout` no cliente. Status desconhecido do lado do servidor. |
| **Modelo teórico** | Falha de omissão parcial — o servidor pode ter respondido, mas a resposta chegou tarde demais. Demonstra que timeout **não** permite afirmar que o servidor falhou (Questão 1). |
| **Métricas** | Tempo até exceção, tipo de exceção, pode o servidor ter processado? |

---

### C3 — Conexão Recusada / Crash

| Campo | Valor |
|---|---|
| **Hipótese** | Com o servidor parado (porta fechada), o cliente recebe `ConnectionRefusedError` imediatamente, sem timeout. |
| **Falha injetada** | Servidor não está em execução (simulado via URL com porta errada: `http://localhost:9999`). |
| **Endpoint** | Qualquer rota em porta fechada. |
| **Comportamento esperado** | `requests.exceptions.ConnectionError` quase instantâneo (< 100ms). |
| **Modelo teórico** | Falha de colapso total — o processo servidor não existe. Diferente do timeout: aqui há certeza de que o servidor não recebeu a requisição. |
| **Métricas** | Tempo até exceção, tipo de exceção (distinguir de C2). |

---

### C4 — Erro 503 com Retry + Backoff + Jitter

| Campo | Valor |
|---|---|
| **Hipótese** | Com `prob_falha=0.7`, o servidor retorna 503 na maioria das chamadas. Com retry exponencial, o cliente deve recuperar em ≤ 4 tentativas na maior parte das execuções. |
| **Falha injetada** | `prob_falha=0.7`, `atraso_ms=100`. |
| **Endpoint** | `GET /experimento/instavel?prob_falha=0.7&atraso_ms=100` |
| **Comportamento esperado** | 0–3 falhas seguidas de sucesso. Espera acumulada entre tentativas. |
| **Modelo teórico** | Falha transiente / falha de timing. Backoff exponencial: `espera = (2^n) * 0.2 + random(0, 0.1)`. Jitter previne thundering herd. |
| **Métricas** | Nº tentativas por execução, latência total, espera acumulada. Executar 10 vezes e calcular mediana. |

---

### C5 — Duplicação por Retry em POST Não Idempotente

| Campo | Valor |
|---|---|
| **Hipótese** | Ao fazer retry de `POST /projetos` após falha temporária, o servidor cria projetos duplicados (cada POST cria um novo recurso com novo ID). |
| **Falha injetada** | Simular falha na 1ª tentativa (ex: timeout artificial) e retry manual para o mesmo POST. |
| **Endpoint** | `POST /projetos` (com retry) |
| **Comportamento esperado** | Dois ou mais projetos com nomes iguais e IDs diferentes existem no servidor. |
| **Modelo teórico** | Efeito adverso de retry em operação não idempotente. O POST falhou na rede, não no servidor — o servidor processou normalmente mas o cliente não recebeu confirmação. |
| **Métricas** | Contagem de projetos com mesmo nome após retry, IDs distintos criados. |

---

### C6 — Controle de Segurança: Bearer Token (401 Unauthorized)

| Campo | Valor |
|---|---|
| **Hipótese** | Requisições sem `Authorization: Bearer <token>` válido são rejeitadas com 401. Requisições com token correto passam. |
| **Falha injetada** | Chamada sem header, com token errado e com token correto. |
| **Endpoint** | `POST /experimento/projetos-lab` (protegido por `@requer_token`) |
| **Comportamento esperado** | Sem token → 401. Token inválido → 401. Token válido → 201. |
| **Modelo teórico** | Propriedade de segurança: Autenticidade e Autorização (seção 10.5 do enunciado). Controle de fronteira de confiança. |
| **Métricas** | Status HTTP por variante, header retornado, corpo do erro. |

---

### C7 — Idempotency-Key (Bônus: Mitigação de Duplicação)

| Campo | Valor |
|---|---|
| **Hipótese** | Ao enviar `POST /experimento/projetos-lab` com o mesmo `Idempotency-Key` header repetido 3 vezes, o servidor retorna o mesmo recurso criado na 1ª vez sem criar duplicatas. |
| **Falha injetada** | Nenhuma (cenário positivo/bônus). |
| **Endpoint** | `POST /experimento/projetos-lab` com header `Idempotency-Key: <uuid>` |
| **Comportamento esperado** | 201 na 1ª chamada, 200 + mesmo ID nas chamadas seguintes. |
| **Modelo teórico** | Idempotency Key (seção 10.11) — o servidor registra chave + resultado; reenvio retorna resultado anterior sem repetir efeito. |
| **Métricas** | IDs retornados (devem ser iguais), código HTTP por chamada (201 vs 200). |

---

## 4. Design da Lógica de Resiliência e Segurança

### 4.1 Algoritmo de Retry com Backoff Exponencial + Jitter

```
função requisicao_com_retry(method, url, max_tentativas=4, base=0.2, cap_jitter=0.1, timeout_req=1.0):
  métricas = []
  
  para tentativa em range(max_tentativas):
    t0 = agora()
    tente:
      resposta = requests[method](url, timeout=timeout_req, **kwargs)
      resposta.raise_for_status()   # lança HTTPError para 4xx/5xx
      registrar(tentativa, agora()-t0, "sucesso", resposta.status_code)
      retornar ResultadoOK(resposta, métricas)
      
    exceto (Timeout, ConnectionError, HTTPError[5xx]) como exc:
      registrar(tentativa, agora()-t0, "falha", tipo(exc))
      
      se tentativa == max_tentativas - 1:
        lançar  # esgotou tentativas
      
      espera = (2 ** tentativa) * base + random.uniform(0, cap_jitter)
      # tentativa 0: ~0.20s, tentativa 1: ~0.41s, tentativa 2: ~0.83s
      logar(f"retry em {espera:.2f}s")
      sleep(espera)
  
  # nota: HTTPError 4xx (ex: 401, 404) NÃO sofrem retry — são erros determinísticos
```

**Sequência de esperas esperadas:**
| Tentativa | Espera base | + Jitter máx | Total máx |
|---|---|---|---|
| 0→1 | 0.20s | +0.10s | ~0.30s |
| 1→2 | 0.40s | +0.10s | ~0.50s |
| 2→3 | 0.80s | +0.10s | ~0.90s |
| **Total máx** | | | **~1.70s** |

### 4.2 Mecanismo de Autenticação Bearer Token

```
# auth.py
TOKEN_VALIDO = os.environ.get("AP5_TOKEN", "ap5-laboratorio-token-2026")

def requer_token(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        header_auth = request.headers.get("Authorization", "")
        
        se header_auth não começa com "Bearer ":
            retornar jsonify({"erro": "Token ausente ou formato inválido"}), 401
        
        token = header_auth.removeprefix("Bearer ").strip()
        
        se token != TOKEN_VALIDO:
            retornar jsonify({"erro": "Token inválido"}), 401
        
        retornar f(*args, **kwargs)
    retornar decorado
```

### 4.3 Idempotency-Key Store

```
# Em server_lab.py (in-memory, suficiente para laboratório)
_idempotency_store = {}   # { idempotency_key: (status_code, response_body) }

@app.route("/experimento/projetos-lab", methods=["POST"])
@requer_token
def criar_projeto_lab():
    chave = request.headers.get("Idempotency-Key")
    
    se chave e chave in _idempotency_store:
        status, corpo = _idempotency_store[chave]
        retornar jsonify(corpo), status   # resposta idempotente
    
    # ... lógica normal de criação ...
    
    se chave:
        _idempotency_store[chave] = (201, novo_projeto)
    
    retornar jsonify(novo_projeto), 201
```

---

## 5. Critérios de Aceite e Verificação

| Requisito do Enunciado | Como será verificado |
|---|---|
| ≥ 4 cenários de falha distintos | C1–C6 = 6 cenários distintos ✓ |
| Coleta de duração, resultado e tipo de erro por tentativa | `retry.py` registra timestamp, status/tipo de exceção por tentativa; `ap5.log` persiste |
| Cenário com retry limitado e backoff | C4: `prob_falha=0.7`, max 4 tentativas, backoff exponencial com jitter ✓ |
| Cenário demonstrando efeito adverso de retry / não idempotente | C5: POST duplicado por retry ✓ |
| Controle de segurança | C6: Bearer Token + 401 ✓ |
| Hipóteses definidas | Seção 3 acima — cada cenário possui hipótese explícita ✓ |
| Logs/métricas | `ap5.log` gerado pelo runner ✓ |
| Tabela resultados | `resultados.md` gerado ao final do runner ✓ |

**Checklist do enunciado:**
- ☐ Existe cenário de referência → **C1 Baseline**
- ☐ As falhas são reproduzíveis → **parâmetros fixos + `random.seed` opcional**
- ☐ Cada cenário possui evidência → **`ap5.log` + `resultados.md`**
- ☐ Retries possuem limite e backoff → **max 4, backoff exponencial**
- ☐ A análise distingue observação de inferência → **colunas separadas na tabela**

---

## 6. Rascunho Analítico das Questões Conceituais

### Q1 — O timeout permite afirmar que o servidor falhou?

**Não.** Timeout é uma falha de omissão do ponto de vista do cliente: ele não recebeu resposta dentro do prazo definido, mas isso pode ocorrer porque: (a) o servidor ainda está processando; (b) a resposta foi enviada mas perdida na rede; (c) o servidor falhou *após* ter recebido e processado a requisição. No C2, o servidor `/slow` processa normalmente e o cliente simplesmente não espera. Timeout é evidência de **falha de timing**, não de colapso. A distinção é fundamental para decidir se é seguro fazer retry (risco de duplicação).

### Q2 — Qual falha foi mais difícil de distinguir apenas pelo cliente?

O **C2 (Timeout)** versus o **C3 (ConnectionRefused)**. Superficialmente ambos "falham", mas: C3 é instantâneo e definitivo (o servidor não existe naquela porta), enquanto C2 é temporal e ambíguo (o servidor pode ter processado). A distinção exige análise do tipo de exceção (`Timeout` vs `ConnectionError`) e do tempo até a falha. Também difícil: distinguir se um 503 (C4) é uma falha transitória recuperável ou um sinal de degradação sistêmica.

### Q3 — Em qual cenário o retry melhorou o resultado? Em qual piorou?

- **Melhorou:** C4 — o servidor retorna 503 transitório e o retry com backoff permite que o cliente recupere em ≤ 4 tentativas. Sem retry, o experimento falharia ~70% das vezes.
- **Piorou:** C5 — o retry em `POST /projetos` (não idempotente) cria recursos duplicados no servidor. O cliente recebeu falha, mas o servidor já havia criado o recurso; ao retentar, criou um segundo com ID diferente e nome igual.

### Q4 — Que propriedade de segurança foi tratada pelo controle escolhido?

O Bearer Token aborda **Autenticidade** (confirmar que o chamador é quem afirma ser — detém o token pré-compartilhado) e **Autorização** (limitar quais entidades podem acessar o endpoint protegido). A propriedade *Confidencialidade* do token em si não é garantida (sem TLS), o que seria uma limitação para produção — mencionaremos isso na análise de segurança.

### Q5 — Como o sistema se comportaria se dois componentes falhassem simultaneamente?

Se o servidor Flask e a rede falhassem ao mesmo tempo: o cliente experimentaria `ConnectionError` (indistinguível do C3). Se dois componentes upstream falhassem (ex: servidor + banco de dados), o servidor poderia processar a requisição mas retornar 503 por falha interna — tornando o comportamento idêntico ao C4 do ponto de vista do cliente. Isso ilustra o problema de diagnóstico: **falhas independentes podem ser confundidas com falhas compostas**. Um circuit breaker ajudaria a isolar o ponto de falha.

---

## 7. Resumo de Decisões Técnicas Acordadas

| Decisão | Valor |
|---|---|
| Base arquitetural | AP2 — Flask REST (Python) |
| Cenários | C1 Baseline, C2 Timeout, C3 Crash, C4 503+Retry, C5 POST duplicado, C6 Auth 401, C7 Idempotency-Key (bônus) |
| Retry: max tentativas | 4 |
| Retry: fórmula backoff | `(2^n) * 0.2 + random.uniform(0, 0.1)` |
| Segurança | Bearer Token via `Authorization` header → 401 se ausente/inválido |
| Token | Env var `AP5_TOKEN` (fallback hardcoded para laboratório) |
| Evidências | `ap5.log` (log estruturado) + `resultados.md` (tabela markdown) |
| Idempotência bônus | Idempotency-Key header + store in-memory no servidor |
