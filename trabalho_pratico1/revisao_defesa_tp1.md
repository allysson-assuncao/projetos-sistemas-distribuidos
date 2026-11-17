# Revisão Técnica e Guia Detalhado de Defesa — Trabalho Prático 1 (SD)

Este documento detalha o funcionamento interno de todos os módulos refatorados do projeto (`trabalho_pratico1/estufa/`), com referências exatas de arquivo, símbolo e linhas para consulta rápida durante a arguição com o professor.

---

## 1. Mapa Rápido de Pontos Críticos no Código

| Tópico de Arguição | Arquivo | Símbolo / Função | Linhas |
|---|---|---|---|
| Topologia do cluster, rank Bully, histerese e timeouts | `estufa/config.py` | `MAPA_CONTROLADORES`, `obter_config_controlador`, `TIMEOUT_RPC_SEGUNDOS` | `L23–L67` |
| Timeout de socket XML-RPC no Windows | `estufa/middleware.py` | `_TimeoutTransport`, `criar_proxy_rpc` | `L23–L47` |
| Consenso dinâmico (`3->2/3`, `2/2`, `1/1` e `ErroQuorum`) | `estufa/middleware.py` | `ClusterMiddleware._normalizar_estado`, `calcular_consenso` | `L110–L170` |
| Failover transparente do Cliente Direto (sem `:9000`) | `estufa/middleware.py` | `ClusterMiddleware._chamar_com_failover`, `obter_estado` | `L194–L260` |
| Servidor XML-RPC multi-thread (sem bloqueios nem `WinError 10048`) | `estufa/controlador.py` | `_ThreadedXMLRPCServer` | `L32–L36` |
| Persistência JSON atômica local | `estufa/controlador.py` | `Controlador._carregar_estado`, `_salvar_estado` | `L161–L202` |
| Eleição de líder (Algoritmo Bully) e guarda de rank | `estufa/controlador.py` | `ping`, `iniciar_eleicao`, `anunciar_lider`, `realizar_eleicao` | `L208–L341` |
| Detecção de queda do líder por Heartbeat | `estufa/controlador.py` | `Controlador._loop_heartbeat` | `L352–L387` |
| Sincronização de réplica ao reconectar (`State Transfer`) | `estufa/controlador.py` | `Controlador._sincronizar_com_cluster` | `L394–L482` |
| Votação P2P, simulação `--byzantino` e commit replicado | `estufa/controlador.py` | `coletar_voto_estado`, `commit_estado`, `_coordenar_consenso_e_persistir` | `L489–L670` |
| Inscrição MQTT QoS 1 e publicação exclusiva do Líder | `estufa/controlador.py` | `_publicar_comando`, `_on_connect`, `_on_message` | `L567–L575`, `L677–L727` |
| Encaminhamento seguidor → líder em comandos manuais | `estufa/controlador.py` | `Controlador._executar_comando_atuador` | `L747–L818` |
| Cliente resiliente a falhas de quórum e queda de nós | `estufa/cliente.py` | `_executar_acao_segura`, `menu_interativo` | `L41–L105` |
| Sensor contínuo em malha fechada e inscrição MQTT QoS 1 | `estufa/sensor.py` | `SimuladorAmbiente`, `_on_connect`, `_on_message`, `executar_sensor` | `L27–L156` |
| Atuador unificado (sem cache LRU) e feedback de status | `estufa/atuador.py` | `_on_connect`, `_publicar_status`, `_processar_atuador`, `_on_message` | `L22–L77` |
| Broker MQTT v3.1.1 em Python puro (varint, `PUBACK`, porta ocupada) | `estufa/broker_local.py` | `BrokerMQTTLocal`, `_atender_cliente`, `_processar_publish`, `executar_broker` | `L47–L328` |

---

## 2. Análise Detalhada Módulo a Módulo

