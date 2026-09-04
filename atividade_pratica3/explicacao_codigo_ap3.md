# Explicação dos Componentes - Atividade Prática 3 (MQTT)

Este documento descreve detalhadamente o fluxo, objetivos e estrutura dos 6 principais arquivos do projeto, com o intuito de apoiar a apresentação da atividade. 

Os arquivos estão divididos nas seguintes categorias:
- **Publishers (Publicadores):** Sensores que enviam dados para o broker.
- **Subscribers (Assinantes):** Clientes que recebem e processam os dados.
- **Orquestração e Análise:** Scripts que automatizam os testes e geram métricas.

---

## 1. `src/pub_porta.py`
**Objetivo Principal:** Atua como um sensor de segurança da porta da frente. Publica o estado da porta ("Aberta" ou "Fechada") e demonstra funcionalidades avançadas do MQTT: **LWT (Last Will and Testament)** e **Mensagens Retidas (Retained)**.

**Parâmetros de Linha de Comando:**
- `--qos`: Nível de Qualidade de Serviço (0, 1 ou 2). Padrão: 1.
- `--count`: Quantidade de mensagens a publicar. Padrão: 60.
- `--interval`: Intervalo entre as mensagens.
- `--simulate-crash`: Se fornecido, simula uma falha abrupta (morte do processo) na metade da execução para forçar o Broker a disparar a mensagem de LWT.

**Ordem de Chamada das Funções:**
1. `main()`: Inicia o parsing dos argumentos, abre o arquivo CSV de log e configura o cliente MQTT.
2. `client.will_set()`: Configura a mensagem de testamento (LWT) **antes** de conectar.
3. `client.connect()`: Estabelece a conexão com o broker (o que aciona o callback `on_connect` de forma assíncrona).
4. Laço `for` em `main()`: Loop de publicação. Dentro do loop, `client.publish()` é chamado. Isso gera chamadas assíncronas para `on_publish` quando o ACK é recebido.
5. Em caso de crash simulado: `os._exit(1)` mata o processo. Senão, ao final, chama `client.disconnect()`.

**Laços de Repetição:**
- `for seq in range(args.count):` Itera para enviar o número exato de mensagens solicitadas, alternando os estados e publicando no broker.

**Laços de Decisão Principais:**
- `if random.random() < 0.3:` Decide aleatoriamente (30% de chance) se o estado da porta vai mudar nesta iteração.
- `if seq == crash_seq:` Interrompe o programa abruptamente se a simulação de falha estiver ativada.
- `if reason_code == 0:` (No `on_connect`) Verifica se a conexão com o broker foi bem-sucedida.

---

## 2. `src/pub_temperatura.py`
**Objetivo Principal:** Atua como o sensor de temperatura da sala. Diferente do sensor de porta, ele foca na publicação contínua de valores numéricos sem o uso de LWT ou retain, permitindo analisar o comportamento puro dos níveis de QoS.

**Parâmetros de Linha de Comando:**
- `--qos`: Nível de QoS (0, 1 ou 2). Padrão: 0.
- `--count`: Número de mensagens. Padrão: 60.
- `--interval`: Intervalo de tempo entre as publicações.

**Ordem de Chamada das Funções:**
1. `main()`: Lê argumentos, prepara CSV, instancia o cliente MQTT e vincula os callbacks `on_connect` e `on_publish`.
2. `client.connect()`: Conecta ao broker (aciona `on_connect`).
3. Laço `for` em `main()`: Gera e publica dados. `client.publish()` aciona posteriormente `on_publish`.
4. Encerramento: Para o loop do MQTT, fecha o arquivo e desconecta.

**Laços de Repetição:**
- `for seq in range(args.count):` Itera enviando mensagens. Em cada iteração, calcula uma nova temperatura variando sobre uma base (`random.gauss`).

**Laços de Decisão Principais:**
- Tratamento de exceção `except KeyboardInterrupt:` Permite que o usuário interrompa com Ctrl+C, saindo graciosamente.

---

## 3. `src/sub_alarme.py`
**Objetivo Principal:** Representa a Central de Alarme da casa. É um assinante crítico que monitora o tópico da porta (`casa/frente/porta`) e o tópico de status do sistema (`casa/status/sensores`). É responsável por detectar perdas de mensagens (verificando a sequência) e falhas nos sensores (recebendo LWT).

**Parâmetros de Linha de Comando:**
- `--qos`: Nível de QoS com o qual a inscrição (subscribe) será feita.
- `--output`: Nome customizado para o arquivo de saída (opcional).
- `--timeout`: Tempo máximo que o script ficará executando e ouvindo mensagens.

**Ordem de Chamada das Funções:**
1. `main()`: Lê argumentos, abre CSV e configura cliente MQTT.
2. `client.connect()`: Conecta. (Isto dispara o `on_connect`).
3. `on_connect()`: Dentro deste callback, o cliente assina os tópicos de interesse (`client.subscribe`).
4. `client.loop_start()`: Roda uma thread em background para receber pacotes da rede.
5. `on_message()`: Invocada a cada nova mensagem recebida pelo broker. Faz toda a lógica de validação.
6. A função `main()` apenas entra em estado de espera (`time.sleep(timeout)`) até o tempo acabar ou o usuário pressionar Ctrl+C.

**Laços de Repetição:**
- O loop de escuta de mensagens é gerenciado internamente pela biblioteca Paho MQTT após chamar `loop_start()`.

