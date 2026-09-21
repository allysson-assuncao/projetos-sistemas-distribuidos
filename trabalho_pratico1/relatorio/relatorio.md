# Relatório Técnico — Trabalho Prático 1: Sistemas Distribuídos
## Estufa Agrícola Automatizada: Sistema Distribuído com MQTT e XML-RPC

**Disciplina:** Sistemas Distribuídos  
**Tema Escolhido:** Controle Automatizado de Estufa Agrícola  
**Tecnologias:** Python 3.10+, MQTT (Eclipse Mosquitto), XML-RPC  
**Padrões Arquiteturais:** Replicação Ativa, Votação por Maioria (BFT), Deduplicação LRU  

---

## 1. Introdução e Motivação

O presente trabalho implementa um sistema distribuído para o controle automatizado de uma estufa agrícola. O sistema monitora variáveis ambientais críticas (temperatura e umidade do solo) por meio de sensores e aciona atuadores físicos (bomba de irrigação e exaustor de temperatura) com base em limiares pré-configurados.

### 1.1 Justificativa da Escolha do Tema

A estufa agrícola foi escolhida pela sua adequação natural a conceitos de sistemas distribuídos. Em uma estufa real, a falha no controle de temperatura ou umidade pode destruir toda uma plantação em poucas horas. Isso torna os requisitos de **disponibilidade**, **tolerância a falhas** e **consistência** não apenas acadêmicos, mas criticos para a operação. O tema permitiu explorar:

- **Mensageria assíncrona:** Sensores publicam dados sem conhecimento dos consumidores (desacoplamento pub/sub via MQTT).
- **Invocação remota síncrona:** O cliente controla atuadores via chamadas de método remoto (XML-RPC).
- **Replicação:** O estado do sistema é mantido por 3 réplicas de controladores para garantir disponibilidade.
- **Tolerância a falhas de crash e falhas arbitrárias (Byzantinas).**

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SISTEMA DISTRIBUÍDO                           │
│                                                                      │
│  ┌─────────┐    MQTT pub      ┌─────────────────────────────────┐   │
│  │ Sensor  │ ─────────────▶  │      Broker MQTT (Mosquitto)    │   │
│  └─────────┘                 │           :1883                  │   │
│                               └──────────────┬──────────────────┘   │
│                                              │ MQTT sub             │
│                               ┌─────────────▼──────────────────┐   │
│                               │    Controlador 1 (:8001)        │   │
│  ┌─────────┐  XML-RPC :9000  │    Controlador 2 (:8002)        │   │
│  │ Cliente │ ──────────────▶ │    Controlador 3 (:8003)        │   │
│  └─────────┘                 │  (cada um expõe XML-RPC Server) │   │
│                               └───────────────┬─────────────────┘   │
│  ┌──────────────────────────┐                │ MQTT pub             │
│  │  Middleware Server :9000 │ ◀──XML-RPC────┘                      │
│  │  (Voting Engine BFT)     │                                       │
│  └──────────────────────────┘                ▼                      │
│                               ┌─────────────────────────────────┐   │
│                               │  Atuador (Bomba + Exaustor)     │   │
│                               │  Deduplicação LRU ativa         │   │
│                               └─────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Componentes e Responsabilidades

| Componente | Arquivo | Porta | Responsabilidade |
|---|---|---|---|
| Sensor | `estufa/sensor.py` | — | Publica temperatura e umidade via MQTT |
| Broker MQTT | Docker (Mosquitto) | 1883 | Central de mensagens assíncronas |
| Controlador (×3) | `estufa/controlador.py` | 8001–8003 | Lógica de decisão + Servidor XML-RPC |
| Middleware Server | `estufa/middleware_server.py` | 9000 | Servidor standalone; votação BFT |
| Middleware Engine | `estufa/middleware.py` | interno | Algoritmo de votação por maioria |
| Atuador | `estufa/atuador.py` | — | Executa comandos; cache LRU |
| Cliente | `estufa/cliente.py` | — | Interface CLI; conecta ao Middleware |

