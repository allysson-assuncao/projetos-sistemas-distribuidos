# AP5 — Experimentos com Interação, Falhas e Segurança

**Disciplina:** Sistemas Distribuídos  
**Base arquitetural:** Atividade Prática 2 — API REST Flask (Gerenciador de Projetos e Tarefas)  
**Tema:** Modelos Fundamentais de Interação, Falhas e Segurança

---

## Sobre o Projeto

Esta atividade submete a API REST construída na AP2 a **falhas controladas**, coletando evidências observáveis para classificar comportamentos segundo os modelos fundamentais de sistemas distribuídos: modelo de interação, modelo de falhas e modelo de segurança.

São executados **7 cenários** (6 obrigatórios + 1 bônus), com coleta automática de métricas, geração de log estruturado e tabela comparativa de resultados.

---

## Estrutura de Arquivos

```
atividade_pratica5/
├── server_lab.py          # Servidor Flask com injeção de falhas + segurança
├── experiment_runner.py   # Orquestra C1–C7 e gera os outputs
├── retry.py               # Módulo reutilizável de retry com backoff + jitter
├── auth.py                # Decorator @requer_token (Bearer Token)
├── requirements.txt       # Dependências Python (flask, requests)
├── README.md              # Documentação completa, análise de segurança e respostas
│
├── ap5.log                # Log estruturado gerado pelo runner (evidência de execução)
└── resultados.md          # Tabela comparativa gerada automaticamente
```

---

## Pré-requisitos

- Python 3.10 ou superior

---

## Instalação

```bash
# 1. Criar e ativar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows PowerShell

# 2. Instalar dependências
pip install -r requirements.txt
```

---

## Execução

### Passo 1 — Iniciar o servidor de laboratório

```bash
python server_lab.py
```

O servidor estará disponível em `http://127.0.0.1:5000` (ou `http://localhost:5000`).  
Para usar outra porta: `AP5_PORT=5001 python server_lab.py`

Para usar um token customizado (recomendado para demonstração real):
```bash
AP5_TOKEN="meu-token-secreto" python server_lab.py
```

### Passo 2 — Executar os experimentos (em outro terminal)

```bash
# Ative o ambiente virtual primeiro
source .venv/bin/activate

python experiment_runner.py
```

O runner conecta por padrão em `http://127.0.0.1:5000`, executa os 7 cenários em sequência, exibe logs no console e grava simultaneamente em `ap5.log`.  
Ao final, gera `resultados.md` com a tabela completa.

```bash
# Para servidor em porta customizada:
python experiment_runner.py --url http://127.0.0.1:5001
```

### Passo 3 — Verificar evidências

```bash
cat ap5.log         # Log estruturado por tentativa
cat resultados.md   # Tabela de hipótese/observação/conclusão
```

---

## Endpoints do Servidor de Laboratório

| Método | URI | Descrição | Proteção |
|--------|-----|-----------|----------|
| `GET` | `/projetos` | Lista projetos em memória | Nenhuma |
| `POST` | `/projetos` | Cria projeto (não idempotente — C5) | Nenhuma |
| `GET` | `/slow` | Dorme 5 s (timeout — C2) | Nenhuma |
| `GET` | `/experimento/instavel` | Atraso e falha probabilísticos (C4) | Nenhuma |
| `POST` | `/experimento/projetos-lab` | Cria projeto (seguro — C6, C7) | Bearer Token |

### Query params de `/experimento/instavel`

| Param | Tipo | Padrão | Descrição |
|---|---|---|---|
| `atraso_ms` | int | 0 | Atraso artificial em milissegundos |
| `prob_falha` | float | 0.0 | Probabilidade de retornar HTTP 503 |

---

## Cenários de Experimento

| # | Cenário | Falha Injetada | Requisito do Enunciado |
|---|---|---|---|
| C1 | **Baseline** | Nenhuma | Cenário de referência |
| C2 | **Timeout** | Servidor dorme 5 s, cliente timeout = 1 s | Diferencia timeout de crash |
| C3 | **Crash / Conexão Recusada** | Porta 9999 fechada | `ConnectionError` imediato |
| C4 | **503 + Retry + Backoff + Jitter** | `prob_falha=0.7`, `atraso_ms=50` | Retry limitado com backoff |
| C5 | **POST duplicado por retry** | 3 POSTs com mesmo payload | Efeito adverso de retry |
| C6 | **Auth 401** | Sem token / token inválido | Controle de segurança |
| C7 | **Idempotency-Key** *(bônus)* | Nenhuma | Mitigação de C5 |

