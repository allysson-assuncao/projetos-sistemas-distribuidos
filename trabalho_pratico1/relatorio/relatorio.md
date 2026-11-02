# Relatório Técnico — Trabalho Prático 1: Sistemas Distribuídos
## Controle Automatizado de Estufa Agrícola com MQTT e XML-RPC

**Disciplina:** Sistemas Distribuídos  
**Tema:** Controle Automatizado de Estufa Agrícola  
**Tecnologias:** Python 3.10+, MQTT (Eclipse Mosquitto), XML-RPC  
**Modelos Aplicados:** Publicar/Assinar, RPC, Replicação Ativa com Votação Majoritária (TMR), Transferência de Estado e Deduplicação LRU  

---

## 1. Introdução e Motivação

Este trabalho apresenta a implementação de um sistema distribuído voltado ao monitoramento e controle ambiental de uma estufa agrícola. O sistema coleta leituras contínuas de temperatura e umidade do solo por meio de sensores e aciona atuadores (bomba de irrigação e exaustor) conforme limiares de histerese definidos.

### 1.1 Adequação do Tema à Disciplina

O cenário de controle ambiental permite exercitar modelos complementares estudados em Sistemas Distribuídos:

- **Comunicação indireta e assíncrona:** Sensores e atuadores interagem por publicação e subscrição de tópicos via broker MQTT, garantindo desacoplamento espacial e temporal.
- **Invocação remota síncrona:** O cliente e o Middleware utilizam chamadas de procedimento remoto (XML-RPC) para consultas de estado e comandos diretos.
- **Replicação ativa:** O estado e a lógica de decisão são replicados em 3 processos controladores independentes.
- **Mascaramento de falhas:** O Middleware aplica votação por maioria simples (quórum 2 de 3) para mascarar até $f = 1$ falha por parada (*crash*) ou falha arbitrária (*bizantina*).

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

```text
+----------------------------------------------------------------------+
|                        SISTEMA DISTRIBUÍDO                           |
|                                                                      |
|  +---------+     MQTT pub     +----------------------------------+   |
|  | Sensor  | ---------------> |      Broker MQTT (Mosquitto)     |   |
|  +---------+                  |              :1883               |   |
|                               +-----------------+----------------+   |
|                                                 | MQTT sub           |
|                               +-----------------v----------------+   |
|                               |    Controlador 1 (:8001)         |   |
|  +---------+   XML-RPC :9000  |    Controlador 2 (:8002)         |   |
|  | Cliente | ---+             |    Controlador 3 (:8003)         |   |
|  +---------+    |             +-----------------+----------------+   |
|                 v                               |                    |
|  +--------------------------+   XML-RPC         | MQTT pub           |
|  | Middleware Server (:9000)| <-----------------+                    |
|  | (Votação Majoritária)    |                   v                    |
|  +--------------------------+ +----------------------------------+   |
|                               |  Atuador (Bomba e Exaustor)      |   |
|                               |  Deduplicação via Cache LRU      |   |
|                               +----------------------------------+   |
+----------------------------------------------------------------------+
```

### 2.2 Componentes e Responsabilidades

| Componente | Arquivo | Porta | Responsabilidade |
|---|---|---|---|
| Sensor | `estufa/sensor.py` | — | Publica leituras de temperatura e umidade via MQTT |
| Broker MQTT | Mosquitto | 1883 | Roteamento assíncrono de mensagens por tópicos |
| Controlador (×3) | `estufa/controlador.py` | 8001–8003 | Avaliação de limiares, persistência JSON e servidor XML-RPC |
| Servidor de Middleware | `estufa/middleware_server.py` | 9000 | Ponto único de entrada XML-RPC para clientes e réplicas |
| Motor de Votação | `estufa/middleware.py` | interno | Invocação paralela das réplicas e apuração de quórum |
| Atuador | `estufa/atuador.py` | — | Execução dos comandos de acionamento com filtro LRU |
| Cliente | `estufa/cliente.py` | — | Interface de linha de comando para monitoramento e operação |

### 2.3 Protocolos de Comunicação

**MQTT (Message Queuing Telemetry Transport)**
- Modelo publicar/assinar com QoS 1 (entrega garantida ao menos uma vez).
- Tópicos separados para telemetria (`estufa/sensores/#`), comandos (`estufa/atuadores/#`) e status (`estufa/status/#`).

**XML-RPC (Remote Procedure Call sobre HTTP)**
- Modelo cliente-servidor síncrono.
- Cada controlador expõe os métodos `obter_estado`, `comandar_bomba`, `comandar_exaustor` e `ping`.
- O Middleware dispara chamadas concorrentes às réplicas usando `ThreadPoolExecutor` e consolida a resposta majoritária para o cliente.