**Laços de Decisão Principais (em `on_message`):**
- `if msg.topic == config.TOPIC_STATUS and dado == "OFFLINE":` Identifica e soa o alarme de que um sensor caiu (LWT recebido).
- `if msg.topic == config.TOPIC_PORTA and seq != -1:` Inicia o bloco de verificação de integridade da mensagem.
  - `if seq > state["seq_esperado"]:` Detecta que houve **perda** de pacote (salto na sequência).
  - `elif seq < state["seq_esperado"]:` Detecta que o pacote é uma **duplicata**.

---

## 4. `src/sub_dashboard.py`
**Objetivo Principal:** Atua como um painel geral de visualização. Mostra o uso do recurso **Wildcard** do MQTT (`casa/#`) para assinar *todos* os tópicos da casa simultaneamente. Ele escuta de forma genérica e formata as saídas na tela dependendo do tópico que chegar.

**Parâmetros de Linha de Comando:**
- `--qos` e `--timeout`: Seguem o mesmo padrão do `sub_alarme.py`.

**Ordem de Chamada das Funções:**
1. `main()` -> `client.connect()` (chama `on_connect`) -> `loop_start()` -> `time.sleep()`.
2. `on_connect()` assina o tópico wildcard: `client.subscribe("casa/#")`.
3. `on_message()`: Disparada para **qualquer** mensagem que chegue da árvore `casa/`.

**Laços de Repetição:**
- O mesmo modelo gerenciado pela thread background `loop_start()`.

**Laços de Decisão Principais (em `on_message`):**
- `if msg.retain:` Incrementa o contador de mensagens retidas recebidas (útil no cenário 5, de assinante tardio).
- `if msg.topic == config.TOPIC_TEMPERATURA: ... elif msg.topic == config.TOPIC_PORTA: ... elif msg.topic == config.TOPIC_STATUS: ...`: Define a formatação visual específica para printar na tela de acordo com a origem do dado.

---

## 5. `experiments/run_experiment.py`
**Objetivo Principal:** Orquestrador automatizado. Para não ter que iniciar vários terminais na mão, este script usa a biblioteca `subprocess` do Python para iniciar instâncias de Publishers e Subscribers de forma sincronizada, simulando cenários complexos (QoS 0, 1, 2, falhas, e subscribers tardios).

**Parâmetros de Linha de Comando:**
- `--count` e `--interval`: Repassa essas configurações para os subprocessos de publisher.

**Ordem de Chamada das Funções:**
1. `main()`: A função principal invoca a função auxiliar `run_scenario()` múltiplas vezes, uma para cada experimento da atividade.
2. `run_scenario()`:
   - Usa `subprocess.Popen` para subir todos os scripts *Subscribers*.
   - Aguarda alguns segundos (`time.sleep`).
   - Usa `subprocess.Popen` para iniciar o *Publisher*.
   - `pub.wait()`: Trava a execução do orquestrador aguardando o Publisher concluir sua tarefa de envios.
   - Percorre a lista de Subscribers chamando o comando `terminate()` para matá-los.

**Laços de Repetição:**
- `for cmd in sub_cmds:` Itera a lista de comandos para subir os subscribers.
- `for p in procs:` Itera a lista de processos para mandar o sinal de terminação e forçar o fechamento (`p.wait`, `p.kill`).

**Laços de Decisão Principais:**
- Tratamento de exceção `except subprocess.TimeoutExpired:` Caso um assinante trave após o comando de terminar, ele decide forçar o fim do processo matando-o via OS (`p.kill()`).

---

## 6. `analysis/analyze.py`
**Objetivo Principal:** Script de pós-processamento de dados. Lê todos os arquivos CSV gerados pelos Subscribers durantes as simulações, cruza os dados, gera uma tabela Markdown de resultados estatísticos e renderiza gráficos.

**Parâmetros de Linha de Comando:**
- `--results`: Pasta onde os CSVs estão.
- `--output`: Pasta para onde as imagens e tabelas geradas irão.
- `--enviadas`: Quantidade base para calcular a porcentagem da Taxa de Entrega.

**Ordem de Chamada das Funções:**
1. `main()`: Configura caminhos, inicia a leitura iterando sobre `SCENARIO_MAP`.
2. Para cada cenário, chama `load_csv()` (para carregar em um DataFrame do Pandas).
3. Em seguida, passa o DataFrame para `analisa_cenario()` calcular total recebido, perdas e LWT.
4. Ao final da leitura de todos os cenários, chama as três funções renderizadoras: `gera_tabela_md()`, `gera_grafico_perdas()` e `gera_grafico_taxa()`.

**Laços de Repetição:**
- `for filename, meta in SCENARIO_MAP.items():` Laço principal para processar cada cenário simulado.
- Laços dentro das funções `gera_*`: Itera sobre o array `resultados` montado pela `main` para construir as colunas da tabela e as barras/linhas dos gráficos do matplotlib.

**Laços de Decisão Principais:**
- Exceções `except FileNotFoundError` / `except pd.errors.EmptyDataError` em `load_csv()`: Protegem o código para não quebrar caso falte algum CSV gerado nos experimentos.
- Em `analisa_cenario()`: `if "seq" in df.columns:` Verifica se a coluna de sequência de fato existe para calcular a métrica de perda com precisão.
