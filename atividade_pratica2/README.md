# Atividade Prática 2 — API REST: Gerenciador de Projetos e Tarefas

**Disciplina:** Sistemas Distribuídos  
**Tema:** API REST com operações CRUD sobre duas coleções relacionadas

---

## Sobre o Projeto

API REST desenvolvida em Python com Flask para gerenciar **Projetos** e **Tarefas**.  
Um projeto pode conter várias tarefas (relação 1-para-N).  
Os dados são armazenados em memória (reiniciam ao encerrar o servidor).

---

## Pré-requisitos

- Python 3.10 ou superior
- pip

---

## Instalação e Execução

### 1. Criar e ativar o ambiente virtual

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Iniciar o servidor

```bash
python server.py
```

O servidor estará disponível em `http://127.0.0.1:5000`.

### 4. Executar os testes (em outro terminal)

```bash
# Ative o ambiente virtual primeiro
.venv\Scripts\activate  # ou source .venv/bin/activate

python client.py
```

---

## Endpoints da API

| Método | URI | Descrição | Status Sucesso |
|--------|-----|-----------|----------------|
| GET | `/projetos` | Lista todos os projetos | 200 |
| POST | `/projetos` | Cria um novo projeto | 201 |
| GET | `/projetos/<id>` | Obtém um projeto pelo ID | 200 |
| PATCH | `/projetos/<id>` | Atualiza parcialmente um projeto | 200 |
| DELETE | `/projetos/<id>` | Remove um projeto | 204 |
| GET | `/projetos/<id>/tarefas` | Lista tarefas de um projeto | 200 |
| POST | `/projetos/<id>/tarefas` | Cria uma tarefa em um projeto | 201 |
| PATCH | `/tarefas/<id>` | Atualiza parcialmente uma tarefa | 200 |
| DELETE | `/tarefas/<id>` | Remove uma tarefa | 204 |
| GET | `/slow` | Endpoint lento (teste de timeout) | 200 (após 10s) |

---

## Modelos de Dados e Formatos (JSON)

A comunicação com a API (envio e recebimento de dados) é feita inteiramente utilizando o formato **JSON**. Internamente, o Flask converte automaticamente esses payloads JSON em Dicionários Python (`dict`), nos quais aplicamos os valores padrão de forma segura utilizando o método `dados.get("chave", "valor_padrao")`.

### Projeto

- **Campos Obrigatórios (POST):** `nome`, `descricao`
- **Campos Opcionais e Padrões:** Se `status` não for enviado na criação, a API assume `"ativo"` por padrão.

**Exemplo de Payload (POST - Request):**
```json
{
  "nome": "Sistema de Vendas",
  "descricao": "Projeto de e-commerce completo"
}
```

**Exemplo de Resposta (201 Created - Response):**
```json
{
  "id": 1,
  "nome": "Sistema de Vendas",
  "descricao": "Projeto de e-commerce completo",
  "status": "ativo",
  "criado_em": "2025-08-24T20:00:00"
}
```

### Tarefa

- **Campos Obrigatórios (POST):** `titulo`, `descricao`
- **Campos Opcionais e Padrões:** Se não fornecidos na criação, `status` assume `"pendente"` e `prioridade` assume `"media"`.

**Exemplo de Payload (POST - Request):**
```json
{
  "titulo": "Modelagem do banco",
  "descricao": "Definir esquema ER",
  "prioridade": "alta"
}
```

**Exemplo de Resposta (201 Created - Response):**
```json
{
  "id": 1,
  "titulo": "Modelagem do banco",
  "descricao": "Definir esquema ER",
  "status": "pendente",
  "prioridade": "alta",
  "projeto_id": 1,
  "criado_em": "2025-08-24T20:10:00"
}
```

---

## Tabela de Cenários de Teste

| # | Cenário | Método | URI | Status Esperado | Status Obtido |
|---|---------|--------|-----|-----------------|---------------|
| 1 | Listar projetos (lista vazia) | GET | /projetos | 200 | 200 |
| 2 | Criar projetos válidos | POST | /projetos | 201 | 201 |
| 3 | Obter projeto existente | GET | /projetos/1 | 200 | 200 |
| 4 | Criar tarefas em um projeto | POST | /projetos/1/tarefas | 201 | 201 |
| 5 | Listar tarefas do projeto | GET | /projetos/1/tarefas | 200 | 200 |
| 6 | Marcar tarefa como concluída (PATCH idempotente, 2x) | PATCH | /tarefas/1 | 200 | 200 |
| 7 | Arquivar projeto (PATCH) | PATCH | /projetos/2 | 200 | 200 |
| 8 | **[ERRO]** Buscar projeto inexistente | GET | /projetos/9999 | 404 | 404 |
| 9 | **[ERRO]** Criar projeto sem campos obrigatórios | POST | /projetos | 400 | 400 |
| 10 | **[CONFLITO]** Deletar projeto com tarefas | DELETE | /projetos/1 | 409 | 409 |
| 11 | **[TIMEOUT]** Requisição para endpoint lento (timeout=3s) | GET | /slow | Timeout | Timeout |
| 12 | Deletar tarefas do projeto | DELETE | /tarefas/<id> | 204 | 204 |
| 13 | Deletar projeto após remover tarefas | DELETE | /projetos/1 | 204 | 204 |

