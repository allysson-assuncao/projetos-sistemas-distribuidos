# Guia de Estudo, Mapa de Código e Sobrevivência na Defesa — TP1 (Estufa Distribuída)

Material de consulta rápida para localizar no código cada mecanismo distribuído, responder às perguntas práticas e conceituais da bancada e treinar a demonstração ao vivo.

---

## 1. Onde Mostrar Cada Mecanismo no Código (Consulta Rápida)

| Mecanismo para Demonstrar | Arquivo | Símbolo / Função | Linhas |
|---|---|---|---|
| **Eleição de líder (Algoritmo Bully)** e guarda de rank | `estufa/controlador.py` | `ping`, `iniciar_eleicao`, `anunciar_lider`, `realizar_eleicao` | `L200–L302` |
| **Heartbeat** e detecção de queda do líder | `estufa/controlador.py` | `Controlador._loop_heartbeat` | `L313–L348` |
| **Consenso e quórum dinâmico (`3→2/3`, `2/2`, `1/1`, `ErroQuorum`)** | `estufa/middleware.py` | `_normalizar_estado`, `calcular_consenso` | `L100–L146` |
| **Votação P2P** e **commit replicado** nos JSONs | `estufa/controlador.py` | `coletar_voto_estado`, `commit_estado`, `_coordenar_consenso_e_persistir` | `L409–L552` |
| **Persistência JSON protegida por `RLock`** | `estufa/controlador.py` | `_carregar_estado`, `_salvar_estado` | `L170–L194` |
| **Falha bizantina (`--byzantino`)** | `estufa/controlador.py` | `_gerar_estado_byzantino`, `coletar_voto_estado`, `obter_estado` | `L157–L168`, `L409–L420`, `L614–L619` |
| **Ressincronização ao religar um controlador** | `estufa/controlador.py` | `Controlador._sincronizar_com_cluster` | `L355–L402` |
| **Failover do cliente e descoberta do líder** | `estufa/middleware.py` | `_ordenar_candidatos`, `_chamar_com_failover`, `obter_estado` | `L148–L224` |
| **Encaminhamento seguidor → líder** em comandos manuais | `estufa/controlador.py` | `_encaminhar_para_lider`, `_executar_comando_atuador` | `L621–L686` |
| **Publicação MQTT exclusiva do líder** | `estufa/controlador.py` | `_publicar_comando`, `_on_connect`, `_on_message` | `L479–L487`, `L559–L608` |
| **Regras de temperatura e umidade** (histerese) | `estufa/config.py` / `controlador.py` | `TEMP_*`, `UMIDADE_*` / `_avaliar_regras_atuacao` | `L58–L62` / `L57–L78` |
| **Malha fechada determinística** (Sensor reage ao Atuador) | `estufa/sensor.py` / `atuador.py` | `SimuladorAmbiente`, `_on_message` / `_processar_atuador` | `L25–L88` / `L31–L77` |
| **Cliente CLI** tolerante a falhas de quórum/rede | `estufa/cliente.py` | `_executar_acao_segura`, `menu_interativo` | `L41–L105` |
| **Broker MQTT local** (`QoS 0/1`, `PUBACK`) | `estufa/broker_local.py` | `BrokerMQTTLocal`, `_processar_publish`, `executar_broker` | `L47–L328` |

---

## 2. Explicação do Funcionamento por Arquivo