### 2.3 Protocolos de Comunicação

O sistema utiliza **dois protocolos complementares**:

**MQTT (Message Queuing Telemetry Transport)**
- Padrão pub/sub assíncrono e leve.
- Sensores publicam leituras; controladores e atuadores subscrevem.
- Desacoplamento temporal: publicador e subscritor não precisam estar ativos simultaneamente.
- QoS 1 garantido: ao menos uma entrega de cada mensagem.

**XML-RPC (Remote Procedure Call sobre HTTP)**
- Protocolo síncrono de invocação remota.
- Controladores expõem métodos (`obter_estado`, `comandar_bomba`, `comandar_exaustor`, `ping`) como servidores XML-RPC.
- Middleware chama esses métodos em paralelo para implementar votação.
- Cliente conecta exclusivamente ao Middleware Server (porta 9000).

---

## 3. Lógica de Replicação

### 3.1 Replicação Ativa (Active Replication)

O sistema utiliza **replicação ativa**: todas as 3 réplicas de controladores recebem os mesmos dados de sensores via MQTT e executam a mesma lógica de decisão de forma independente. Esta abordagem garante:

- **Alta disponibilidade:** O sistema continua funcionando mesmo que 1 controlador falhe.
- **Detecção de falhas Byzantinas:** Respostas divergentes são identificadas pelo algoritmo de votação.
- **Sem ponto único de falha** no nível de tomada de decisão.

### 3.2 Sequência de Boot com Transferência de Estado

Quando um controlador reinicia após uma falha (crash recovery), ele **não parte do estado local (potencialmente desatualizado)**. Em vez disso, executa uma **sincronização de estado via Middleware**:

```
[Broker UP] → [Middleware Server UP :9000] → [Controlador Inicia]
                                                    │
                                          ① Sobe servidor XML-RPC
                                          ② Consulta Middleware.obter_estado()
                                          ③ Recebe estado aprovado por quórum
                                          ④ Sobrescreve arquivo JSON local
                                          ⑤ Inicia consumo MQTT
```

Esta sequência implementa o padrão **State Transfer** de sistemas distribuídos, garantindo que uma réplica recuperada converja imediatamente para o estado atual do cluster.

---

## 4. Tolerância a Falhas de Crash (Quórum 2/3)

### 4.1 Modelo de Falhas de Crash

Uma falha de crash ocorre quando um processo para de responder (seja por exceção, kill de processo, ou falha de rede). O sistema tolera até **f = 1 falha de crash** com **n = 3 controladores**.

### 4.2 Algoritmo de Votação

O algoritmo no `Middleware._votar()` funciona da seguinte forma:

```
1. Envia chamadas XML-RPC para TODOS os 3 controladores em paralelo
   (via ThreadPoolExecutor com timeout configurável)
2. Coleta respostas dentro do timeout
3. Normaliza respostas (remove campos voláteis como 'ultima_atualizacao')
4. Conta votos: agrupa respostas idênticas
5. Verifica se o grupo mais comum ≥ QUORUM_MINIMO (2)
6. Se sim: retorna o resultado do grupo majoritário
7. Se não: levanta ErroQuorum
```

**Exemplo com 1 controlador crashado:**

```
ctrl_1: {"bomba_ligada": true, "exaustor_ligado": false}  ✓
ctrl_2: {"bomba_ligada": true, "exaustor_ligado": false}  ✓
ctrl_3: (ConnectionRefusedError — timeout)                 ✗ ignorado

Votos: {"bomba_ligada: true...": 2} ≥ QUORUM_MINIMO(2) → APROVADO
```

### 4.3 Demonstração de Crash Recovery

Para demonstrar a tolerância a falhas de crash durante a apresentação:

