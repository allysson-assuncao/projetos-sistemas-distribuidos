# Guia de Estudo, Mapa de Código e Sobrevivência na Defesa — TP1 (Estufa Distribuída)

Material de consulta e estudo para entender a arquitetura de ponta a ponta, localizar no código cada mecanismo distribuído, responder às perguntas da bancada e treinar a demonstração ao vivo.

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

## 2. Explicação Detalhada do Funcionamento por Arquivo

### 2.1 `estufa/config.py` (`66` linhas) — O "Contrato" Compartilhado
Nenhum processo funciona isolado; todos importam `config.py` para falar os mesmos endereços, portas e regras:
- **MQTT (`L9–L19`):** define `MQTT_HOST = "127.0.0.1"`, `MQTT_PORT = 1883` e os **6 tópicos** que ligam Sensor, Controladores e Atuador. Usar `127.0.0.1` direto evita atrasos de resolução DNS/IPv6 no Windows.
- **Topologia do Cluster (`L23–L55`):** `MAPA_CONTROLADORES` cadastra os 3 nós fixos do cluster:
  - `ctrl_1` (`rank=1`, porta `8001`, banco `data_ctrl_1.json`)
  - `ctrl_2` (`rank=2`, porta `8002`, banco `data_ctrl_2.json`)
  - `ctrl_3` (`rank=3`, porta `8003`, banco `data_ctrl_3.json`)
  - O **`rank`** é o número usado pelo algoritmo Bully: quem tem o maior rank vence a eleição (`ctrl_3 > ctrl_2 > ctrl_1`).
- **Regras de Histerese e Timeouts (`L58–L66`):**
  - Temperatura: `> 35.0°C` liga exaustor; `< 15.0°C` desliga exaustor. Entre `15°C` e `35°C` mantém como estava (banda morta / histerese, evitando ficar ligando e desligando toda hora).
  - Umidade: `< 30.0%` liga bomba; `> 70.0%` desliga bomba.
  - `TIMEOUT_RPC_SEGUNDOS = 0.6` (tempo máximo que um controlador espera outro responder na rede local) e `INTERVALO_HEARTBEAT_SEGUNDOS = 2.0` (de quanto em quanto tempo os seguidores checam se o líder está vivo).

### 2.2 `estufa/middleware.py` (`279` linhas) — A Camada Lógica Distribuída
Na Figura 1 do enunciado, o **Middleware** não é um processo separado no meio do caminho — ele é uma **biblioteca lógica** importada pelo `cliente.py` (para achar o líder e fazer failover) e pelo `controlador.py` (para criar proxies RPC e calcular o consenso).
1. **Por que existe `_TimeoutTransport` (`L22–L46`):** a biblioteca padrão `xmlrpc.client.ServerProxy` do Python não aceita um parâmetro `timeout=` direto e, se um servidor cair, pode travar por vários segundos. Essa subclasse injeta `conn.timeout` no socket (`make_connection`, `L29–L32`).
   - Entre controladores: `timeout = 0.6s`.
   - No cliente (`__init__`, `L74–L84`): `timeout = 0.6 * 2.5 = 1.5s`, porque quando o cliente manda um comando ao líder, o líder ainda precisa votar e fazer commit nos pares antes de responder ao cliente.
