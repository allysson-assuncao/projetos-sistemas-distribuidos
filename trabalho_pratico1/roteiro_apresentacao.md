# Roteiro de Apresentação e Demonstração — TP1 Sistemas Distribuídos

## 1. Mapeamento de Conceitos no Código

| Conceito | Arquivo | Método / Símbolo | Linhas | Mecanismo Implementado |
|---|---|---|---|---|
| **Pub/Sub Assíncrono (MQTT)** | [`estufa/sensor.py`](estufa/sensor.py) | `publicar_leitura` | 39–48 | Publicação JSON com `QoS = 1` e `timestamp` de origem nos tópicos de telemetria |
| **Subscrição e Atuação MQTT** | [`estufa/atuador.py`](estufa/atuador.py) | `_on_connect` / `_on_message` | 44–54, 88–105 | Subscrição nos tópicos de comando (`bomba` e `exaustor`) e publicação de confirmação |
| **RPC Síncrono (XML-RPC)** | [`estufa/middleware_server.py`](estufa/middleware_server.py) | `MiddlewareService` / `iniciar_servidor` | 18–73 | Servidor XML-RPC na porta `9000` expondo `obter_estado`, `comandar_bomba`, `comandar_exaustor` e `verificar_saude` |
| **Transparência de Acesso e Replicação** | [`estufa/cliente.py`](estufa/cliente.py) | `_criar_proxy` | 19–21 | Cliente conectado unicamente ao Middleware (`:9000`), sem visibilidade das réplicas (`:8001`–`:8003`) |
| **Replicação Ativa** | [`estufa/controlador.py`](estufa/controlador.py) | `Controlador` | 40–55, 164–185 | 3 processos independentes consumindo os mesmos tópicos MQTT e mantendo máquina de estados idêntica |
| **Concorrência Local (`Lock`)** | [`estufa/controlador.py`](estufa/controlador.py) | `self._lock` | 50, 87, 173, 188, 219, 249 | Exclusão mútua entre a thread de consumo MQTT (`loop_forever`) e a thread do servidor XML-RPC (`server_thread`) |
| **Transferência de Estado (*State Transfer*)** | [`estufa/controlador.py`](estufa/controlador.py) | `_sincronizar_estado_via_middleware` | 74–105, 265–305 | Consulta de quórum ao Middleware no boot antes de iniciar o consumo MQTT |
| **Votação Majoritária TMR ($N = 2f + 1 = 3$)** | [`estufa/middleware.py`](estufa/middleware.py) | `Middleware._votar` | 41–91 | Invocação paralela (`ThreadPoolExecutor`) e exigência de `QUORUM_MINIMO = 2` votos concordantes |
| **Normalização de Respostas** | [`estufa/middleware.py`](estufa/middleware.py) | `_normalizar` | 69–76 | Serialização JSON ordenada descartando metadados de instância (`ultima_atualizacao` e `controlador_id`) |
| **Simulação de Falha Bizantina** | [`estufa/controlador.py`](estufa/controlador.py) | `obter_estado` / `comandar_bomba` / `comandar_exaustor` | 189–198, 211–217, 241–247 | Adulteração de leituras (`999.0 °C`, `-1.0 %`), inversão de estados booleanos e omissão de comando manual |
| **ID Determinístico (Autônomo)** | [`estufa/controlador.py`](estufa/controlador.py) | `gerar_comando_id` | 117–119 | Cálculo de `MD5(f"{acao_alvo}_{sensor_ts}")` idêntico nas 3 réplicas para o mesmo evento do sensor |
| **ID Compartilhado (Manual)** | [`estufa/middleware.py`](estufa/middleware.py) | `comandar_bomba` / `comandar_exaustor` | 97–107 | Geração de um único `uuid.uuid4()` por requisição no Middleware, repassado às 3 réplicas |
| **Deduplicação LRU** | [`estufa/atuador.py`](estufa/atuador.py) | `_is_duplicado` | 22–41 | Cache `collections.OrderedDict` (`DEDUP_CACHE_SIZE = 50`) para descarte de publicações redundantes |

---

## 2. Guia de Percorrimento do Código

