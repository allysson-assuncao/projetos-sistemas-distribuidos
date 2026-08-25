# Resumo da Implementação: Atividade Prática 2

Este documento serve como um registro do desenvolvimento da Atividade Prática 2 (API REST de Gerenciamento de Projetos e Tarefas). Ele foi atualizado a cada fase concluída.

## Fase 1 — Criação do Ambiente e Dependências

- **Diretório do projeto**: Criado o diretório `atividade_pratica2`.
- **Dependências**: Gerado o arquivo `requirements.txt` com as bibliotecas `flask>=3.0.0` e `requests>=2.31.0`.
- **Ambiente Virtual**: Criado ambiente virtual local `.venv`.
- **Instalação**: Ativado o ambiente virtual e instaladas as dependências via `pip`. Verificou-se a instalação com `pip show flask requests`.

## Fase 2 — Implementação do Servidor (`server.py`)

- **Criação do Servidor**: Implementado o arquivo `server.py` contendo a API REST em Flask.
- **Armazenamento**: Configurado o armazenamento em memória (dicionários) para projetos e tarefas.
- **Modelos e Validação**: Adicionada a lógica de validação de dados para criação e atualização de projetos e tarefas.
- **Endpoints**:
  - `GET /projetos`: Listagem de projetos.
  - `POST /projetos`: Criação de projetos.
  - `GET /projetos/<id>`: Obtenção de projeto.
  - `PATCH /projetos/<id>`: Atualização de projeto.
  - `DELETE /projetos/<id>`: Remoção de projeto (com validação de dependência de tarefas retornando `409 Conflict`).
  - `GET /projetos/<id>/tarefas`: Listagem de tarefas do projeto.
  - `POST /projetos/<id>/tarefas`: Criação de tarefas.
  - `PATCH /tarefas/<id>`: Atualização de tarefa.
  - `DELETE /tarefas/<id>`: Remoção de tarefa.
- **Timeout Endpoint**: Implementada a rota `GET /slow` que simula uma resposta demorada (10 segundos) para testes de timeout.

## Fase 3 — Implementação do Cliente de Testes (`client.py`)

- **Criação do Cliente**: Implementado o arquivo `client.py` usando a biblioteca `requests`.
- **Cenários de Teste**: Codificados 13 cenários de teste sequenciais, cobrindo:
  - Casos de sucesso (CRUD completo de projetos e tarefas).
  - Testes de idempotência (ex: múltiplos `PATCH` na mesma tarefa).
  - Erros de aplicação (recursos inexistentes `404`, validação `400` e conflito de exclusão `409`).
  - Simulação de timeout acessando a rota `/slow` e capturando a exceção `requests.exceptions.Timeout`.
  - Limpeza final (remoção encadeada de tarefas e depois o projeto).
- **Formatação de Saída**: Utilizadas cores ANSI para terminal, fornecendo uma saída clara e estruturada dos resultados dos testes em relação ao status HTTP esperado.

## Fase 4 — Criação da Documentação (`README.md`)

- **Documentação Base**: Gerado o arquivo `README.md` detalhando as instruções de uso e inicialização do projeto.
- **Tabelas de API e Testes**: Incluída a documentação de todos os endpoints e dos 13 cenários cobertos pelo cliente de testes.
- **Análise Teórica**: Inserida a fundamentação acadêmica exigida pelo projeto abordando:
  - Idempotência de operações HTTP.
  - Diferenciação entre erros de aplicação (ex: HTTP 404/400) e falhas de conectividade (Timeout).
  - Decisões de design que influenciam o acoplamento entre cliente e servidor (como HATEOAS / uso de URI Location).
  - Mitigação de perda de dados via *Optimistic Locking* (ETags) em atualizações concorrentes.

## Fase 5 — Execução e Validação

- **Execução do Servidor**: O servidor `server.py` foi inicializado em um processo *background* com sucesso, expondo a API na porta local `5000`.
- **Execução do Cliente**: O script de testes `client.py` processou toda a bateria de 13 cenários em sequência.
- **Validação Visual**: Constatou-se que:
  - Todas as chamadas retornaram o *status code* esperado (como os sucessos `200`/`201` e os erros `404`/`400`/`409`).
  - O timeout na rota `/slow` foi perfeitamente interceptado pelo `requests` configurado para 3 segundos, gerando a exceção devida.
  - A limpeza de dados fluiu como planejado (`DELETE` operando idempotente com status `204`).
  - A saída terminal confirmou sucesso final com a mensagem: `"TODOS OS CENÁRIOS EXECUTADOS COM SUCESSO!"`.
- **Limpeza**: Ao finalizar as validações, encerrei o servidor para não prender processos indesejados em background.

---

## Próximos Passos (Checklist de Entrega e Apresentação)

O escopo básico obrigatório do projeto foi 100% cumprido. Para garantir uma entrega impecável de acordo com os critérios do arquivo `Atividade Prática 2.pdf`, verifique os pontos a seguir:

### 🧑‍💻 Tarefas para Você (Aluno)
1. **Ensaiar a Demonstração Prática:** A avaliação exige uma "demonstração reproduzível e objetiva". Abra dois terminais lado a lado; no primeiro suba a API com `python server.py`, e no segundo rode os testes com `python client.py` para mostrar os fluxos funcionando em tempo real.
2. **Estudar a Análise Teórica:** O professor certamente fará perguntas na demonstração. Leia atentamente a seção de "Análise Teórica" gerada no `README.md` para estar afiado nos conceitos de *Idempotência*, *Acoplamento* e a diferença entre erro de timeout vs falha HTTP `4xx/5xx`.
3. **Coletar Evidências Visuais (Opcional, mas recomendado):** Se a entrega exigir envio de arquivo (Moodle/Classroom), além de enviar a pasta zipada com os 4 arquivos (server, client, requirements, README), tire prints da tela dos testes rodando em verde no seu terminal e anexe.
4. **Empacotar a Entrega:** Crie um arquivo ZIP ou suba os arquivos num repositório Git, certificando-se de incluir a pasta `atividade_pratica2/` e ignorando a pasta `.venv`.

### 🤖 Tarefas onde Agentes IA podem te ajudar (Desafios Opcionais)
A especificação cita três "Desafios Opcionais". Se você quiser a pontuação máxima (ou um bônus da disciplina), basta me chamar novamente (ou a qualquer agente) para implementarmos:
1. **Implementar ETag / Versionamento Otimista:** Para evitar perda de atualização concorrente, podemos refatorar o `server.py` para incluir e validar cabeçalhos `ETag` e `If-Match`.
2. **Adicionar Autenticação Baseada em Token:** Podemos adicionar um simples middleware de autenticação (Bearer Token) nas rotas de alteração de estado (POST/PATCH/DELETE).
3. **Execução de Clientes Concorrentes:** Podemos criar um script secundário (`concorrente_test.py`) que lança múltiplas threads simultâneas alterando o mesmo recurso, demonstrando na prática conflitos HTTP.