---

## Análise Teórica

### 1. Quais operações são idempotentes e por quê?

Uma operação é **idempotente** quando executá-la múltiplas vezes com os mesmos parâmetros produz sempre o mesmo estado final no servidor.

Na nossa API:

- **GET** (todos os endpoints): seguro e idempotente — apenas lê dados, nunca os modifica.
- **DELETE `/projetos/<id>` e `/tarefas/<id>`**: idempotente — após a primeira chamada o recurso é removido; chamadas subsequentes retornam 404 (o estado final do recurso é "inexistente" em ambos os casos, o efeito sobre o estado do recurso é o mesmo).
- **PATCH `/projetos/<id>` e `/tarefas/<id>`**: idempotente **quando aplicado com os mesmos valores** — aplicar `{"status": "concluida"}` dez vezes resulta no mesmo estado. Demonstrado no Cenário 6.

Não é idempotente:
- **POST `/projetos` e `/projetos/<id>/tarefas`**: cada chamada cria um novo recurso com um novo ID, alterando o estado do servidor.

### 2. Diferença entre erro do servidor e falha de conectividade

| Aspecto | Erro de aplicação (4xx/5xx) | Falha de conectividade (Timeout) |
|---|---|---|
| **O que acontece** | O servidor recebeu a requisição, processou e retornou uma resposta de erro | O cliente não recebe nenhuma resposta dentro do tempo limite |
| **Quem detecta** | O cliente recebe o status HTTP e o corpo do erro | O cliente dispara `requests.exceptions.Timeout` (ou similar) |
| **Causa** | Dado inválido, recurso não encontrado, conflito de negócio | Servidor offline, rede congestionada, servidor muito lento |
| **Exemplo na API** | GET /projetos/9999 → 404 JSON explicando o erro | GET /slow com timeout=3s → cliente lança exceção antes de receber qualquer byte |
| **Rastreabilidade** | O servidor registra a requisição no log | O servidor pode ter recebido a requisição mas o cliente nunca saberá |

### 3. Decisões da API que impactam o acoplamento cliente-servidor

O acoplamento define o quão dependente o cliente é de detalhes internos do servidor. Decisões tomadas nesta API para **reduzir** o acoplamento:

- **Uso do header `Location`**: ao criar um recurso (201 Created), o servidor retorna o URI do novo recurso no header `Location`. O cliente não precisa saber como construir o URI — ele segue o que o servidor informa (princípio HATEOAS básico).
- **URIs baseados em recursos, não em ações**: `/projetos` ao invés de `/getCriarProjeto`. O método HTTP define a ação; a URI identifica o recurso. Isso torna a interface mais estável e previsível.
- **Envelope de erro padronizado** com campos `erro` e `detalhes`: o cliente pode tratar qualquer resposta de erro da mesma forma sem conhecer detalhes internos.

Decisão que **aumenta** o acoplamento: o modelo de dados (`status`, `prioridade`) com valores específicos em português. Se o servidor mudar os valores válidos, os clientes precisam ser atualizados.

### 4. Como evitar perda de dados com atualizações concorrentes (Optimistic Locking)

O problema: dois clientes leem o Projeto 1 ao mesmo tempo, ambos fazem alterações diferentes e ambos enviam PATCH. A última atualização sobrescreve silenciosamente a primeira — **lost update**.

A solução recomendada é o **Optimistic Locking com ETag**:

1. O servidor adiciona um campo `versao` (inteiro) em cada recurso.
2. O GET retorna o recurso com sua versão atual: `{ ..., "versao": 3 }`.
3. O cliente envia o PATCH com o header `If-Match: 3`.
4. O servidor compara: se `versao_atual == versao_recebida`, aplica a mudança e incrementa `versao` para 4.
5. Se outro cliente já atualizou (versão atual é 4), o servidor rejeita com **409 Conflict** ou **412 Precondition Failed**.
6. O cliente que recebeu 412 deve recarregar o recurso e tentar novamente com a nova versão.

Essa abordagem não requer locks no servidor e é escalável para ambientes distribuídos. Nesta atividade, a versão simplificada (sem ETag) é usada por simplicidade, mas a extensão é direta.

### 5. Decisão Arquitetural: Uso do Flask (vs FastAPI)

Enquanto o laboratório de referência da apostila utilizou **FastAPI** com **Pydantic**, esta API foi intencionalmente implementada utilizando **Flask "puro"**. A justificativa técnica para essa escolha inclui:

- **Controle Manual e Transparência:** O FastAPI abstrai a validação e conversão de dados quase que "magicamente" através das classes do Pydantic (`BaseModel`). Ao utilizar o Flask, todo o processo de extração do JSON (`request.get_json()`), acesso aos dados utilizando dicionários nativos (`dict`) e a verificação manual da integridade dos campos foi implementado explicitamente (ex: funções de validação locais). Isso demonstra um entendimento profundo de como as estruturas de dados e a semântica HTTP operam na prática na linguagem Python, sem depender de camadas opacas de framework.
- **Simplicidade de Dependências:** O Flask requer uma infraestrutura base menor, e a utilização de bibliotecas nativas como `datetime` e `json` simplificou o escopo do projeto, atingindo todos os objetivos e requisitos obrigatórios da atividade sem a necessidade de adicionar múltiplos schemas ou classes de validação externa.