### 2.1 `estufa/config.py` (`67` linhas)
Centraliza todas as constantes compartilhadas sem credenciais ou dependências externas:
- **MQTT (`L9–L19`):** Define `MQTT_HOST = "127.0.0.1"`, `MQTT_PORT = 1883`, `MQTT_KEEPALIVE = 60` e os 6 tópicos separados por responsabilidade (`estufa/sensores/*`, `estufa/atuadores/*` e `estufa/status/*`). O uso explícito de `"127.0.0.1"` evita que o Windows 11 tente conectar primeiro em IPv6 (`::1`) causando atraso de ~1–2s em cada conexão.
- **Topologia do Cluster (`L23–L55`):** `MAPA_CONTROLADORES` associa números curtos (`1, 2, 3`) aos metadados `id` (`ctrl_1..ctrl_3`), `rank` (`1..3`), `host` (`127.0.0.1`), `port` (`8001..8003`) e `data_file` (`data_ctrl_1..3.json`). A função `obter_config_controlador` (`L34–L55`) valida e aceita tanto `1` quanto `"ctrl_1"` no CLI, rejeitando booleanos ou IDs fora do intervalo com `ValueError`.
- **Regras de Histerese e Timeouts (`L59–L67`):** `TEMP_MAX_CELSIUS = 35.0`, `TEMP_MIN_CELSIUS = 15.0`, `UMIDADE_MIN_PERCENT = 30.0`, `UMIDADE_MAX_PERCENT = 70.0`. `TIMEOUT_RPC_SEGUNDOS = 1.5`, `INTERVALO_HEARTBEAT_SEGUNDOS = 2.0` e `QUORUM_MINIMO = 2`.

---

### 2.2 `estufa/middleware.py` (`318` linhas) — Camada Lógica Distribuída
Não existe mais processo servidor intermediário (`:9000`). O `ClusterMiddleware` é importado diretamente por `cliente.py` e pelos controladores (`controlador.py`).

1. **Prevenção de Travamento TCP no Windows (`_TimeoutTransport`, `L23–L47`):**
   - Por padrão, `xmlrpc.client.ServerProxy` no Windows pode travar dezenas de segundos aguardando handshake/leitura em portas paradas ou semi-abertas. `_TimeoutTransport.make_connection` (`L30–L33`) injeta `conn.timeout = self._timeout` diretamente no socket HTTP subjacente.
   - `ClusterMiddleware.__init__` (`L85–L95`) define o timeout padrão do cliente como `config.TIMEOUT_RPC_SEGUNDOS * 2.5` (`3.75s`), pois uma chamada de comando (`comandar_bomba`/`comandar_exaustor`) dispara dentro do líder duas rodadas RPC paralelas entre pares (`coletar_voto_estado` + `commit_estado`).