### 2.1 `estufa/config.py` (`66` linhas)
Centraliza as configurações compartilhadas pelos processos:
- **MQTT (`L9–L19`):** `MQTT_HOST = "127.0.0.1"`, `MQTT_PORT = 1883`, `MQTT_KEEPALIVE = 60` e os 6 tópicos de sensores, atuadores e status. O uso direto de `127.0.0.1` evita atraso de resolução IPv6 no loopback.
- **Topologia do Cluster (`L23–L55`):** `MAPA_CONTROLADORES` define os 3 nós (`ctrl_1` rank 1 porta `8001`, `ctrl_2` rank 2 porta `8002`, `ctrl_3` rank 3 porta `8003`) e seus respectivos bancos `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`. `obter_config_controlador` (`L34–L55`) aceita `1..3` ou `"ctrl_1..ctrl_3"`.
- **Regras e Timeouts (`L58–L66`):** `TEMP_MAX_CELSIUS = 35.0`, `TEMP_MIN_CELSIUS = 15.0`, `UMIDADE_MIN_PERCENT = 30.0`, `UMIDADE_MAX_PERCENT = 70.0`, `TIMEOUT_RPC_SEGUNDOS = 0.6` e `INTERVALO_HEARTBEAT_SEGUNDOS = 2.0`.

