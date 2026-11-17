# Guia de Estudo e Mapa de Código — TP1 (Estufa Distribuída)

Material de consulta rápida para localizar no código cada mecanismo distribuído e explicar seu funcionamento durante a apresentação.

---

## 1. Onde Mostrar Cada Mecanismo no Código (Consulta Rápida)

| O que o professor pedir para mostrar | Arquivo | Símbolo / Função | Linhas |
|---|---|---|---|
| **Eleição de líder (Algoritmo Bully)** e guarda de rank | `estufa/controlador.py` | `ping`, `iniciar_eleicao`, `anunciar_lider`, `realizar_eleicao` | `L208–L341` |
| **Heartbeat** e detecção de queda do líder | `estufa/controlador.py` | `Controlador._loop_heartbeat` | `L352–L387` |
| **Consenso e quórum dinâmico (`3→2/3`, `2/2`, `1/1`, `ErroQuorum`)** | `estufa/middleware.py` | `_normalizar_estado`, `calcular_consenso` | `L110–L170` |
| **Votação P2P** e **commit replicado** nos JSONs | `estufa/controlador.py` | `coletar_voto_estado`, `commit_estado`, `_coordenar_consenso_e_persistir` | `L489–L670` |
| **Persistência JSON atômica** (`tmp` + `os.replace`) | `estufa/controlador.py` | `_carregar_estado`, `_salvar_estado` | `L161–L202` |
| **Falha bizantina (`--byzantino`)** | `estufa/controlador.py` | `coletar_voto_estado` | `L495–L502` |
| **Ressincronização ao religar um controlador** | `estufa/controlador.py` | `Controlador._sincronizar_com_cluster` | `L394–L482` |
| **Failover do cliente e descoberta do líder** | `estufa/middleware.py` | `_ordenar_candidatos`, `_chamar_com_failover`, `obter_estado` | `L172–L260` |
| **Encaminhamento seguidor → líder** em comandos manuais | `estufa/controlador.py` | `Controlador._executar_comando_atuador` | `L747–L818` |
| **Publicação MQTT exclusiva do líder** | `estufa/controlador.py` | `_publicar_comando`, `_on_connect`, `_on_message` | `L567–L575`, `L677–L727` |
| **Regras de temperatura e umidade** (histerese) | `estufa/config.py` / `controlador.py` | `TEMP_*`, `UMIDADE_*` / `_avaliar_regras_atuacao` | `L59–L67` / `L58–L79` |
| **Malha fechada** (Sensor reage ao Atuador) | `estufa/sensor.py` / `atuador.py` | `SimuladorAmbiente`, `_on_message` / `_processar_atuador` | `L27–L103` / `L31–L77` |
| **Cliente CLI** tolerante a falhas de quórum/rede | `estufa/cliente.py` | `_executar_acao_segura`, `menu_interativo` | `L41–L105` |
| **Broker MQTT local** (`QoS 0/1`, `PUBACK`) | `estufa/broker_local.py` | `BrokerMQTTLocal`, `_processar_publish`, `executar_broker` | `L47–L328` |

---

## 2. Explicação do Funcionamento por Arquivo

### 2.1 `estufa/config.py` (`67` linhas)
Centraliza as configurações compartilhadas pelos processos:
- **MQTT (`L9–L19`):** `MQTT_HOST = "127.0.0.1"`, `MQTT_PORT = 1883`, `MQTT_KEEPALIVE = 60` e os 6 tópicos de sensores, atuadores e status. O uso direto de `127.0.0.1` evita atraso de resolução IPv6 no loopback.
- **Topologia do Cluster (`L23–L55`):** `MAPA_CONTROLADORES` define os 3 nós (`ctrl_1` rank 1 porta `8001`, `ctrl_2` rank 2 porta `8002`, `ctrl_3` rank 3 porta `8003`) e seus respectivos bancos `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`. `obter_config_controlador` (`L34–L55`) aceita `1..3` ou `"ctrl_1..ctrl_3"`.
- **Regras e Timeouts (`L59–L67`):** `TEMP_MAX_CELSIUS = 35.0`, `TEMP_MIN_CELSIUS = 15.0`, `UMIDADE_MIN_PERCENT = 30.0`, `UMIDADE_MAX_PERCENT = 70.0`, `TIMEOUT_RPC_SEGUNDOS = 1.5`, `INTERVALO_HEARTBEAT_SEGUNDOS = 2.0` e `QUORUM_MINIMO = 2`.