### 2.1 [`estufa/config.py`](estufa/config.py)
- Define endereço do broker MQTT (`localhost:1883`) e os 6 tópicos do sistema (linhas 9–19).
- Declara a topologia das 3 réplicas de controlador (`ctrl_1:8001`, `ctrl_2:8002`, `ctrl_3:8003`) e do Middleware (`localhost:9000`) (linhas 22–30).
- Define os limiares com histerese: temperatura (`> 35.0 °C` liga exaustor, `< 15.0 °C` desliga) e umidade (`< 30.0 %` liga bomba, `> 70.0 %` desliga) (linhas 33–36).
- Define `TIMEOUT_RPC_SEGUNDOS = 3`, `QUORUM_MINIMO = 2` e `DEDUP_CACHE_SIZE = 50` (linhas 39–43).

### 2.2 [`estufa/sensor.py`](estufa/sensor.py)
- `PERFIS` (linhas 24–29): faixas de valores para simulação (`normal`, `seco`, `quente`, `frio`).
- `publicar_leitura` (linhas 39–48): publica JSON com `valor`, `unidade` e `timestamp` (`time.time()`) usando `qos=1`.
- `executar_sensor` (linhas 51–81): inicia thread de rede do MQTT (`loop_start()`) e publica leituras em intervalo configurável (padrão `2.0s`).

### 2.3 [`estufa/controlador.py`](estufa/controlador.py)
- `_carregar_estado` e `_salvar_estado` (linhas 56–72): persistência local do dicionário `self._estado` em `data_ctrl_X.json`.
- `iniciar` (linhas 265–305): sequência de inicialização em 3 etapas:
  1. Inicia `SimpleXMLRPCServer` em thread daemon (`server_thread`).
  2. Executa `_sincronizar_estado_via_middleware` (linhas 74–105), consultando `proxy.obter_estado()` no Middleware (`:9000`) com até 10 tentativas antes de consumir o broker.
  3. Conecta ao broker MQTT, subscreve aos tópicos de sensores e bloqueia em `loop_forever()`.
- `_on_message` e `_decidir_atuacao` (linhas 107–144, 164–185):
  - Atualiza `self._estado` sob `self._lock`, preservando `sensor_timestamp` da mensagem original.
  - Avalia limiares de histerese; em caso de transição de estado, gera `comando_id = MD5(acao_alvo + sensor_timestamp)` e publica comando MQTT para o atuador.
- Métodos remotos XML-RPC (linhas 186–263):
  - `obter_estado`: retorna `self._estado` (ou dados adulterados se `self.byzantino=True`).
  - `comandar_bomba` / `comandar_exaustor`: altera estado, publica no MQTT com o `comando_id` recebido do Middleware e retorna `{"sucesso": True, "mensagem": "...", "controlador_id": self.ctrl_id}` (em modo bizantino, não atua e retorna a mensagem referente à ação inversa).
  - `ping`: retorna `"pong:<ctrl_id>"`.

### 2.4 [`estufa/middleware_server.py`](estufa/middleware_server.py) e [`estufa/middleware.py`](estufa/middleware.py)
- `MiddlewareService` (`middleware_server.py`, linhas 18–52): expõe os métodos XML-RPC na porta `9000` e converte `ErroQuorum` em exceção XML-RPC (`Fault`) para o cliente.
- `Middleware._votar` (`middleware.py`, linhas 41–91):
  - Dispara chamadas concorrentes às 3 réplicas via `ThreadPoolExecutor` com timeout de 3 segundos.
  - Normaliza os dicionários recebidos em `_normalizar` (linhas 69–76), removendo `ultima_atualizacao` e `controlador_id`.
  - Contabiliza votos com `collections.Counter`. Se a resposta mais frequente tiver `votos >= 2` (`QUORUM_MINIMO`), retorna o resultado; caso contrário, lança `ErroQuorum`.
- `comandar_bomba` e `comandar_exaustor` (`middleware.py`, linhas 97–107): gera um `uuid.uuid4()` único por operação manual e o envia para todas as réplicas.