---

## 3. Replicação e Consistência

### 3.1 Replicação Ativa

Todas as 3 réplicas de controlador subscrevem aos mesmos tópicos MQTT de sensores e executam de maneira determinística a mesma máquina de estados. Dessa forma, não há ponto único de falha na camada de controle e qualquer réplica saudável mantém o estado atualizado da estufa.

### 3.2 Transferência de Estado na Inicialização

Quando um controlador é iniciado ou reiniciado após uma falha, ele não assume imediatamente o conteúdo de seu arquivo JSON local (que pode estar defasado). Sua sequência de inicialização segue cinco passos:

```text
1. Inicia o servidor XML-RPC local em thread dedicada
2. Consulta o método obter_estado() no Servidor de Middleware (:9000)
3. Recebe o estado atual validado pelo quórum das réplicas ativas
4. Atualiza e persiste o estado local em disco
5. Conecta ao broker MQTT e passa a processar novas leituras
```

Esse protocolo implementa o padrão de *State Transfer*, assegurando que réplicas recuperadas converjam antes de emitir decisões de atuação.

---

## 4. Tolerância a Falhas por Parada (Crash)

### 4.1 Modelo de Falha

Uma falha por parada (*crash*) ocorre quando um controlador deixa de responder por encerramento do processo ou indisponibilidade de comunicação. Com $N = 3$ réplicas e `QUORUM_MINIMO = 2`, o sistema tolera a queda de até $f = 1$ controlador sem interrupção do serviço.

### 4.2 Algoritmo de Votação no Middleware

O método `Middleware._votar()` executa as seguintes etapas:

```text
1. Submete chamadas XML-RPC em paralelo para os 3 controladores
2. Coleta as respostas recebidas dentro do limite de timeout (3 segundos)
3. Normaliza cada resposta removendo metadados específicos de instância
   (ultima_atualizacao e controlador_id)
4. Agrupa e contabiliza as respostas equivalentes com collections.Counter
5. Se a resposta mais frequente tiver votos >= QUORUM_MINIMO (2), retorna-a
6. Caso contrário, lança a exceção ErroQuorum
```

**Cenário com 1 réplica inativa:**

```text
ctrl_1: {"bomba_ligada": true, "exaustor_ligado": false}  (OK)
ctrl_2: {"bomba_ligada": true, "exaustor_ligado": false}  (OK)
ctrl_3: ConnectionRefusedError / Timeout                  (ignorado)

Resultado: 2 votos concordantes >= QUORUM_MINIMO (2) -> Operação aprovada
```

### 4.3 Recuperação de Falha (Crash Recovery)

Quando o processo de uma réplica inativa (por exemplo, `ctrl_3`) é restabelecido:
1. Enquanto esteve inativo, as operações manuais ou autônomas continuaram sendo processadas por `ctrl_1` e `ctrl_2`.
2. Ao subir novamente, `ctrl_3` consulta o Middleware (`:9000`), obtém o estado aprovado pelo quórum (`ctrl_1` e `ctrl_2`), atualiza seu arquivo `data_ctrl_3.json` e retoma o consumo MQTT em consistência com os demais nós.

---

## 5. Tolerância a Falhas Bizantinas

### 5.1 Mascaramento por Votação Majoritária (TMR)

Uma falha bizantina ocorre quando um componente continua respondendo, porém fornece valores corrompidos, arbitrários ou contraditórios. No modelo de redundância tripla modular (*Triple Modular Redundancy* — TMR) com votador centralizado no Middleware, são necessárias $N \ge 2f + 1$ réplicas para mascarar $f$ respostas bizantinas. Com $N = 3$ e quórum mínimo de 2, o sistema mascara $f = 1$ réplica bizantina.

### 5.2 Normalização e Detecção de Divergência

O método `_normalizar()` em `Middleware._votar()` serializa o dicionário de resposta em JSON ordenado, descartando apenas os campos `ultima_atualizacao` e `controlador_id`. Todos os dados semânticos de estado (`temperatura`, `umidade_solo`, `bomba_ligada`, `exaustor_ligado`) e de resultado de comando (`sucesso`, `mensagem`) participam da votação:

```text
ctrl_1 retorna: {"bomba_ligada": false, "exaustor_ligado": false, "temperatura": 25.0}
ctrl_2 retorna: {"bomba_ligada": true,  "exaustor_ligado": true,  "temperatura": 999.0} (Bizantino)
ctrl_3 retorna: {"bomba_ligada": false, "exaustor_ligado": false, "temperatura": 25.0}

Contagem: {estado_honesto: 2, estado_adulterado: 1}
Resultado: estado_honesto (2 votos >= QUORUM_MINIMO)
```