### Algoritmo de Retry (C4)

```
espera = (2 ** n) * 0.2 + random.uniform(0, 0.1)
```

| Tentativa | Espera mínima | Espera máxima |
|---|---|---|
| 0 → 1 | 0.20 s | 0.30 s |
| 1 → 2 | 0.40 s | 0.50 s |
| 2 → 3 | 0.80 s | 0.90 s |

> Erros 4xx são **determinísticos** e **não** recebem retry. Apenas 5xx, `Timeout` e `ConnectionError` ativam a lógica de retry.

---

## Análise de Segurança

### Ativo protegido

O endpoint `POST /experimento/projetos-lab` cria recursos persistentes em memória. Sem controle de acesso, qualquer cliente poderia criar recursos arbitrários, poluir o estado do servidor ou explorar a lógica de negócio.

### Ameaça identificada (Threat Modeling)

| Dimensão | Detalhe |
|---|---|
| **Agente** | Cliente não autorizado com acesso à rede local (laboratório) |
| **Superfície de ataque** | Endpoint HTTP sem autenticação |
| **Ameaça** | Acesso não autorizado, criação de recursos falsos, exploração de efeitos colaterais |
| **Abuso potencial** | Enumeração de IDs, poluição de estado, teste de regras de negócio sem permissão |

### Controle aplicado: Bearer Token

O decorator `@requer_token` (em [`auth.py`](auth.py)) valida o header `Authorization: Bearer <token>` em toda requisição ao endpoint protegido:

```
Sem token        → 401 Unauthorized  {"erro": "Token ausente ou formato inválido"}
Token inválido   → 401 Unauthorized  {"erro": "Token inválido ou expirado"}
Token válido     → 201 Created       {recurso criado}
```

**Propriedades de segurança cobertas:**

- ✅ **Autenticidade:** confirma que o chamador detém o segredo compartilhado (token).
- ✅ **Autorização:** restringe a operação de criação a entidades detentoras do token.

### Limitações e o que *não* é coberto

| Propriedade | Cobertura | Justificativa |
|---|---|---|
| Confidencialidade do canal | ❌ Não coberta | Sem TLS: o token trafega em texto claro. Em produção, obrigatório HTTPS. |
| Confidencialidade do token | ❌ Não coberta | Token pré-compartilhado no ambiente; em produção, usar JWT assinado ou OAuth2. |
| Não repúdio / auditoria | ⚠️ Parcial | Logs registram chamadas, mas sem assinatura criptográfica. |
| Disponibilidade | ⚠️ Parcial | Sem rate limiting — flood de requisições pode degradar o servidor. |

### Recomendações para produção

1. **TLS obrigatório:** usar HTTPS para proteger o token em trânsito.
2. **JWT com expiração:** substituir token fixo por JWT com claims, assinatura RS256 e `exp`.
3. **Rotação de segredos:** nunca usar fallback hardcoded em código-fonte.
4. **Rate limiting:** adicionar `Flask-Limiter` para prevenir brute-force do token.
5. **Auditoria:** registrar em log imutável (append-only) cada tentativa de acesso com timestamp e IP.

---

## Questões para Análise

### Q1 — O timeout permite afirmar que o servidor falhou?

**Não.** Um `Timeout` (especificamente `ReadTimeout` na biblioteca `requests`) ocorre *após* a conexão TCP ser estabelecida com sucesso, quando o servidor não envia resposta dentro do prazo configurado pelo cliente. Isso significa que:

- O servidor **recebeu** a requisição.
- O servidor **pode ter processado** a requisição (ou ainda estar processando).
- A resposta foi enviada tarde demais, ou a rede a descartou no caminho de volta.

No **C2**, o endpoint `/slow` dorme 5 s e o cliente configura `timeout=1 s`. O cliente lança `ReadTimeout` em ~1000 ms, mas o servidor continua dormindo por mais 4 s — prova de que o servidor não falhou. Timeout é evidência de **falha de timing** (o servidor não respondeu dentro do prazo do cliente), e não de **falha de colapso** (o servidor parou de funcionar).