2. **Normalização e Cálculo de Consenso (`_normalizar_estado` e `calcular_consenso`, `L100–L146`):**
   - Cada controlador carrega seu próprio `ultima_atualizacao` (timestamp em milissegundos) e pode haver pequenas diferenças de metadados. `_normalizar_estado` (`L100–L114`) extrai **apenas os 4 campos oficiais** (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`) em JSON ordenado para comparar votos com precisão.
   - `calcular_consenso(respostas)` (`L118–L146`) usa `collections.Counter` para contar qual estado teve mais votos e aplica o **quórum dinâmico**:
     - `>= 3` respostas: precisa de **pelo menos 2 votos iguais (`2/3`)**. Se 1 nó estiver `--byzantino`, os 2 honestos vencem e o voto adulterado é descartado.
     - `2` respostas: exige **unanimidade (`2/2`)**. Se 1 honesto e 1 bizantino empatarem (`1 vs 1`), lança `ErroQuorum` (`L137–L140`).
     - `1` resposta: **modo degradado (`1/1`)** — aceita o único nó vivo para manter a estufa funcionando.
     - `0` respostas: lança `ErroQuorum` (`L126–L127`).
3. **Descoberta de Líder e Failover (`_ordenar_candidatos`, `_chamar_com_failover`, `L148–L202`):**
   - `_ordenar_candidatos` (`L148–L155`) monta a fila de tentativa: primeiro o último líder guardado em cache (`self._lider_atual`), depois os demais por maior `rank` (`ctrl_3 -> ctrl_2 -> ctrl_1`).
   - `_chamar_com_failover` (`L170–L202`) percorre essa fila para executar `comandar_bomba` ou `comandar_exaustor` (explicado em detalhe na Seção 3.1).
   - `obter_estado` (`L205–L224`) **não confia em um único controlador**: ele consulta todos os nós alcançáveis, reúne as respostas e roda `calcular_consenso(respostas)` no próprio cliente antes de exibir na tela.
   - `verificar_saude` (`L238–L275`) envia `ping()` para os 3 nós e mostra quem está `ok (LÍDER)`, `ok (seguidor)` ou `OFFLINE`.

### 2.3 `estufa/controlador.py` (`779` linhas) — O Cérebro Replicado do Cluster
Os 3 processos (`ctrl_1`, `ctrl_2`, `ctrl_3`) executam exatamente a mesma classe `Controlador`:
1. **Concorrência Segura (`_ThreadedXMLRPCServer` e `self._lock`, `L31–L35`, `L100–L147`):**
   - Cada controlador roda **3 threads principais**: (a) o servidor XML-RPC multi-thread (`serve_forever`), (b) o loop de `_loop_heartbeat` em background e (c) o loop do cliente MQTT (`loop_forever`).
   - `self._lock` (`RLock`) protege apenas a leitura/escrita de `self._estado`, `self.lider_id` e do arquivo `data_ctrl_X.json`. **Regra de ouro:** nenhuma chamada XML-RPC de rede é feita dentro de `with self._lock:`, evitando que dois controladores travem esperando um pelo outro (*deadlock*).
2. **Persistência JSON (`_carregar_estado` e `_salvar_estado`, `L170–L194`):**
   - Ao subir, lê `data_ctrl_X.json` (ou começa com `ESTADO_INICIAL`). Sempre que há consenso ou eleição, `_salvar_estado` grava os 6 campos oficiais (`CAMPOS_PERSISTIDOS`) protegido por `self._lock`.
3. **Eleição Bully e Heartbeat (`L200–L348`):**
   - `ping()`, `iniciar_eleicao()`, `anunciar_lider()`, `realizar_eleicao()` e `_loop_heartbeat()` (fluxo detalhado na Seção 3.3).
4. **Ressincronização no Boot (`_sincronizar_com_cluster`, `L355–L402`):**
   - Quando um controlador cai e é religado, `self.lider_id` começa como `None` (`L142`). Antes de entrar em eleição, ele busca `obter_estado()` nos pares ativos e atualiza seu JSON (fluxo detalhado na Seção 3.4).
5. **Votação, Consenso e Commit (`L409–L552`):**
   - `coletar_voto_estado(proposta)`: cada réplica valida se os valores do sensor são fisicamente possíveis (`_validar_limites_sensor`, `L81–L93`), calcula `_avaliar_regras_atuacao` e devolve seu voto. Se estiver com `--byzantino`, devolve `_gerar_estado_byzantino()` (`999.9°C`, `-50.0%` e atuadores invertidos).
   - `_coordenar_consenso_e_persistir`: executado apenas pelo Líder para coordenar votação, `calcular_consenso`, `commit_estado` nos pares e publicação MQTT (fluxo detalhado na Seção 3.2).
6. **Recepção MQTT e Comandos Manuais (`L559–L694`):**
   - `_on_message` (`L567–L608`): todos os 3 recebem as leituras dos sensores, mas **não alteram `self._estado` antes do consenso**; apenas o Líder inicia `_coordenar_consenso_e_persistir`.
   - `_executar_comando_atuador` (`L627–L686`): trata `comandar_bomba` / `comandar_exaustor`. Se quem recebeu foi um seguidor, encaminha ao líder via `_encaminhar_para_lider` (`L621–L625`).

### 2.4 `estufa/cliente.py` (`130` linhas) — Interface do Operador
- Não possui servidor nem porta aberta e **não fala MQTT**.
- Cria uma instância de `ClusterMiddleware()` (`L126`) e oferece o `menu_interativo` (`L60–L105`) ou `--auto` (`L108–L116`).
- `_executar_acao_segura` (`L41–L57`) envolve toda chamada em `try/except (ErroQuorum, Fault, OSError)` para que o terminal do cliente nunca feche com erro se você matar controladores durante a apresentação.

### 2.5 `estufa/sensor.py` (`155` linhas) — Simulador Físico em Malha Fechada
- `SimuladorAmbiente` (`L25–L59`) simula o ambiente da estufa com passos fixos determinísticos:
  - **Exaustor OFF:** temperatura sobe `+2.0°C` por ciclo; **Exaustor ON:** cai `-2.5°C` por ciclo (limitada entre `0°C` e `55°C`).
  - **Bomba OFF:** umidade cai `-3.0%` por ciclo; **Bomba ON:** sobe `+6.0%` por ciclo (limitada entre `0%` e `100%`).
- Assina `estufa/status/bomba` e `estufa/status/exaustor` (`_on_connect`, `L63–L69`). Quando o atuador confirma que ligou/desligou, `_on_message` (`L73–L88`) atualiza `bomba_ligada` ou `exaustor_ligado` no simulador, invertendo a curva automaticamente.

### 2.6 `estufa/atuador.py` (`96` linhas) — Executor IoT
- Assina `estufa/atuadores/bomba` e `estufa/atuadores/exaustor` (`_on_connect`, `L22–L28`).
- Quando recebe `{"acao": "ligar"}` ou `{"acao": "desligar"}` do Controlador Líder, `_processar_atuador` (`L42–L63`) atualiza `_estado_bomba`/`_estado_exaustor` e publica a confirmação em `estufa/status/*` (`_publicar_status`, `L31–L39`).

### 2.7 `estufa/broker_local.py` (`336` linhas) — Broker MQTT em Python Puro
- Servidor TCP na porta `1883` implementado sobre `socket` e `threading` para permitir rodar o trabalho nos computadores do laboratório Windows sem precisar de Docker ou permissão de Administrador para instalar o Mosquitto.
- Implementa o subconjunto necessário do protocolo MQTT v3.1.1: `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0` e `QoS 1`), `PINGREQ/PINGRESP` e `DISCONNECT`.

---

## 3. Fluxos Completos Passo a Passo (Multi-Arquivo e MQTT)

Esta seção conecta os arquivos entre si para você visualizar exatamente o que acontece em cada cenário que o professor vai testar.

### 3.1 Fluxo Cliente ↔ `ClusterMiddleware` ↔ Controladores (`_chamar_com_failover`)
Quando você escolhe uma ação no `cliente.py` (ex.: `2. Ligar bomba`), o cliente chama `middleware.comandar_bomba(True)`:
1. **`cliente.py` (`L91`)** ➔ chama `middleware.comandar_bomba(True)` dentro de `_executar_acao_segura`.
2. **`middleware.py` (`L226–L230`)** ➔ valida que `ligar` é booleano e chama `self._chamar_com_failover("comandar_bomba", True)`.
3. **`middleware.py` (`L170–L202`, `_chamar_com_failover`):**
   - Pede a lista ordenada em `_ordenar_candidatos()` (`L148–L155`): coloca primeiro o último líder conhecido (`self._lider_atual`, ex.: `ctrl_3`), seguido pelos demais em ordem decrescente de `rank` (`ctrl_2`, `ctrl_1`).
   - Entra no loop `for ctrl in self._ordenar_candidatos():`:
     - Cria um proxy XML-RPC com timeout de `1.5s` (`_criar_proxy`).
     - Tenta chamar `proxy.comandar_bomba(True)`.
     - **Se funcionar:** atualiza `self._lider_atual` (`_atualizar_lider_cache`, `L157–L167`) e devolve o dicionário de resposta para o `cliente.py` imprimir `[OK]`.
     - **Se o controlador estiver morto ou der timeout (`ConnectionRefusedError`, `TimeoutError`, `socket.timeout`):** limpa `_lider_atual` se era ele, imprime `[MIDDLEWARE] Failover: ctrl_X indisponível...` e o `for` passa automaticamente para o próximo controlador da lista (`ctrl_2`).
     - **Se o controlador responder `xmlrpc.client.Fault` com `"ERRO_QUORUM"`:** não tenta outro nó; converte imediatamente em `ErroQuorum` para o cliente exibir `[FALHA DE CONSENSO/QUÓRUM]` (pois o cluster inteiro está em empate, ex.: `1 honesto vs 1 bizantino`).
   - **E se a chamada cair num seguidor (ex.: `ctrl_2` antes de descobrir que `ctrl_3` ainda é líder)?**
     - No `controlador.py`, `_executar_comando_atuador` (`L640–L661`) percebe `if lider_atual != self.ctrl_id:` e chama `_encaminhar_para_lider(par_lider, "bomba", True)` (`L621–L625`), repassando o comando via XML-RPC diretamente ao líder. Se esse líder também tiver caído, o seguidor dispara `self.realizar_eleicao()` na hora (`L656`) para eleger o novo líder e executar o comando.

### 3.2 Processo de Votação, Consenso e Replicação (`_coordenar_consenso_e_persistir`)
Toda mudança de estado (seja vinda do sensor ou do cliente) passa por **4 fases síncronas** coordenadas exclusivamente pelo **Líder** em `controlador.py` (`L490–L552`):
1. **Fase 1 — Montagem da Proposta:** o líder copia o estado anterior e monta `proposta` (com a nova leitura do sensor ou o comando manual do cliente).
2. **Fase 2 — Coleta de Votos (`coletar_voto_estado`, `L409–L449` e `L501–L514`):**
   - O líder computa seu próprio voto (`self.coletar_voto_estado(proposta)`).
   - Em seguida, percorre `for par in pares:` chamando `proxy.coletar_voto_estado(proposta)` via XML-RPC.
   - Cada seguidor honesto valida os limites físicos (`_validar_limites_sensor`), roda `_avaliar_regras_atuacao` e devolve seu voto. Um seguidor `--byzantino` devolve `999.9°C`, `-50.0%` e atuadores invertidos.
3. **Fase 3 — Apuração de Quórum (`ClusterMiddleware.calcular_consenso`, `middleware.py` `L118–L146`):**
   - O líder passa a lista `votos` para `calcular_consenso(votos)`.
   - `3` votos (`2` honestos + `1` bizantino): maioria `2/3` vence, descartando o voto bizantino.
   - `2` votos (`1` honesto + `1` bizantino): empate `1 vs 1` lança `ErroQuorum`, abortando o processo antes de sujar qualquer arquivo JSON.
   - `1` voto (só o líder vivo): modo degradado `1/1` aprova.
4. **Fase 4 — Commit Replicado e Publicação MQTT (`L520–L550`):**
   - O líder carimba `ultima_atualizacao` (UTC) e `lider_id = self.ctrl_id`.
   - Salva no próprio banco (`self.commit_estado(estado_oficial)` ➔ `_salvar_estado()`).
   - Envia `proxy.commit_estado(estado_oficial)` para cada par alcançável (`pares_alcancaveis`), fazendo `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json` ficarem idênticos.
   - **Somente após o commit**, se `bomba_ligada` ou `exaustor_ligado` mudou (ou foi comando manual), o líder chama `_publicar_comando()` (`L479–L487`) no MQTT.

### 3.3 Definição do Líder (Algoritmo Bully) e Heartbeat
O sistema elege e mantém o líder usando prioridade estática por `rank` (`ctrl_1=1`, `ctrl_2=2`, `ctrl_3=3`):
1. **No boot ou após falha (`realizar_eleicao`, `controlador.py` `L241–L302`):**
   - O controlador filtra todos os pares com `rank > self.rank` (`superiores`) e pergunta a cada um via XML-RPC: `iniciar_eleicao(self.rank)` (`L255–L262`).
   - **Caso A — Nenhum superior responde (ex.: `ctrl_3` subindo, ou `ctrl_2` após queda de `ctrl_3`):**
     - Ele conclui `superior_ativo is None`, define `self.lider_id = self.ctrl_id`, salva no JSON e envia `anunciar_lider(self.ctrl_id)` + `commit_estado` para todos os pares vivos (`L264–L284`).
   - **Caso B — Um superior responde `{"aceito": True}` (`L210–L219`):**
     - O superior aceita e dispara sua própria `realizar_eleicao()` em uma thread em background (`L216`). O nó menor aguarda até `0.25s` (`L287`) e confirma quem é o líder via `ping()`.
2. **Guarda de Rank (`anunciar_lider`, `L221–L238`):**
   - Se um nó menor (`ctrl_1`) tentar se anunciar líder enquanto `ctrl_3` está vivo, `ctrl_3` vê `rank_anunciado < self.rank` (`L227`), retorna `{"ok": False}` e inicia `realizar_eleicao()` para retomar a liderança.
3. **Detecção de Queda (`_loop_heartbeat`, `L313–L348`):**
   - A cada `2.0s` (`INTERVALO_HEARTBEAT_SEGUNDOS`), cada seguidor chama `proxy.ping()` no líder atual.
   - Se der `ConnectionRefusedError` ou timeout (`0.6s`), imprime `[HEARTBEAT] Líder 'ctrl_X' falhou...` e chama `self.realizar_eleicao()`, promovendo automaticamente o próximo maior `rank` vivo.

### 3.4 Sincronização na Inicialização / Reinicialização Pós-Queda
Quando um controlador (ex.: `ctrl_3`) cai e você o religa depois que o estado mudou sem ele, o método `iniciar_servidor_rpc()` (`controlador.py` `L700–L716`) executa uma ordem rígida:
1. Sobe o servidor XML-RPC na porta `8003` (`L711`).
2. **Antes de abrir eleição**, chama `self._sincronizar_com_cluster()` (`L712`, implementado em `L355–L402`):
   - Note que no `__init__` (`L142`) o nó nasce com `self.lider_id = None` (ele nunca confia no líder antigo salvo em disco).
   - Ele percorre `self._pares` chamando `obter_estado()` via XML-RPC.
   - Descarta respostas não inicializadas (`ultima_atualizacao is None`) ou fora dos limites físicos.
   - Passa os estados válidos por `ClusterMiddleware.calcular_consenso(estados_validos)` (`L383`).
   - Atualiza `self._estado` e grava imediatamente em `data_ctrl_3.json` via `_salvar_estado()` (`L395`).
3. Só **depois** de estar com o banco JSON sincronizado é que chama `self.realizar_eleicao()` (`L713`) para reassumir a liderança (por ter `rank=3`) e inicia `_loop_heartbeat` (`L714`).

### 3.5 Os Tópicos MQTT e o Fluxo Autônomo (Sensor ↔ Controladores ↔ Atuador)

No projeto existem **6 tópicos MQTT** no `broker_local.py` (`:1883`), todos usando `QoS 1` (garantia de entrega com `PUBACK`), divididos em **3 etapas da malha fechada**:

```text
[1. Telemetria]   sensor.py  --PUB--> estufa/sensores/temperatura   --SUB--> ctrl_1, ctrl_2, ctrl_3
                             --PUB--> estufa/sensores/umidade_solo  --SUB--> ctrl_1, ctrl_2, ctrl_3

[2. Comando]      LÍDER      --PUB--> estufa/atuadores/exaustor     --SUB--> atuador.py
                  (só ele!)  --PUB--> estufa/atuadores/bomba        --SUB--> atuador.py

[3. Feedback]     atuador.py --PUB--> estufa/status/exaustor        --SUB--> sensor.py
                             --PUB--> estufa/status/bomba           --SUB--> sensor.py
```

**Passo a passo do ciclo autônomo completo:**
1. **`sensor.py` (`L125–L128`):** a cada `--intervalo` segundos, `simulador.proxima_leitura()` calcula a nova temperatura e umidade e `publicar_leitura()` publica nos tópicos `estufa/sensores/temperatura` e `estufa/sensores/umidade_solo`.
2. **`broker_local.py` (`L273–L308`):** recebe o `PUBLISH`, envia `PUBACK` ao sensor e encaminha a mensagem para os 3 controladores inscritos.
3. **`controlador.py` (`_on_message`, `L567–L608`):**
   - Os 3 controladores recebem a mensagem e validam `_validar_limites_sensor`.
   - **Seguidores (`ctrl_1`, `ctrl_2`):** não alteram `self._estado` e param aqui (aguardando o líder).
   - **Líder (`ctrl_3`):** monta `proposta` com a nova leitura e chama `_coordenar_consenso_e_persistir(proposta, publicar_atuacao=True)` (`L605`).
4. **Consenso + Decisão (`L490–L550`):**
   - Na votação (`coletar_voto_estado`), os controladores avaliam `_avaliar_regras_atuacao`: se `temp > 35.0°C`, votam `exaustor_ligado = True`; se `umidade < 30.0%`, votam `bomba_ligada = True`.
   - Após `calcular_consenso` e `commit_estado` nos JSONs, o líder compara o novo estado com `estado_anterior` (`L542–L550`). Se houve mudança, publica `{"acao": "ligar"}` em `estufa/atuadores/exaustor` ou `estufa/atuadores/bomba`.
5. **`atuador.py` (`_on_message` ➔ `_processar_atuador`, `L42–L77`):**
   - Recebe o comando, muda seu estado interno (`_estado_bomba` / `_estado_exaustor`) e publica `{"atuador": "exaustor", "ligado": True}` em `estufa/status/exaustor` (ou `estufa/status/bomba`).
6. **`sensor.py` (`_on_message`, `L73–L88`):**
   - Recebe o feedback de `estufa/status/*`, atualiza `simulador.exaustor_ligado = True` (ou `bomba_ligada = True`) e, no próximo ciclo, passa a resfriar (`-2.5°C`) e/ou umidificar (`+6.0%`), fechando a malha.

### 3.6 Fluxo das Chamadas Manuais do Cliente
Quando você escolhe `2. Ligar bomba` ou `4. Ligar exaustor` no `cliente.py`:
1. **`cliente.py` (`L91`)** ➔ **`middleware.py` (`_chamar_com_failover`, `L170–L202`)**: envia `comandar_bomba(True)` via XML-RPC ao líder em cache (com failover se ele tiver caído).
2. **`controlador.py` (`_executar_comando_atuador`, `L627–L686`)**:
   - Se chegou em um seguidor, encaminha ao líder (`_encaminhar_para_lider`, `L621–L625`).
   - No líder, monta uma proposta manual (`{"manual": True, "bomba_ligada": True, ...}`, `L663–L669`) e chama `_coordenar_consenso_e_persistir(..., forcar_publicacao=("bomba", True))`.
3. **Consenso + Persistência + MQTT (`L490–L552`)**:
   - Os pares votam, `calcular_consenso` aprova (se houver quórum), `commit_estado` grava o novo estado nos 3 `data_ctrl_*.json` e o líder publica `{"acao": "ligar"}` no tópico MQTT `estufa/atuadores/bomba`.
4. **Retorno ao Cliente (`L680–L686`)**:
   - O líder devolve o estado atualizado com `"sucesso": True` e `"mensagem": "Bomba ligada com sucesso"`, que aparece na tela do `cliente.py` (`L47`).
   - Paralelamente, o `atuador.py` executa e avisa o `sensor.py` via `estufa/status/bomba`.

---

## 4. Guia de Sobrevivência para a Bancada

### 4.1 Comparação Direta: Controlador Líder vs. Controlador Seguidor

Todos os 3 processos executam o mesmo código (`estufa/controlador.py`), mas o resultado da eleição (`self.eh_lider()`) define a autonomia:

| Ação / Responsabilidade | Controlador **Líder** (`lider_id == ctrl_id`) | Controlador **Seguidor** (`lider_id != ctrl_id`) |
|---|---|---|
| **Leitura MQTT dos Sensores** | Recebe a leitura e inicia o consenso (`_coordenar_consenso_e_persistir`). | Recebe a leitura (pronto para assumir se o líder cair), mas **não altera seu estado nem inicia consenso**. |
| **Decisão (Histerese)** | Avalia `_avaliar_regras_atuacao` e envia proposta aos pares. | Valida a proposta recebida do líder quando chamado em `coletar_voto_estado()`. |
| **Gravação no Banco JSON** | Apura o quórum, grava localmente e ordena `commit_estado` aos pares. | Só grava quando recebe `commit_estado()` do líder (ou ao ressincronizar no boot). |
| **Comando MQTT ao Atuador** | **Exclusivo do Líder:** publica em `estufa/atuadores/*`. | **Nunca publica** no MQTT de atuadores (evita comandos duplicados). |
| **Comandos do Cliente** | Executa consenso, grava e publica ao atuador. | **Encaminha via RPC para o Líder** (`_encaminhar_para_lider`). |
| **Monitoramento** | Responde `ping()` dos seguidores. | Envia `ping()` ao líder a cada `2s` (`_loop_heartbeat`); se falhar, abre `realizar_eleicao()`. |

### 4.2 Mapa das 8 Chamadas XML-RPC (`controlador.py` `:8001..8003`)

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

### 4.3 As 7 Perguntas Críticas do Professor (Respostas Prontas)

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

### 4.4 Checklist de Treino Prático na Tela

- [ ] Suba o sistema com `start_all.ps1` e deixe os arquivos `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json` abertos lado a lado no VS Code para provar visualmente a replicação.
- [ ] Antes de apertar `Ctrl+C` no `ctrl_3`, diga em voz alta: *"Agora o heartbeat de `ctrl_2` e `ctrl_1` vai falhar em até 2s e `ctrl_2` assumirá a liderança"*.
- [ ] Aperte `Ctrl+C` no `ctrl_2`, faça uma alteração no cliente (`ctrl_1` em `1/1`), depois use `↑` + `Enter` na janela do `ctrl_2` e `ctrl_3` para mostrar o `[SYNC]` e os JSONs convergindo na hora.
- [ ] Suba `ctrl_2 --byzantino` (editando a linha após `↑`), mostre que o cliente e os JSONs continuam corretos (`2/3`), e depois derrube `ctrl_1` para mostrar o `[FALHA DE CONSENSO/QUÓRUM]` (`1 vs 1`).