1. Iniciar os 3 controladores normalmente.
2. Matar o processo do `ctrl_3` com `kill` ou `Ctrl+C` na janela correspondente.
3. Executar um comando via cliente: `python -m estufa.cliente` → ligar bomba.
4. Observar nos logs do Middleware: `ctrl_3 falhou` mas quórum atingido com ctrl_1 e ctrl_2.
5. Reiniciar o `ctrl_3`: ele executará sincronização de estado via Middleware.

---

## 5. Tolerância a Falhas Byzantinas

### 5.1 Modelo de Falhas Byzantinas

Uma falha Byzantina ocorre quando um processo **responde com dados incorretos ou maliciosos** (sem crashar). Este é o modelo de falha mais severo em sistemas distribuídos. O sistema detecta e neutraliza falhas Byzantinas mediante **votação por maioria**.

**Capacidade:** Com n=3 e QUORUM_MINIMO=2, o sistema tolera **f=1 réplica Byzantina**.

> **Nota técnica:** Para tolerar f réplicas Byzantinas com votação por maioria simples, são necessárias n ≥ 2f+1 réplicas. Com f=1, n=3 é o mínimo suficiente.

### 5.2 Mecanismo de Detecção

O método `_normalizar()` em `Middleware._votar()` serializa as respostas em JSON ordenado, excluindo campos voláteis (`ultima_atualizacao`, `controlador_id`, `_byzantino`). Isto permite comparar respostas semanticamente equivalentes:

```python
# Exemplo: ctrl_2 em modo Byzantino
ctrl_1 retorna: {"bomba_ligada": false, "exaustor_ligado": false, "temperatura": 25.0}
ctrl_2 retorna: {"bomba_ligada": true,  "exaustor_ligado": true,  "temperatura": 999.0}  ← Byzantino
ctrl_3 retorna: {"bomba_ligada": false, "exaustor_ligado": false, "temperatura": 25.0}

Votos: {estado_honesto: 2, estado_byzantino: 1}
→ Maioria: estado_honesto com 2 votos ≥ QUORUM_MINIMO(2)
→ RESULTADO: estado honesto retornado ao cliente
```

### 5.3 Modo Byzantino para Demonstração

O controlador pode ser iniciado em modo Byzantino:

```bash
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
```

Em modo Byzantino, o controlador:
- Retorna `temperatura=999.0`, `umidade=-1.0` em `obter_estado()`
- Inverte o estado dos atuadores (`bomba_ligada=True` quando deve ser `False`)
- Confirma comandos sem executá-los (falso positivo)

O Middleware neutraliza este comportamento e retorna o estado honesto aprovado pelos outros 2 controladores.

---

## 6. Deduplicação de Comandos MQTT (LRU Cache)

### 6.1 Problema

Com 3 controladores em replicação ativa, todos processam o mesmo evento MQTT do sensor e podem publicar o mesmo comando ao Atuador simultaneamente. Sem deduplicação, o atuador executaria a mesma ação 3 vezes.

### 6.2 Solução: `comando_id` Determinístico + Cache LRU

**Para decisões autônomas (trigger por sensor MQTT):**

Cada controlador gera um `comando_id` determinístico usando MD5:

```python
# Em controlador._decidir_atuacao():
raw = f"{acao_alvo}_{sensor_timestamp}"
cmd_id = hashlib.md5(raw.encode("utf-8")).hexdigest()
```

O `sensor_timestamp` é extraído do payload JSON original do sensor. Como todos os 3 controladores recebem a mesma mensagem MQTT com o mesmo timestamp, produzem **exatamente o mesmo hash**.

**Para comandos manuais (trigger por cliente):**

O Middleware gera um UUID4 aleatório **único por invocação** e envia o mesmo ID para todos os 3 controladores:

```python
# Em middleware.comandar_bomba():
comando_id = str(uuid.uuid4())  # Gerado uma vez
return self._votar("comandar_bomba", acao, comando_id)  # Enviado aos 3
```