### 2.2 `estufa/middleware.py` (`279` linhas)
Camada lógica usada tanto pelo cliente quanto pelos controladores para comunicação XML-RPC, failover e cálculo de quórum:
1. **Sockets com Timeout Explícito (`_TimeoutTransport`, `L22–L46`):** injeta `conn.timeout` no transporte HTTP do `xmlrpc.client` (`make_connection`, `L29–L32`) para detectar rapidamente nós fora do ar sem bloquear o processo. No cliente (`__init__`, `L74–L84`), o timeout padrão é `TIMEOUT_RPC_SEGUNDOS * 2.5` (`1.5s`) porque um comando no líder dispara votação e commit nos pares.
2. **Normalização e Quórum Dinâmico (`_normalizar_estado` e `calcular_consenso`, `L100–L146`):**
   - `_normalizar_estado` (`L100–L114`) ignora metadados voláteis (`ultima_atualizacao`, `lider_id`) e compara apenas os 4 campos oficiais (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`).
   - `calcular_consenso` (`L118–L146`) conta os votos com `collections.Counter`:
     - **`>= 3` ativos (`L133`):** exige pelo menos `2` votos iguais (`2/3`), tolerando 1 réplica divergente (`--byzantino`).
     - **`2` ativos (`L137`):** exige unanimidade (`2/2`); um empate `1 vs 1` levanta `ErroQuorum`.
     - **`1` ativo (`L142–L144`):** modo degradado `1/1`, mantendo o controle ativo se dois controladores caírem.
     - **`0` ativos (`L126–L127`):** levanta `ErroQuorum`.
3. **Failover e Consulta ao Cluster (`L148–L275`):**
   - `_ordenar_candidatos` (`L148–L155`) prioriza o último líder conhecido (`_lider_atual`) e depois ordena por maior `rank` (`ctrl_3 -> ctrl_2 -> ctrl_1`).
   - `_chamar_com_failover` (`L170–L202`) percorre os candidatos sequencialmente em falhas de rede/timeout; se receber `Fault` com `"ERRO_QUORUM"`, propaga `ErroQuorum`.
   - `obter_estado` (`L205–L224`) consulta cada réplica acessível e aplica `calcular_consenso`.
   - `verificar_saude` (`L238–L275`) envia `ping()` para cada controlador e identifica o líder e os nós offline.

### 2.3 `estufa/controlador.py` (`779` linhas)
Nó replicado do cluster:
1. **Servidor Multi-thread, Locks e Persistência (`L31–L35`, `L96–L194`):**
   - `_ThreadedXMLRPCServer` (`L31–L35`) combina `ThreadingMixIn` com `SimpleXMLRPCServer` (`allow_reuse_address = True`), atendendo `ping`, votação e eleição concorrentemente e permitindo reiniciar rápido na mesma porta.
   - `self._lock` (`RLock`, `L100–L101`) protege leitura/escrita em memória e disco — chamadas XML-RPC externas rodam sempre fora do lock para evitar deadlock.
   - `_salvar_estado` (`L186–L194`) grava `data_ctrl_X.json` diretamente com `json.dump()` protegido por `self._lock`.
2. **Eleição de Líder — Bully (`L200–L348`):**
   - Ranks: `ctrl_1 (1) < ctrl_2 (2) < ctrl_3 (3)`.
   - `iniciar_eleicao(rank_origem)` (`L210–L219`): se o nó tiver rank maior, responde `aceito=True` e dispara `realizar_eleicao()` em thread separada.
   - `anunciar_lider(novo_lider_id)` (`L221–L238`): rejeita anúncio se o próprio rank for maior (`L227–L230`) e inicia nova eleição.
   - `realizar_eleicao()` (`L241–L302`): consulta os nós de rank maior em ordem decrescente (`L255–L262`). Sem resposta de superiores, assume a liderança e envia `anunciar_lider` + `commit_estado` para os pares (`L264–L284`). Se algum superior responder, aguarda brevemente e confirma o novo líder via `ping()` (`L286–L302`).
   - `_loop_heartbeat()` (`L313–L348`): seguidores fazem `ping()` no líder a cada `2.0s`; se falhar, iniciam `realizar_eleicao()`.
3. **Sincronização na Reconexão (`_sincronizar_com_cluster`, `L355–L402`):**
   - No boot (`__init__`, `L142`), `lider_id` inicia `None`. Em `iniciar_servidor_rpc()` (`L700–L716`), o nó busca `obter_estado()` dos pares vivos (`L364–L376`), aplica `ClusterMiddleware.calcular_consenso()` (`L383`) e atualiza seu JSON antes de participar da eleição.
4. **Consenso, Persistência Replicada e Comandos MQTT (`L409–L694`):**
   - `coletar_voto_estado(proposta)` (`L409–L449`): se `self.byzantino` estiver ativo (`L415–L416`), retorna `_gerar_estado_byzantino()` (`999.9°C`, `-50.0%` e atuadores invertidos). Caso contrário, valida limites físicos e aplica `_avaliar_regras_atuacao` (`L57–L78`).
   - `_coordenar_consenso_e_persistir()` (`L490–L552`): executado apenas pelo líder. Coleta votos dos pares ativos (`L504–L514`), apura `calcular_consenso` (`L519`), carimba `ultima_atualizacao` e `lider_id` (`L520–L521`), grava localmente e envia `commit_estado` aos seguidores (`L523–L529`). Só então o líder publica os comandos MQTT (`_publicar_comando`, `L479–L487`, chamado em `L531–L550`).
   - `_on_message` (`L567–L608`): todos os 3 assinam `estufa/sensores/*` com `qos=1`, mas **nenhum altera `self._estado` antes do consenso**; apenas o líder monta a proposta e dispara `_coordenar_consenso_e_persistir`.
   - `_executar_comando_atuador` (`L627–L686`): se um seguidor receber `comandar_bomba` ou `comandar_exaustor` do cliente, encaminha via `_encaminhar_para_lider` (`L621–L625`) ou dispara nova eleição caso o líder tenha caído.

### 2.4 `estufa/cliente.py` (`130` linhas)
- Instancia `ClusterMiddleware()` diretamente (`L126`) para falar direto com `8001..8003`.
- `_executar_acao_segura` (`L41–L57`) trata `ErroQuorum`, `Fault` e erros de conexão para o menu continuar funcionando mesmo quando controladores são fechados.
- `menu_interativo` (`L60–L105`) traz consulta por consenso (`1`), acionamento de bomba/exaustor (`2..5`) e saúde/liderança do cluster (`6`).

### 2.5 `estufa/sensor.py` (`155` linhas)
- `SimuladorAmbiente` (`L25–L59`): utiliza passos fixos determinísticos — quando o exaustor está desligado a temperatura sobe `+2.0°C` e quando ligado cai `-2.5°C` (limitada em `[0, 55]°C`); quando a bomba está desligada a umidade cai `-3.0%` e quando ligada sobe `+6.0%` (limitada em `[0, 100]%`).
- Assina `estufa/status/bomba` e `estufa/status/exaustor` (`_on_connect`, `L63–L69`; `_on_message`, `L73–L88`) antes de `connect()` (`L119–L121`) e publica leituras em `executar_sensor` (`L104–L141`) com `qos=1` e `wait_for_publish()` (`L99–L100`). Flags: `--temp`, `--umidade`, `--intervalo` (`L144–L155`).

### 2.6 `estufa/atuador.py` (`96` linhas)
- Assina `estufa/atuadores/bomba` e `estufa/atuadores/exaustor` (`_on_connect`, `L22–L28`).
- `_processar_atuador` (`L42–L63`) valida o comando (`"ligar"`/`"desligar"`), atualiza `_estado_bomba`/`_estado_exaustor` e publica a confirmação em `estufa/status/*` via `_publicar_status` (`L31–L39`), fechando a malha do sensor.

### 2.7 `estufa/broker_local.py` (`336` linhas)
- Broker MQTT v3.1.1 TCP em `127.0.0.1:1883` implementado sobre `socket` e `threading` para rodar no laboratório Windows sem Docker/Mosquitto.
- Trata varint de até 4 bytes (`L17–L44`), `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0/1`, `L290`), `PINGREQ/PINGRESP` e `DISCONNECT` (`L189–L308`), além de verificar porta em uso no startup (`_porta_em_uso`, `L311–L314`, `executar_broker`, `L317–L328`).

---

## 3. Guia de Sobrevivência para a Bancada

### 3.1 Comparação Direta: Controlador Líder vs. Controlador Seguidor

Todos os 3 processos executam o mesmo código (`estufa/controlador.py`), mas o resultado da eleição (`self.eh_lider()`) define a autonomia:

| Ação / Responsabilidade | Controlador **Líder** (`lider_id == ctrl_id`) | Controlador **Seguidor** (`lider_id != ctrl_id`) |
|---|---|---|
| **Leitura MQTT dos Sensores** | Recebe a leitura e inicia o consenso (`_coordenar_consenso_e_persistir`). | Recebe a leitura (pronto para assumir se o líder cair), mas **não altera seu estado nem inicia consenso**. |
| **Decisão (Histerese)** | Avalia `_avaliar_regras_atuacao` e envia proposta aos pares. | Valida a proposta recebida do líder quando chamado em `coletar_voto_estado()`. |
| **Gravação no Banco JSON** | Apura o quórum, grava localmente e ordena `commit_estado` aos pares. | Só grava quando recebe `commit_estado()` do líder (ou ao ressincronizar no boot). |
| **Comando MQTT ao Atuador** | **Exclusivo do Líder:** publica em `estufa/atuadores/*`. | **Nunca publica** no MQTT de atuadores (evita comandos duplicados). |
| **Comandos do Cliente** | Executa consenso, grava e publica ao atuador. | **Encaminha via RPC para o Líder** (`_encaminhar_para_lider`). |
| **Monitoramento** | Responde `ping()` dos seguidores. | Envia `ping()` ao líder a cada `2s` (`_loop_heartbeat`); se falhar, abre `realizar_eleicao()`. |

### 3.2 Mapa das 8 Chamadas XML-RPC (`controlador.py` `:8001..8003`)

| Método XML-RPC | Quem Chama | Quem Responde | Papel no Sistema |
|---|---|---|---|
| `ping()` | Seguidores (`_loop_heartbeat`) / Cliente (`verificar_saude`) | Qualquer controlador | Detecção de falhas e identificação do `lider_id` atual. |
| `iniciar_eleicao(rank_origem)` | Nó de rank menor em `realizar_eleicao()` | Nó de rank maior | Algoritmo Bully: o nó maior aceita (`aceito=True`) e assume a eleição. |
| `anunciar_lider(novo_lider_id)` | Novo líder eleito | Todos os pares | Registra o novo coordenador (ou rejeita se quem recebeu tiver rank maior). |
| `coletar_voto_estado(proposta)` | Líder em `_coordenar_consenso_e_persistir()` | Pares ativos | Coleta votos de histerese/estado antes do commit (ou retorna erro em `--byzantino`). |
| `commit_estado(estado_oficial)` | Líder após `calcular_consenso()` | Todos os pares alcançáveis | Replicação síncrona nos arquivos `data_ctrl_1..3.json`. |
| `obter_estado()` | Cliente (`ClusterMiddleware`) / Nó no boot (`_sincronizar_com_cluster`) | Todos os pares alcançáveis | Leitura por consenso no cliente e recuperação de banco na reconexão. |
| `comandar_bomba(ligar)` | Cliente (`ClusterMiddleware`) / Seguidor encaminhando | Líder (ou seguidor que repassa) | Acionamento manual da bomba com consenso e publicação MQTT. |
| `comandar_exaustor(ligar)` | Cliente (`ClusterMiddleware`) / Seguidor encaminhando | Líder (ou seguidor que repassa) | Acionamento manual do exaustor com consenso e publicação MQTT. |

### 3.3 Mapa dos 6 Tópicos MQTT (`broker_local.py` `:1883`, `QoS 1`)

| Tópico MQTT | Quem Publica | Quem Assina | Finalidade |
|---|---|---|---|
| `estufa/sensores/temperatura` | `sensor.py` | `ctrl_1`, `ctrl_2`, `ctrl_3` | Envia temperatura atual (°C). |
| `estufa/sensores/umidade_solo` | `sensor.py` | `ctrl_1`, `ctrl_2`, `ctrl_3` | Envia umidade atual (%). |
| `estufa/atuadores/bomba` | **Somente o Controlador Líder** | `atuador.py` | Comando oficial `"ligar"` / `"desligar"` bomba. |
| `estufa/atuadores/exaustor` | **Somente o Controlador Líder** | `atuador.py` | Comando oficial `"ligar"` / `"desligar"` exaustor. |
| `estufa/status/bomba` | `atuador.py` | `sensor.py` | Confirmação de estado para fechar a malha do sensor. |
| `estufa/status/exaustor` | `atuador.py` | `sensor.py` | Confirmação de estado para fechar a malha do sensor. |

### 3.4 As 7 Perguntas Críticas do Professor (Respostas Prontas)

1. **"Onde fica o Middleware da Figura 1? Por que não existe um servidor `middleware_server.py`?"**
   - Na Figura 1 do enunciado, o bloco `MIDDLEWARE` **engloba os Controladores de Processo**. Um processo intermediário único seria um Ponto Único de Falha (SPOF). Por isso `estufa/middleware.py` (`ClusterMiddleware`) é uma camada lógica embarcada diretamente no `cliente.py` e nos controladores (`8001..8003`).
2. **"Por que usar MQTT e XML-RPC juntos no mesmo sistema?"**
   - A camada IoT (`sensor`/`atuador`) usa **MQTT (Publish/Subscribe)** para desacoplamento no tempo e no espaço — o sensor não precisa conhecer IPs nem quantos controladores existem. Já a camada de controle e cliente usa **XML-RPC (Invocação Remota de Métodos)** porque exige comunicação síncrona orientada a métodos com retorno imediato para votação de quórum, eleição e comandos manuais.
3. **"Se todos os controladores recebem as leituras do sensor via MQTT, por que o atuador não recebe 3 comandos?"**
   - Todos assinam `estufa/sensores/#` para estar prontos em caso de failover, mas `_on_message` (`L599–L608`) verifica `if sou_lider:`. Só o Líder coordena o consenso e chama `_publicar_comando()` (`L479–L487`).
4. **"O que acontece quando eu derrubar o `ctrl_3` com `Ctrl+C`?"**
   - Os seguidores fazem `ping()` no líder a cada `2s` em `_loop_heartbeat` (`L313–L348`). Ao detectar `ConnectionRefusedError`/timeout (`0.6s`), chamam `realizar_eleicao()` (Bully). Como `ctrl_3` (`rank=3`) não responde, `ctrl_2` (`rank=2`) assume a liderança, anuncia para `ctrl_1` (`rank=1`) e o sistema segue operando com quórum `2/2`.
5. **"E se eu religar o `ctrl_3` depois de alterar o estado sem ele?"**
   - No startup (`iniciar_servidor_rpc`, `L700–L716`), `ctrl_3` executa `_sincronizar_com_cluster()` (`L355–L402`) **antes** da eleição: ele busca `obter_estado()` nos pares ativos, valida por `calcular_consenso()`, atualiza `data_ctrl_3.json` e só então reassume a liderança pelo Bully.
6. **"Como vocês garantem a segurança se um controlador for invadido ou responder valores falsos (`--byzantino`)?"**
   - Com 3 nós ativos (`2 honestos + 1 bizantino`), `calcular_consenso()` exige maioria `>= 2/3`: os 2 honestos concordam e descartam o voto adulterado (`999.9°C`, `-50%`). Se restarem apenas 2 nós (`1 honesto vs 1 bizantino`), ocorre empate `1 vs 1`, `calcular_consenso()` lança `ErroQuorum` e o sistema bloqueia a gravação e atuação (**fail-safe**).
7. **"Sobre `broker_local.py`, por que ele foi escrito em código de sockets?"**
   - O sistema usa o protocolo padrão MQTT v3.1.1 com `paho-mqtt` e inclui `docker-compose.yml` para o Eclipse Mosquitto. O `broker_local.py` é um broker MQTT leve em Python puro adicionado para permitir executar a demonstração nos computadores do laboratório sem depender de Docker ou permissão de Administrador.

### 3.5 Como Treinar e Dominar o Código Antes da Apresentação

1. **Estude seguindo 3 Fluxos (não decore arquivos isolados):**
   - **Fluxo 1 (Malha Fechada IoT):** `sensor.py:proxima_leitura` ➔ `publicar_leitura` ➔ `controlador.py:_on_message` ➔ `_coordenar_consenso_e_persistir` (`coletar_voto_estado` ➔ `calcular_consenso` ➔ `commit_estado` ➔ `_publicar_comando`) ➔ `atuador.py:_processar_atuador` ➔ `sensor.py:_on_message`.
   - **Fluxo 2 (Queda e Reconexão):** `controlador.py:_loop_heartbeat` (`ping` falha) ➔ `realizar_eleicao` (`iniciar_eleicao` / `anunciar_lider`) ➔ ao religar: `iniciar_servidor_rpc` ➔ `_sincronizar_com_cluster` ➔ `realizar_eleicao`.
   - **Fluxo 3 (Cliente e Failover):** `cliente.py:menu_interativo` ➔ `middleware.py:obter_estado` / `_chamar_com_failover` ➔ `controlador.py:_executar_comando_atuador` (`_encaminhar_para_lider`).
2. **Checklist de Treino Prático na Tela:**
   - [ ] Suba o sistema com `start_all.ps1` e deixe os arquivos `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json` abertos lado a lado no VS Code para provar visualmente a replicação.
   - [ ] Antes de apertar `Ctrl+C` no `ctrl_3`, diga em voz alta: *"Agora o heartbeat de `ctrl_2` e `ctrl_1` vai falhar em até 2s e `ctrl_2` assumirá a liderança"*.
   - [ ] Aperte `Ctrl+C` no `ctrl_2`, faça uma alteração no cliente (`ctrl_1` em `1/1`), depois use `↑` + `Enter` na janela do `ctrl_2` e `ctrl_3` para mostrar o `[SYNC]` e os JSONs convergindo na hora.
   - [ ] Suba `ctrl_2 --byzantino` (editando a linha após `↑`), mostre que o cliente e os JSONs continuam corretos (`2/3`), e depois derrube `ctrl_1` para mostrar o `[FALHA DE CONSENSO/QUÓRUM]` (`1 vs 1`).