### 2.2 `estufa/middleware.py` (`318` linhas)
Camada lógica usada tanto pelo cliente quanto pelos controladores para comunicação XML-RPC, failover e cálculo de quórum:
1. **Sockets com Timeout Explícito (`_TimeoutTransport`, `L23–L47`):** injeta `conn.timeout` no transporte HTTP do `xmlrpc.client` (`make_connection`, `L30–L33`) para detectar rapidamente nós fora do ar sem bloquear o processo. No cliente (`__init__`, `L85–L95`), o timeout é `TIMEOUT_RPC_SEGUNDOS * 2.5` (`3.75s`) porque um comando no líder dispara duas rodadas RPC em paralelo (`coletar_voto_estado` e `commit_estado`).
2. **Normalização e Quórum Dinâmico (`_normalizar_estado` e `calcular_consenso`, `L110–L170`):**
   - `_normalizar_estado` (`L110–L134`) remove metadados (`ultima_atualizacao`, `lider_id`, `controlador_id`) e compara apenas o estado oficial (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`).
   - `calcular_consenso` (`L137–L170`) conta os votos com `collections.Counter`:
     - **`>= 3` ativos (`L157`):** exige pelo menos `2` votos iguais (`2/3`), tolerando 1 réplica divergente (`--byzantino`).
     - **`2` ativos (`L161`):** exige unanimidade (`2/2`); um empate `1 vs 1` levanta `ErroQuorum`.
     - **`1` ativo (`L166–L168`):** modo degradado `1/1`, mantendo o controle ativo se dois controladores caírem.
     - **`0` ativos (`L150–L151`):** levanta `ErroQuorum`.
3. **Failover e Leitura Paralela (`L172–L272`):**
   - `_ordenar_candidatos` (`L172–L179`) prioriza o último líder conhecido (`_lider_atual`) e depois ordena por maior `rank` (`ctrl_3 -> ctrl_2 -> ctrl_1`).
   - `_chamar_com_failover` (`L194–L227`) tenta o próximo controlador automaticamente em falhas de rede/timeout; se receber `Fault` com `"ERRO_QUORUM"`, propaga `ErroQuorum`.
   - `obter_estado` (`L230–L260`) consulta todos os nós vivos em paralelo via `ThreadPoolExecutor` e aplica `calcular_consenso`.

### 2.3 `estufa/controlador.py` (`911` linhas)
Núcleo de cada réplica do cluster:
1. **Servidor Multi-thread, Locks e Persistência (`L32–L36`, `L101–L202`):**
   - `_ThreadedXMLRPCServer` (`L32–L36`) combina `ThreadingMixIn` com `SimpleXMLRPCServer` (`allow_reuse_address = True`), atendendo `ping`, votação e eleição concorrentemente e permitindo reiniciar rápido na mesma porta.
   - `self._lock` (`RLock`, `L101–L102`) protege só leitura/escrita em memória e disco — chamadas XML-RPC externas rodam fora do lock para evitar deadlock.
   - `_salvar_estado` (`L179–L202`) escreve primeiro em arquivo temporário e faz `os.replace` atômico no `data_ctrl_X.json`.
2. **Eleição de Líder — Bully (`L208–L387`):**
   - Ranks: `ctrl_1 (1) < ctrl_2 (2) < ctrl_3 (3)`.
   - `iniciar_eleicao(rank_origem)` (`L218–L228`): se o nó tiver rank maior, responde `aceito=True` e dispara `realizar_eleicao()` em thread separada.
   - `anunciar_lider(novo_lider_id)` (`L237–L254`): rejeita anúncio se o próprio rank for maior (`L243–L246`) e inicia nova eleição.
   - `realizar_eleicao()` (`L257–L341`): consulta todos os nós de rank maior em paralelo (`L270–L295`). Sem resposta de superiores, assume a liderança e envia `anunciar_lider` + `commit_estado` para os pares (`L297–L322`). Se algum superior responder, aguarda e confirma o novo líder via `ping()` (`L324–L341`).
   - `_loop_heartbeat()` (`L352–L387`): seguidores fazem `ping()` no líder a cada `2.0s`; se falhar, iniciam `realizar_eleicao()`.
3. **Sincronização na Reconexão (`_sincronizar_com_cluster`, `L394–L482`):**
   - No boot (`__init__`, `L151`), `lider_id` inicia `None`. Em `iniciar_servidor_rpc()` (`L832–L848`), o nó busca `obter_estado()` dos pares vivos (`L405–L425`), aplica consenso ou escolhe o estado do líder ativo com `ultima_atualizacao` mais recente (`L443–L460`) e atualiza seu JSON antes de participar da eleição.
4. **Consenso, Persistência Replicada e Comandos MQTT (`L489–L818`):**
   - `coletar_voto_estado(proposta)` (`L489–L537`): se `self.byzantino` estiver ativo (`L495–L502`), retorna dados adulterados (`999.9°C`, `-50.0%` e atuadores invertidos). Caso contrário, valida os limites físicos e aplica `_avaliar_regras_atuacao` (`L58–L79`).
   - `_coordenar_consenso_e_persistir()` (`L578–L670`): executado pelo líder. Coleta votos em paralelo (`L593–L618`), apura `calcular_consenso` (`L623`), carimba `ultima_atualizacao` e `lider_id` (`L624–L625`), grava localmente e envia `commit_estado` aos seguidores (`L627–L648`). Só então o líder publica os comandos MQTT (`_publicar_comando`, `L567–L575`, chamado em `L650–L668`).
   - `_on_message` (`L685–L727`): todos os 3 assinam `estufa/sensores/*` com `qos=1`, mas apenas o líder dispara o ciclo de consenso.
   - `_executar_comando_atuador` (`L747–L818`): se um seguidor receber `comandar_bomba` ou `comandar_exaustor` do cliente, encaminha para o líder atual (`L763–L767`) ou dispara nova eleição caso o líder tenha caído.

### 2.4 `estufa/cliente.py` (`130` linhas)
- Instancia `ClusterMiddleware()` diretamente (`L126`) para falar direto com `8001..8003`.
- `_executar_acao_segura` (`L41–L57`) trata `ErroQuorum`, `Fault` e erros de conexão para o menu continuar funcionando mesmo quando controladores são fechados.
- `menu_interativo` (`L60–L105`) traz consulta por consenso (`1`), acionamento de bomba/exaustor (`2..5`) e saúde/liderança do cluster (`6`).

### 2.5 `estufa/sensor.py` (`170` linhas)
- `SimuladorAmbiente` (`L27–L74`): quando o exaustor está desligado a temperatura sobe (`+1.6..+2.6°C`) e quando ligado cai (`-3.5..-2.2°C`); quando a bomba está desligada a umidade cai (`-4.0..-2.5%`) e quando ligada sobe (`+5.0..+7.5%`).
- Assina `estufa/status/bomba` e `estufa/status/exaustor` (`_on_connect`, `L78–L84`; `_on_message`, `L88–L103`) antes de `connect()` (`L136–L138`) e publica leituras em `executar_sensor` (`L119–L156`) com `qos=1` e `wait_for_publish()` (`L114–L115`). Flags: `--temp`, `--umidade`, `--intervalo` (`L159–L170`).

### 2.6 `estufa/atuador.py` (`96` linhas)
- Assina `estufa/atuadores/bomba` e `estufa/atuadores/exaustor` (`_on_connect`, `L22–L28`).
- `_processar_atuador` (`L42–L63`) valida o comando (`"ligar"`/`"desligar"`), atualiza `_estado_bomba`/`_estado_exaustor` e publica a confirmação em `estufa/status/*` via `_publicar_status` (`L31–L39`), fechando a malha do sensor.

### 2.7 `estufa/broker_local.py` (`336` linhas)
- Broker MQTT v3.1.1 TCP em `127.0.0.1:1883` implementado sobre `socket` e `threading`.
- Trata varint de até 4 bytes (`L17–L44`), `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0/1`, `L290`), `PINGREQ/PINGRESP` e `DISCONNECT` (`L189–L308`), além de verificar porta em uso no startup (`_porta_em_uso`, `L311–L314`, `executar_broker`, `L317–L328`).

---

## 3. Perguntas Prováveis na Apresentação

1. **"Onde fica o Middleware do sistema?"**
   - Ele é distribuído entre o `ClusterMiddleware` (`estufa/middleware.py`, embarcado no cliente e nos nós) e a camada XML-RPC P2P dos próprios controladores (`8001..8003`), seguindo o modelo sem ponto único de falha.
2. **"Como o cliente acha o líder e sobrevive à queda de um controlador?"**
   - O `ClusterMiddleware` tenta primeiro o último líder em cache e depois ordena por rank (`3 -> 2 -> 1`) em `_chamar_com_failover`. Se o nó contatado cair, migra para o próximo; se cair em um seguidor, `_executar_comando_atuador` encaminha ao líder.
3. **"Por que os 3 arquivos JSON nunca ficam dessincronizados?"**
   - Porque ninguém grava leitura MQTT sozinho. O líder coleta os votos (`coletar_voto_estado`), calcula a maioria em `calcular_consenso` e dispara `commit_estado` atômico (`os.replace`) para todas as réplicas ativas.
4. **"O que acontece se derrubarmos `ctrl_3` e depois `ctrl_2`?"**
   - Caindo `ctrl_3`, `_loop_heartbeat` detecta a falha e `realizar_eleicao` elege `ctrl_2` (quórum `2/2`). Caindo `ctrl_2`, `ctrl_1` assume em modo degradado `1/1`. Ao religar `ctrl_2` e `ctrl_3`, `_sincronizar_com_cluster` copia o JSON atualizado antes de o Bully devolver a liderança a `ctrl_3`.
5. **"Como funciona o `--byzantino`?"**
   - Com 3 nós ativos (`ctrl_1`, `ctrl_2 --byzantino`, `ctrl_3`), os 2 honestos formam maioria `2/3` em `calcular_consenso` e descartam os valores adulterados antes de gravar. Se só restarem 1 honesto e 1 bizantino (`1 vs 1`), `calcular_consenso` detecta o empate e lança `ErroQuorum` sem gravar dado inválido.