**No Atuador — Cache LRU:**

O atuador mantém um `OrderedDict` com os últimos `DEDUP_CACHE_SIZE=50` IDs processados:

```
MQTT mensagem 1 (ctrl_1): {acao: "ligar", comando_id: "abc123"}  → NOVO → processa
MQTT mensagem 2 (ctrl_2): {acao: "ligar", comando_id: "abc123"}  → DUPLICADO → descarta
MQTT mensagem 3 (ctrl_3): {acao: "ligar", comando_id: "abc123"}  → DUPLICADO → descarta
```

Resultado: O atuador executa cada ação física exatamente uma vez.

---

## 7. Configuração do Sistema

Todos os parâmetros configuráveis estão centralizados em `estufa/config.py`:

| Parâmetro | Valor Padrão | Descrição |
|---|---|---|
| `MQTT_HOST` | `localhost` | Host do broker MQTT |
| `MQTT_PORT` | `1883` | Porta do broker MQTT |
| `MIDDLEWARE_PORT` | `9000` | Porta do Middleware Server |
| `TEMP_MAX_CELSIUS` | `35.0°C` | Temperatura máxima → aciona exaustor |
| `TEMP_MIN_CELSIUS` | `15.0°C` | Temperatura mínima → desliga exaustor |
| `UMIDADE_MIN_PERCENT` | `30.0%` | Umidade mínima → aciona bomba |
| `UMIDADE_MAX_PERCENT` | `70.0%` | Umidade máxima → desliga bomba |
| `TIMEOUT_RPC_SEGUNDOS` | `3` | Timeout por chamada XML-RPC |
| `QUORUM_MINIMO` | `2` | Votos mínimos para aprovação |
| `DEDUP_CACHE_SIZE` | `50` | Tamanho do cache LRU de deduplicação |

---

## 8. Testes Automatizados

O projeto conta com uma suíte de testes unitários cobrindo os componentes críticos:

### 8.1 Suíte de Testes

| Arquivo | Componente Testado | Cobertura Principal |
|---|---|---|
| `tests/test_atuador.py` | `Atuador` (LRU cache) | Deduplicação, evicção LRU, IDs duplicados |
| `tests/test_controlador.py` | `Controlador` | Lógica de decisão, IDs determinísticos, modo Byzantino |
| `tests/test_middleware.py` | `Middleware` | Votação BFT, quórum, falhas Byzantinas (via mocks) |

### 8.2 Execução

```bash
# Da raiz do projeto (trabalho_pratico1/)
pytest tests/ -v

# Com cobertura detalhada
pytest tests/ -v --tb=short
```

**Nota:** Os testes de controlador e middleware **não requerem** broker MQTT ou processos de controlador em execução — utilizam injeção de estado direta e mocks XML-RPC respectivamente.

---

## 9. Conclusão

O sistema implementado demonstra na prática os seguintes conceitos fundamentais de Sistemas Distribuídos:

1. **Transparência de Localização:** O cliente interage com o Middleware como se fosse um único servidor, sem conhecimento dos controladores internos.

2. **Tolerância a Falhas de Crash (Crash Fault Tolerance):** O sistema mantém disponibilidade com 1 controlador offline através de quórum 2/3.

3. **Tolerância a Falhas Byzantinas (Byzantine Fault Tolerance):** A votação por maioria neutraliza 1 réplica com comportamento arbitrário, retornando sempre o resultado honesto ao cliente.

4. **Consistência por Transferência de Estado:** Réplicas recuperadas sincronizam automaticamente com o estado do cluster antes de retomar a operação.

5. **Deduplicação de Mensagens:** O cache LRU com IDs determinísticos garante semântica de entrega "exatamente uma vez" (effectively-once) ao nível do atuador.

6. **Desacoplamento via Mensageria:** MQTT permite que sensores e atuadores operem de forma completamente desacoplada dos controladores, aumentando a resiliência geral do sistema.