A consequência prática é diretamente relevante para o retry: se o cliente tentar novamente após um timeout, o servidor **pode ter processado a primeira requisição** — risco real de duplicação em operações não idempotentes (veja C5).

---

### Q2 — Qual falha foi mais difícil de distinguir apenas pelo cliente?

A mais difícil de distinguir foi **Timeout (C2) vs. Erro 503 (C4)**. Em ambos os casos, do ponto de vista do cliente, a requisição "falhou" — mas por razões completamente diferentes:

| Aspecto | C2 — Timeout | C4 — Erro 503 |
|---|---|---|
| Exceção Python | `requests.exceptions.Timeout` | `requests.exceptions.HTTPError` |
| O servidor processou? | Possivelmente sim | Não (rejeitou explicitamente) |
| Seguro fazer retry? | **Não para POST** (risco de duplicata) | Sim (servidor rejeitou sem efeito) |
| Evidência no log | Ausência de status HTTP | HTTP 503 + corpo JSON |

Além disso, distinguir **C2 (Timeout)** de um **C3 (Crash)** com timeout longo também é não trivial: se o servidor está derrubado *mas* a rede é lenta (ex.: rota com muitos hops), o cliente pode receber `ConnectTimeout` (que é subclasse de `ConnectionError` *e* de `Timeout`), tornando ambíguo se o servidor "caiu" ou "está lento". A distinção requer análise do **tipo exato de exceção** e do **tempo até a falha** (quase imediato para crash local; próximo ao valor de timeout para rede lenta).

---

### Q3 — Em qual cenário o retry melhorou o resultado? Em qual piorou?

**Retry melhorou — C4 (503 probabilístico):**  
Com `prob_falha=0.7`, o servidor retorna 503 em ~70% das chamadas individualmente, mas a probabilidade de *todas* as 4 tentativas falharem é apenas `0.7⁴ ≈ 8,2%`. O retry exponencial com jitter permitiu que a maioria das execuções recuperasse com 2–3 tentativas, sem sobrecarregar o servidor (backoff espaçou as requisições no tempo).

**Retry piorou — C5 (POST não idempotente):**  
O `POST /projetos` cria um novo recurso com ID único a cada chamada. Ao simular que o cliente "não recebeu a confirmação" e retentar 3 vezes com o mesmo payload, o servidor criou 3 projetos com nomes iguais e IDs distintos — **3 efeitos colaterais para 1 intenção de negócio**. O cliente não tem como saber (apenas observando respostas) que o servidor já processou a primeira requisição. Em sistemas reais de pagamento ou criação de pedidos, este cenário representa perda financeira ou experiência degradada para o usuário.

---

### Q4 — Que propriedade de segurança foi tratada pelo controle escolhido?

O controle de **Bearer Token** (implementado em [`auth.py`](auth.py)) trata duas propriedades da taxonomia de segurança (seção 10.5 do enunciado):

1. **Autenticidade:** o cliente prova que detém o segredo compartilhado (o token). Sem o token, a identidade não pode ser confirmada — a requisição é rejeitada com 401. O servidor sabe *quem está chamando* (ou ao menos *qual cliente detém o segredo*).

2. **Autorização:** mesmo que a autenticidade seja confirmada, o acesso ao endpoint protegido é limitado a clientes com o token correto. A autorização define *o que* uma identidade autenticada pode fazer.

**O que não foi tratado:**  
- **Confidencialidade** do canal: sem TLS, o token trafega em texto claro — uma escuta passiva (sniffing) na rede pode capturá-lo. Em produção, TLS é obrigatório.  
- **Confidencialidade** dos dados retornados: os projetos criados são visíveis sem autenticação via `GET /projetos`.

O experimento C6 demonstra as três variantes (sem token, token inválido, token válido) e confirma que o controle funciona como especificado.

---

### Q5 — Como o mesmo sistema se comportaria se dois componentes falhassem simultaneamente?

**Resposta curta: o cliente observaria `ConnectionError` — não `Timeout`.**

A distinção é técnica e importante. Em Python's `requests`:

- **`ReadTimeout`** (subclasse de `Timeout`): ocorre quando a conexão TCP *foi estabelecida* com sucesso, mas o servidor não envia dados dentro do prazo. Para isso, o servidor **deve estar de pé** e respondendo ao handshake TCP.
- **`ConnectionError`** (inclui `ConnectTimeout`): ocorre quando o *próprio handshake TCP falha* — o servidor não existe naquela porta, a porta está fechada (RST), ou o handshake expira por timeout de rede.