### 2.5 [`estufa/atuador.py`](estufa/atuador.py)
- `_is_duplicado` (linhas 25–41): implementa cache LRU usando `collections.OrderedDict`.
  - Se `comando_id` já consta no dicionário: move para o final (`move_to_end`) e retorna `True` (descarta duplicata).
  - Se é inédito: insere no final e, se exceder `DEDUP_CACHE_SIZE` (50), remove a entrada mais antiga (`popitem(last=False)`).
- `_processar_bomba` e `_processar_exaustor` (linhas 56–76): altera o estado simulado do atuador e publica confirmação em `estufa/status/#`.

### 2.6 [`estufa/cliente.py`](estufa/cliente.py)
- Conecta-se apenas a `http://localhost:9000` via `xmlrpc.client.ServerProxy` (linhas 19–21).
- `menu_interativo` (linhas 42–100): consulta de estado, acionamento manual de bomba/exaustor, verificação de saúde das réplicas e tratamento de `xmlrpc.client.Fault` e `ConnectionRefusedError`.
- `modo_automatico` (linhas 103–117): consulta periódica com `--auto`.

### 2.7 Testes Automatizados (`tests/`) e Relatório (`relatorio/relatorio.md`)
- [`tests/test_atuador.py`](tests/test_atuador.py) (7 testes): inserção de IDs inéditos, descarte das 2 publicações redundantes das réplicas e evicção LRU ao ultrapassar 50 entradas.
- [`tests/test_controlador.py`](tests/test_controlador.py) (29 testes): persistência JSON com fixture `tmp_path`, igualdade do hash MD5 entre as 3 réplicas, histerese de temperatura/umidade e respostas do modo bizantino.
- [`tests/test_middleware.py`](tests/test_middleware.py) (15 testes): simulação das réplicas via `unittest.mock.patch`, validando quórum 3/3, quórum 2/3 (1 *crash*), perda de quórum (`ErroQuorum`), mascaramento de 1 réplica bizantina em leituras e comandos, e compartilhamento de UUID.
- [`relatorio/relatorio.md`](relatorio/relatorio.md): documentação da arquitetura, protocolos MQTT/XML-RPC, replicação ativa com *State Transfer*, modelo de falhas de *crash* e bizantinas (TMR $2f+1$) e deduplicação LRU.

---

## 3. Síntese dos Fluxos de Execução

### Fluxo 1 — Acionamento Autônomo (Telemetria)
```text
[Sensor] --MQTT (valor, sensor_ts)--> [Broker :1883]
                                            |
                  +-------------------------+-------------------------+
                  v                         v                         v
            [ctrl_1 :8001]            [ctrl_2 :8002]            [ctrl_3 :8003]
         Avalia limiar (histerese)  Avalia limiar (histerese)  Avalia limiar (histerese)
         cmd_id = MD5(acao+ts)      cmd_id = MD5(acao+ts)      cmd_id = MD5(acao+ts)
                  |                         |                         |
                  +-------------------------+-------------------------+
                                            | (3 publicações MQTT com mesmo cmd_id)
                                            v
                                    [Atuador (Cache LRU)]
                               1ª mensagem: executa e registra no LRU
                               2ª e 3ª mensagens: descarta (duplicadas)
```

### Fluxo 2 — Acionamento Manual e Consulta (Via Middleware)
```text
[Cliente CLI] --XML-RPC (:9000)--> [Middleware Server]
                                   Gera cmd_id = UUID4 único (se comando)
                                   Dispara chamadas paralelas (ThreadPoolExecutor)
                                            |
                  +-------------------------+-------------------------+
                  v                         v                         v
            [ctrl_1 :8001]            [ctrl_2 :8002]            [ctrl_3 :8003]
         Publica MQTT (cmd_id)     Publica MQTT (cmd_id)     Publica MQTT (cmd_id)
         Retorna dict XML-RPC      Retorna dict XML-RPC      Retorna dict XML-RPC
                  |                         |                         |
                  +-------------------------+-------------------------+
                                            |
                                   [Middleware._votar]
                           _normalizar() remove controlador_id e ultima_atualizacao
                           Apura maioria >= 2/3 (QUORUM_MINIMO = 2)
                                            |
                                            v
                                      [Cliente CLI]
```