2. **Normalização e Quórum Dinâmico (`_normalizar_estado` e `calcular_consenso`, `L110–L170`):**
   - `_normalizar_estado` (`L110–L134`) descarta campos voláteis (`ultima_atualizacao`, `lider_id`, `controlador_id`) e serializa em JSON ordenado apenas os 4 campos de domínio (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`).
   - `calcular_consenso` (`L137–L170`) conta as ocorrências com `collections.Counter` e aplica as regras por tamanho de quórum ativo:
     - **`>= 3` ativos (`L157`):** exige `votos >= 2`. Se 1 controlador for `--byzantino`, os 2 honestos vencem (`2/3`). Se todos os 3 divergirem, lança `ErroQuorum`.
     - **`2` ativos (`L161`):** exige concordância total (`votos == 2`). Se houver empate `1 vs 1` (ex.: 1 honesto + 1 bizantino com o terceiro caído), lança `ErroQuorum` porque não há desempate seguro.
     - **`1` ativo (`L166–L168`):** modo degradado (`1/1`) — o único controlador sobrevivente mantém o sistema disponível.
     - **`0` ativos (`L150–L151`):** lança `ErroQuorum`.

3. **Failover Transparente e Leitura Paralela (`_chamar_com_failover` e `obter_estado`, `L172–L260`):**
   - `_ordenar_candidatos` (`L172–L179`) coloca o último líder em cache (`self._lider_atual`) em primeiro lugar e ordena os demais do maior `rank` para o menor (`ctrl_3 -> ctrl_2 -> ctrl_1`).
   - `_chamar_com_failover` (`L194–L227`) tenta o próximo controlador automaticamente em qualquer `ConnectionRefusedError`, `TimeoutError`, `socket.timeout`, `OSError` ou `ProtocolError`, limpando `_lider_atual` se ele falhou. Caso receba um `xmlrpc.client.Fault` contendo `"ERRO_QUORUM"`, converte e propaga `ErroQuorum` imediatamente.
   - `obter_estado` (`L230–L260`) dispara chamadas paralelas (`ThreadPoolExecutor`) para todos os controladores alcançáveis com timeout limitado (`self._timeout + 0.3s`), aplica `calcular_consenso` e atualiza `_lider_atual`.
   - `comandar_bomba` / `comandar_exaustor` (`L262–L272`) validam estritamente `isinstance(ligar, bool)` antes de encaminhar ao cluster.

---

### 2.3 `estufa/controlador.py` (`911` linhas) — Núcleo Distribuído

1. **Concorrência e Prevenção de Deadlock (`L32–L36`, `L101–L147`):**
   - `_ThreadedXMLRPCServer` (`L32–L36`) combina `socketserver.ThreadingMixIn` com `SimpleXMLRPCServer`, `allow_reuse_address = True` e `daemon_threads = True`. Isso é essencial para que um controlador possa atender `ping()`, `coletar_voto_estado()` ou `anunciar_lider()` simultaneamente enquanto outra thread coordena consenso ou heartbeat, além de permitir reinício rápido na mesma porta sem `WinError 10048`.
   - **Regra de Lock (`L101–L102`):** `self._lock` (`RLock`) protege apenas acessos em memória e disco (`self._estado`, `self.lider_id`) e **nunca** é mantido durante chamadas XML-RPC externas. Sempre fazemos um snapshot sob lock, liberamos o lock, executamos o RPC em paralelo e readquirimos o lock para gravar.
   - `_salvar_estado` (`L179–L202`) escreve primeiro em um arquivo temporário por thread (`{data_file}.{tid}.tmp`) e faz substituição atômica via `os.replace` (com retry curto contra `PermissionError` transitório no Windows), evitando arquivos JSON vazios/truncados durante leituras concorrentes.

2. **Eleição de Líder — Algoritmo Valentão / Bully (`L208–L387`):**
   - Prioridade definida pelo `rank`: `ctrl_1 (1) < ctrl_2 (2) < ctrl_3 (3)`.
   - `ping()` (`L208–L216`): retorna `{"status": "ok", "id": ..., "rank": ..., "lider_id": ...}`.
   - `iniciar_eleicao(rank_origem)` (`L218–L228`): se `self.rank > rank_origem`, responde `{"aceito": True}` imediatamente e inicia `realizar_eleicao()` em thread daemon separada (sem bloquear o solicitante).
   - `anunciar_lider(novo_lider_id)` (`L237–L254`): valida que o anunciante não tem `rank` inferior ao próprio (`_obter_rank_id(lider_limpo) < self.rank`, `L243–L246`). Se um nó inferior tentar se anunciar líder enquanto um superior está vivo, o superior rejeita e dispara nova eleição Bully.
   - `realizar_eleicao()` (`L257–L341`): serializada por `self._eleicao_lock`. Consulta todos os pares de rank maior em paralelo (`L270–L295`). Se nenhum responder, assume `self.lider_id = self.ctrl_id`, persiste e envia `anunciar_lider` + `commit_estado` (se já houver estado inicializado e não for bizantino) para sincronizar imediatamente os pares (`L297–L322`). Se algum superior responder, aguarda brevemente (`0.25s`) e confirma o líder via `ping()` (`L324–L341`).
   - `_loop_heartbeat()` (`L352–L387`): a cada `INTERVALO_HEARTBEAT_SEGUNDOS` (`2.0s`), se o nó não for o líder, executa `ping()` no líder atual. Se houver falha de conexão, timeout ou resposta inválida, imprime `[HEARTBEAT]` e chama `realizar_eleicao()`.

3. **Recuperação de Réplica no Boot / Reconexão (`_sincronizar_com_cluster`, `L394–L482`):**
   - Na inicialização (`__init__`, `L151`), `self.lider_id` começa sempre como `None` (não confia em líder antigo salvo em disco antes da queda).
   - Em `iniciar_servidor_rpc()` (`L832–L848`), após subir o socket XML-RPC, o nó chama `_sincronizar_com_cluster()` antes de executar `realizar_eleicao()`.
   - `_sincronizar_com_cluster()` coleta `obter_estado()` de todos os pares alcançáveis em paralelo (`L405–L425`), filtra nós ainda não inicializados se já existir estado ativo (`L431–L440`), tenta `ClusterMiddleware.calcular_consenso` (`L443`) e, em caso de empate (ex.: 1 nó atualizado vs 1 nó em reinício ou bizantino), prioriza o nó que responde como líder ativo e possui `ultima_atualizacao` mais recente (`L454–L460`), gravando o banco JSON local antes de voltar a operar.

4. **Consenso Antes da Persistência e Publicação Exclusiva do Líder (`L489–L670`):**
   - `coletar_voto_estado(proposta)` (`L489–L537`): se `self.byzantino` for `True` (`L495–L502`), retorna valores adulterados (`temperatura=999.9, umidade=-50.0` e atuadores invertidos). Caso contrário, valida os limites físicos (`_validar_limites_sensor`) da proposta recebida e avalia as regras de histerese em `_avaliar_regras_atuacao` (`L58–L79`).
   - `_coordenar_consenso_e_persistir()` (`L578–L670`): executado apenas pelo Líder:
     1. Coleta o próprio voto e os votos de todos os pares ativos em paralelo (`L593–L618`).
     2. Apura o estado oficial via `ClusterMiddleware.calcular_consenso(votos)` (`L623`).
     3. Carimba `ultima_atualizacao` (UTC ISO-8601) e `lider_id = self.ctrl_id` (`L624–L625`).
     4. Grava localmente via `commit_estado` (`L627`) e envia `commit_estado` em paralelo para todos os seguidores alcançáveis (`L629–L648`), garantindo que `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json` fiquem idênticos.
     5. Somente se `self.eh_lider()` (`L650–L668`), publica o comando MQTT (`_publicar_comando`, `L567–L575`) quando há alteração de estado ou comando manual.

5. **Consumo MQTT e Comandos Manuais (`L677–L826`):**
   - `_on_connect` (`L677–L683`) assina `estufa/sensores/temperatura` e `estufa/sensores/umidade_solo` com `qos=1`.
   - `_on_message` (`L685–L727`) valida JSON e limites físicos; apenas o Líder dispara `_coordenar_consenso_e_persistir`, enquanto seguidores aguardam a votação/commit do Líder (sem escrever JSON divergente por conta própria!).
   - `_executar_comando_atuador` (`L747–L818`): se o cliente ou um failover chamar `comandar_bomba`/`comandar_exaustor` em um seguidor, o seguidor encaminha ao líder atual com timeout `self._timeout_rpc * 2.5` (`L763–L767`); se o líder caiu, dispara `realizar_eleicao()` imediatamente e executa/encaminha ao novo líder.

---

### 2.4 `estufa/cliente.py` (`130` linhas)
- Instancia `ClusterMiddleware()` diretamente (`L126`), sem qualquer referência à porta `9000`.
- `_executar_acao_segura` (`L41–L57`) captura `ErroQuorum`, `xmlrpc.client.Fault` e exceções de rede (`ConnectionRefusedError`, `TimeoutError`, `socket.timeout`, `OSError`) para que o terminal do cliente nunca feche quando o professor derruba controladores.
- `menu_interativo` (`L60–L105`) oferece consulta com consenso (`1`), acionamento direto (`2..5`) e diagnóstico de saúde + liderança atual do cluster (`6`).

---

### 2.5 `estufa/sensor.py` (`170` linhas)
- `SimuladorAmbiente` (`L27–L74`): valida temperatura inicial (`-50..100°C`) e umidade inicial (`0..100%`). Sem perfis estáticos: quando `exaustor_ligado=False`, a temperatura sobe (`+1.6..+2.6°C`); quando `True`, cai (`-3.5..-2.2°C`). Quando `bomba_ligada=False`, a umidade cai (`-4.0..-2.5%`); quando `True`, sobe (`+5.0..+7.5%`). Valores limitados a `[0, 55]°C` e `[0, 100]%`.
- `_on_connect` (`L78–L84`) e `_on_message` (`L88–L103`) são registrados **antes** de `client.connect()` (`L136–L138`) e assinam `estufa/status/bomba` e `estufa/status/exaustor` com `qos=1` para fechar a malha do simulador.
- `executar_sensor` (`L119–L156`) valida `intervalo > 0.05` e publica com `qos=1` e `wait_for_publish()` (`L114–L115`). CLI aceita `--temp`, `--umidade` e `--intervalo` (`L159–L170`).

---

### 2.6 `estufa/atuador.py` (`96` linhas)
- Removeu cache LRU e hash MD5 porque apenas o Líder publica após consenso.
- `_on_connect` (`L22–L28`) assina `estufa/atuadores/bomba` e `estufa/atuadores/exaustor` com `qos=1`.
- `_processar_atuador` (`L42–L63`) unifica bomba e exaustor, valida `"ligar"`/`"desligar"`, atualiza `_estado_bomba`/`_estado_exaustor` e chama `_publicar_status` (`L31–L39`) com `qos=1` para realimentar o sensor.

---

### 2.7 `estufa/broker_local.py` (`336` linhas)
- Servidor TCP MQTT v3.1.1 em Python puro (`127.0.0.1:1883`) sem necessidade de Docker ou Admin.
- Implementa codificação/decodificação varint limitada a 4 bytes (`L17–L44`), `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0` e `QoS 1`, liberando `wait_for_publish()` na linha `L290`), `PINGREQ/PINGRESP` e `DISCONNECT` (`L189–L308`).
- `executar_broker` (`L317–L328`) valida host e porta (`1..65535`) e, se a porta já estiver ocupada (`_porta_em_uso`, `L311–L314`), avisa e encerra imediatamente sem travar.

---

## 3. Perguntas Frequentes na Apresentação (Q&A)

1. **"Onde está o Middleware no diagrama de vocês?"**
   - Seguindo a Figura 1 do enunciado, o middleware não é um processo separado na porta `9000` (que seria um ponto único de falha). Ele é a camada lógica distribuída formada pelo `ClusterMiddleware` embarcado no cliente e pela comunicação P2P XML-RPC entre os próprios controladores (`8001..8003`).
2. **"Como o cliente sabe para quem enviar comandos se qualquer controlador pode cair?"**
   - O `ClusterMiddleware` conhece os 3 endpoints (`8001..8003`), mantém cache do último líder e ordena por rank (`ctrl_3 -> ctrl_2 -> ctrl_1`). Se o alvo cair ou der timeout, `_chamar_com_failover` migra automaticamente para o próximo nó vivo. Se cair em um seguidor, o próprio seguidor encaminha ao líder ou dispara nova eleição.
3. **"Por que não há divergência nos bancos locais mesmo se um nó perder mensagens ou for bizantino?"**
   - Nenhum controlador persiste leitura MQTT isoladamente. O líder coleta os votos de todos os nós ativos (`coletar_voto_estado`), apura o quórum em `calcular_consenso` (que descarta o voto adulterado do `--byzantino` pela maioria `2/3`) e só então envia `commit_estado` atômico para todas as réplicas gravarem exatamente o mesmo JSON.
4. **"O que acontece se eu fechar dois dos três controladores?"**
   - Ao fechar `ctrl_3`, `ctrl_2` vence a eleição Bully e o sistema opera em `2/2`. Ao fechar `ctrl_2`, `ctrl_1` assume liderança em modo degradado `1/1`, mantendo disponibilidade para o cliente e para a estufa. Quando `ctrl_2` e `ctrl_3` são religados, ambos puxam o estado atualizado via `_sincronizar_com_cluster` antes de retomar a liderança Bully.
5. **"E se houver 1 controlador honesto e 1 bizantino ao mesmo tempo (com o terceiro fechado)?"**
   - Com 2 nós ativos divergindo (`1 vs 1`), `calcular_consenso` detecta o empate sem maioria e lança `ErroQuorum`, recusando gravar ou confirmar estado corrompido até que a maioria seja restabelecida.