Se o **servidor Flask cair** (processo encerrado):
- A porta é fechada → o SO responde com `TCP RST` imediato → `ConnectionError` em < 10 ms.

Se o **servidor Flask cair E a rede estiver lenta** (pacotes demorando):
- O `TCP SYN` do cliente aguarda sem receber `SYN-ACK` → o handshake expira → `ConnectTimeout`, que é subclasse de `ConnectionError`.

Em ambos os cenários, a exceção observada é uma instância de `ConnectionError` (ou subclasse), nunca um `ReadTimeout` isolado. O **C3** demonstra o caso de servidor parado: a exceção é `ConnectionError` em < 100 ms — imediata e sem ambiguidade quanto ao processamento (o servidor definitivamente não recebeu a requisição).

A consequência prática para resiliência:
- **Crash detectado como `ConnectionError`**: sistema pode fazer retry com segurança relativa (servidor não processou).
- **Falha de rede *após* conexão estabelecida (`ReadTimeout`)**: servidor pode ter processado — retry de POST é arriscado.
- **Dois componentes falhando simultaneamente** (ex.: servidor + banco de dados interno): o cliente observa o mesmo `ConnectionError` ou `503` que observaria em falha simples. O diagnóstico do *ponto exato* de falha requer **logs no servidor** e/ou **health checks** separados — não é possível inferir apenas pelo comportamento do cliente.

---

## Tabela de Cenários Resumida

| # | Cenário | Tipo de Falha (modelo) | Retry ajuda? |
|---|---|---|---|
| C1 | Baseline | — (referência) | — |
| C2 | Timeout | Falha de timing / omissão parcial | ⚠️ Arriscado para POST |
| C3 | Crash | Falha de colapso / omissão total | ✅ Seguro (servidor não processou) |
| C4 | 503 Probabilístico | Falha transiente / timing | ✅ Melhora significativamente |
| C5 | POST duplicado | Efeito adverso de retry | ❌ Piora (multiplica efeitos) |
| C6 | 401 Unauthorized | Falha de segurança / autorização | ❌ Não (erro determinístico 4xx) |
| C7 | Idempotency-Key | Mitigação de não-idempotência | ✅ Mitiga problema de C5 |

---

## Conformidade com os Entregáveis do Enunciado

| Entregável do Enunciado | Arquivo / Seção Correspondente | Status |
|---|---|:---:|
| **Código/configuração de injeção de falhas** | [`server_lab.py`](server_lab.py), [`retry.py`](retry.py), [`auth.py`](auth.py), [`experiment_runner.py`](experiment_runner.py) | ✅ Concluído |
| **Tabela com hipótese, falha, observação, classificação e conclusão** | [`resultados.md`](resultados.md) (gerado automaticamente) | ✅ Concluído |
| **Logs ou métricas** | [`ap5.log`](ap5.log) (estruturado por tentativa com latência e status) | ✅ Concluído |
| **Breve análise de segurança** | Seção [Análise de Segurança](#análise-de-segurança) deste README | ✅ Concluído |
| **Demonstração de um cenário selecionado** | Orquestração reproduzível via [`experiment_runner.py`](experiment_runner.py) | ✅ Concluído |
| **Respostas conceituais (5 questões)** | Seção [Questões para Análise](#questões-para-análise) deste README | ✅ Concluído |

---

## Empacotamento para Submissão (.zip)

Para submissão da atividade, os seguintes arquivos essenciais compõem a entrega:

```
atividade_pratica5/
├── server_lab.py          # Servidor Flask com injeção de falhas
├── experiment_runner.py   # Orquestrador dos experimentos
├── retry.py               # Algoritmo de retry com backoff exponencial + jitter
├── auth.py                # Decorator Bearer Token
├── requirements.txt       # Dependências
├── README.md              # Relatório técnico completo e respostas às 5 questões
├── resultados.md          # Tabela markdown de resultados dos testes
└── ap5.log                # Log de evidências da execução limpa
```

> **Nota:** Pastas como `.venv/`, `__pycache__/` e artefatos de apoio interno (`artifacts/`) não precisam ser incluídos no `.zip` final de entrega.