### 5.3 Simulação de Comportamento Bizantino

Um controlador pode ser iniciado com a flag `--byzantino`:

```bash
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
```

Nesse modo, a réplica simula falhas arbitrárias tanto em consultas quanto em comandos:
- Em `obter_estado()`, reporta valores espúrios (`temperatura = 999.0`, `umidade_solo = -1.0`) e inverte os estados booleanos da bomba e do exaustor.
- Em `comandar_bomba()` e `comandar_exaustor()`, omite a execução real do comando e retorna confirmação referente à ação oposta, sendo vencida na votação pelas duas réplicas honestas.

---

## 6. Deduplicação de Comandos MQTT (Cache LRU)

### 6.1 Problema da Replicação Ativa na Atuação

Como os 3 controladores processam simultaneamente cada leitura publicada pelos sensores (ou cada comando originado pelo Middleware), os 3 publicam o comando resultante no tópico MQTT do atuador. Sem filtragem, o atuador processaria a mesma ordem três vezes consecutivas.

### 6.2 Identificadores de Comando e Filtro LRU

1. **Decisões autônomas (acionadas por leitura de sensor):**
   Cada controlador calcula um identificador determinístico a partir da ação e do `timestamp` original contido no payload do sensor:
   ```python
   raw = f"{acao_alvo}_{sensor_ts}"
   cmd_id = hashlib.md5(raw.encode("utf-8")).hexdigest()
   ```
   Como as 3 réplicas recebem a mesma mensagem MQTT do sensor, todas produzem o mesmo hash MD5.

2. **Comandos manuais (acionados pelo cliente):**
   O Middleware gera um único `UUID4` por chamada e o envia como argumento para as 3 réplicas, que o repassam no payload MQTT.

3. **Descarte no Atuador:**
   O atuador armazena os últimos `DEDUP_CACHE_SIZE` (50) identificadores em um `OrderedDict` com política LRU (*Least Recently Used*). A primeira mensagem com um novo `comando_id` é executada e registrada; as duas mensagens subsequentes das demais réplicas encontram o ID no cache e são descartadas.

---

## 7. Parâmetros de Configuração

Os parâmetros globais estão definidos em `estufa/config.py`:

| Parâmetro | Valor Padrão | Descrição |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `localhost:1883` | Endereço do broker MQTT |
| `MIDDLEWARE_PORT` | `9000` | Porta XML-RPC do Servidor de Middleware |
| `TEMP_MAX_CELSIUS` | `35.0 °C` | Limiar superior de temperatura (liga o exaustor) |
| `TEMP_MIN_CELSIUS` | `15.0 °C` | Limiar inferior de temperatura (desliga o exaustor) |
| `UMIDADE_MIN_PERCENT` | `30.0 %` | Limiar inferior de umidade (liga a bomba) |
| `UMIDADE_MAX_PERCENT` | `70.0 %` | Limiar superior de umidade (desliga a bomba) |
| `TIMEOUT_RPC_SEGUNDOS` | `3` | Timeout por chamada XML-RPC às réplicas |
| `QUORUM_MINIMO` | `2` | Quantidade mínima de respostas concordantes |
| `DEDUP_CACHE_SIZE` | `50` | Capacidade máxima do cache LRU no atuador |

---

## 8. Testes Automatizados

A verificação automatizada é dividida em três módulos de teste executados via `pytest`:

| Arquivo | Escopo Testado |
|---|---|
| `tests/test_atuador.py` | Aceitação de novos IDs, descarte de duplicatas e política de evicção LRU |
| `tests/test_controlador.py` | Persistência JSON, geração determinística de hash MD5, regras de histerese e modo bizantino |
| `tests/test_middleware.py` | Quórum 3/3 e 2/3, falha de quórum, mascaramento de réplica bizantina em leituras e comandos, e verificação de saúde |

Para executar toda a suíte:

```bash
pytest tests/ -v
```

---

## 9. Conclusão

A arquitetura desenvolvida integra comunicação indireta por mensageria (MQTT) e invocação remota (XML-RPC) para atender aos requisitos de desacoplamento, disponibilidade e consistência em um sistema de controle distribuído. A combinação de replicação ativa com votação majoritária no Middleware, transferência de estado no boot e deduplicação LRU no atuador garante que o sistema tolere tanto falhas por parada quanto respostas bizantinas de uma réplica sem comprometer a integridade das decisões nem causar atuações duplicadas.