---

## 4. Roteiro Passo a Passo de Demonstração Prática

### Etapa 1 — Execução dos Testes Unitários (Sem processos externos)
```bash
pytest tests/ -v
```

### Etapa 2 — Inicialização do Sistema (Ordem de Dependência)
- **Via script:**
  ```bash
  bash scripts/start_all.sh
  python3 -m estufa.cliente
  ```
- **Ou manualmente por terminal (com `.venv` ativa):**
  ```bash
  # Terminal 1 — Broker MQTT
  docker compose up -d

  # Terminal 2 — Servidor de Middleware (:9000)
  python3 -m estufa.middleware_server

  # Terminais 3, 4 e 5 — Réplicas de Controlador (:8001, :8002, :8003)
  python3 -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
  python3 -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
  python3 -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json

  # Terminal 6 — Atuador (Cache LRU)
  python3 -m estufa.atuador

  # Terminal 7 — Sensor
  python3 -m estufa.sensor --modo normal

  # Terminal 8 — Cliente Interativo
  python3 -m estufa.cliente
  ```

### Etapa 3 — Demonstração de Acionamento Autônomo e Deduplicação LRU
No terminal do sensor (Terminal 7), interromper (`Ctrl+C`) e iniciar no perfil `seco` (umidade < 30%) ou `quente` (temperatura > 35°C):
```bash
python3 -m estufa.sensor --modo seco
```
- **Logs dos Controladores:** As 3 réplicas detectam `Umidade < 30.0% -> LIGAR bomba` no mesmo evento.
- **Log do Atuador:** Executa a transição `Bomba de irrigação -> LIGADA` na primeira mensagem e registra `Comando duplicado descartado` nas duas seguintes.

### Etapa 4 — Demonstração de Tolerância a Falha por Parada (*Crash*) — Quórum 2/3
1. Interromper o processo do `ctrl_3` (`Ctrl+C` no Terminal 5).
2. No Cliente (Terminal 8), selecionar a opção `6` (*Verificar saúde dos controladores*):
   - Exibe `ctrl_1: ok`, `ctrl_2: ok`, `ctrl_3: OFFLINE`.
3. No Cliente, selecionar a opção `3` (*Desligar bomba*) ou `4` (*Ligar exaustor*):
   - **Log do Middleware:** Reporta `Controlador ctrl_3 indisponível`, contabiliza 2 votos concordantes (`ctrl_1` e `ctrl_2`) e aprova a operação.

### Etapa 5 — Demonstração de Recuperação de Falha (*Crash Recovery* / *State Transfer*)
Reiniciar o `ctrl_3` no Terminal 5:
```bash
python3 -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
```
- **Log do `ctrl_3`:** Exibe `Sincronizando estado inicial via Middleware` seguido de `Estado sincronizado na tentativa 1/10`, convergindo imediatamente com as alterações feitas enquanto esteve inativo.

### Etapa 6 — Demonstração de Tolerância a Falha Bizantina (Votação 2 x 1)
1. Interromper o `ctrl_2` (Terminal 4) e reiniciá-lo com a flag `--byzantino`:
   ```bash
   python3 -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
   ```
2. No Cliente, selecionar a opção `1` (*Consultar estado atual*) e a opção `2` (*Ligar bomba*):
   - **Log do Middleware:** Exibe a contagem de votos `2` (estado honesto de `ctrl_1` e `ctrl_3`) contra `1` (resposta adulterada do `ctrl_2`), retornando o estado íntegro ao cliente.

### Etapa 7 — Demonstração de Perda de Quórum ($f = 2$ Falhas)
1. Com `ctrl_2` em modo bizantino (ou parado), interromper também o `ctrl_3` (`Ctrl+C` no Terminal 5), restando apenas 1 réplica honesta.
2. No Cliente, selecionar a opção `1` (*Consultar estado atual*):
   - **Log do Middleware / Cliente:** Lança `ErroQuorum` (`Quórum não atingido: 1 voto(s) para a resposta mais comum (mínimo: 2)`), impedindo retorno de estado não confiável.
