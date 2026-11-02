# Guia Completo de Revisão e Defesa — Trabalho Prático 1 (Sistemas Distribuídos)

Este documento foi preparado para você ler **lado a lado com o código** antes da apresentação individual na bancada. Ele reconstrói toda a lógica do projeto do zero, explica cada arquivo linha por linha, detalha os dois fluxos de execução e antecipa as perguntas teóricas e práticas que o professor costuma fazer.

---

## 1. O Que é o Projeto (Resumo de 1 Minuto para Abrir a Apresentação)

> **Como explicar ao professor em 30 segundos:**
> *"O projeto implementa o sistema de controle automatizado de uma estufa agrícola distribuída. Temos sensores de temperatura e umidade do solo que publicam leituras continuamente via **MQTT** (modelo publicar/assinar). Três **Controladores replicados** (replicação ativa) consomem essas leituras de forma independente, avaliam regras de histerese e enviam comandos via MQTT para o **Atuador** (bomba de irrigação e exaustor), que usa um **cache LRU** para descartar comandos duplicados vindos das 3 réplicas. Para o usuário final (Cliente CLI) consultar o estado ou enviar comandos manuais, a comunicação é síncrona via **XML-RPC** passando obrigatoriamente por um **Servidor de Middleware** na porta 9000. Esse Middleware consulta os 3 controladores em paralelo (portas 8001 a 8003) e aplica **votação majoritária (quórum 2 de 3)**, mascarando tanto a queda de 1 controlador (falha por parada/crash) quanto 1 controlador retornando dados falsos (falha bizantina)."*

---

## 2. Mapa Conceitual: Teoria da Disciplina $\leftrightarrow$ Implementação no Código

Quando o professor perguntar *"Onde está o conceito X da disciplina no seu código?"*, use esta tabela:

| Conceito de Sistemas Distribuídos | Onde está implementado | Como funciona no projeto |
|---|---|---|
| **Comunicação Indireta (Pub/Sub)** | [`estufa/sensor.py`](estufa/sensor.py) e [`estufa/atuador.py`](estufa/atuador.py) | Desacoplamento espacial e temporal via broker MQTT (Mosquitto na porta `1883`) com `QoS = 1` (entrega *at-least-once*). |
| **Invocação Remota (RPC)** | [`estufa/middleware_server.py`](estufa/middleware_server.py), [`estufa/middleware.py`](estufa/middleware.py) e [`estufa/controlador.py`](estufa/controlador.py) | Chamadas síncronas cliente-servidor sobre HTTP/XML usando `SimpleXMLRPCServer` e `xmlrpc.client.ServerProxy`. |
| **Transparência de Acesso, Localização e Replicação** | [`estufa/cliente.py`](estufa/cliente.py) (linhas 19–21) | O cliente conhece apenas `http://localhost:9000` (Middleware). Ele não sabe que existem 3 réplicas nas portas `8001`, `8002` e `8003`. |
| **Replicação Ativa (*State Machine Replication*)** | [`estufa/controlador.py`](estufa/controlador.py) | Todas as 3 réplicas recebem os mesmos eventos MQTT dos sensores e executam a mesma máquina de estados deterministicamente. |
| **Tolerância a Falhas por Votação Majoritária (TMR)** | [`estufa/middleware.py`](estufa/middleware.py) (`_votar`, linhas 41–91) | *Triple Modular Redundancy* ($N = 2f + 1 = 3$). O Middleware chama as 3 réplicas em paralelo (`ThreadPoolExecutor`) e exige `QUORUM_MINIMO = 2` respostas idênticas. |
| **Transferência de Estado (*State Transfer*)** | [`estufa/controlador.py`](estufa/controlador.py) (`_sincronizar_estado_via_middleware`, linhas 74–105) | Quando uma réplica inicia ou volta de um *crash*, antes de assinar o MQTT ela pede `obter_estado()` ao Middleware para sincronizar seu JSON local com o quórum ativo. |
| **Idempotência / Deduplicação de Mensagens** | [`estufa/atuador.py`](estufa/atuador.py) (`_is_duplicado`, linhas 25–41) | Como 3 réplicas ativas publicam o mesmo comando no MQTT, o Atuador filtra o `comando_id` num cache LRU (`OrderedDict` de 50 posições), executando a ação física apenas 1 vez. |

---

## 3. Roteiro de Leitura do Código (Arquivo por Arquivo)

Abra os arquivos abaixo na ordem indicada para revisar toda a implementação em ~15 minutos.

### Passo 1: [`estufa/config.py`](estufa/config.py) (43 linhas)
É o arquivo mais simples e centraliza todas as constantes:
- **Linhas 9–19:** Configuração do Broker MQTT (`localhost:1883`) e os 6 tópicos MQTT:
  - Sensores: `estufa/sensores/temperatura` e `estufa/sensores/umidade_solo`
  - Comandos para atuadores: `estufa/atuadores/bomba` e `estufa/atuadores/exaustor`
  - Confirmação de status: `estufa/status/bomba` e `estufa/status/exaustor`
- **Linhas 22–26 (`CONTROLADORES`):** Lista com os 3 dicionários das réplicas (`ctrl_1` na `8001`, `ctrl_2` na `8002`, `ctrl_3` na `8003`) e o respectivo arquivo JSON de persistência de cada uma.
- **Linhas 29–30:** Endereço do Servidor de Middleware (`localhost:9000`).
- **Linhas 33–36 (Limiares com Histerese):**
  - Temperatura: acima de `35.0 °C` liga o exaustor; abaixo de `15.0 °C` desliga o exaustor.
  - Umidade do solo: abaixo de `30.0 %` liga a bomba; acima de `70.0 %` desliga a bomba.
- **Linhas 39–43:** `TIMEOUT_RPC_SEGUNDOS = 3`, `QUORUM_MINIMO = 2` e `DEDUP_CACHE_SIZE = 50`.

---

### Passo 2: [`estufa/sensor.py`](estufa/sensor.py) (91 linhas)
Simula os sensores físicos publicando no MQTT a cada 2 segundos:
- **Linhas 24–29 (`PERFIS`):** Permite rodar o sensor em 4 modos via linha de comando (`--modo normal`, `seco`, `quente`, `frio`). Por exemplo, `--modo seco` sorteia umidade entre 10% e 29% (forçando os controladores a ligarem a bomba), e `--modo quente` sorteia temperatura entre 36°C e 42°C (forçando os controladores a ligarem o exaustor).
- **Linhas 39–48 (`publicar_leitura`):** Monta o JSON com `"valor"`, `"unidade"` e `"timestamp": time.time()`.
  - **Ponto-chave para a defesa:** Esse campo `"timestamp"` gerado pelo sensor é crucial! Quando o broker entrega essa mensagem para os 3 controladores, todos os 3 recebem **exatamente o mesmo número de `timestamp`**. É graças a ele que os 3 controladores conseguem calcular o mesmo hash MD5 sem precisarem conversar entre si.
- **Linhas 60–81 (`executar_sensor`):** Usa `client.loop_start()` (que cria uma thread de rede interna do `paho-mqtt`) e, no `while True`, publica temperatura e umidade com `qos=1`.

---

### Passo 3: [`estufa/controlador.py`](estufa/controlador.py) (319 linhas)
É o coração do trabalho. Cada instância desse script representa uma réplica (`ctrl_1`, `ctrl_2` ou `ctrl_3`).

1. **Estado e Concorrência (linhas 29–55):**
   - `self._estado` guarda `temperatura`, `umidade_solo`, `bomba_ligada`, `exaustor_ligado`, `ultima_atualizacao`, `sensor_timestamp` e `controlador_id`.
   - **Por que existe `self._lock = threading.Lock()` na linha 50?**
     Porque cada controlador roda **duas threads simultâneas**:
     1. A thread do servidor XML-RPC (`server_thread`, linha 288), que lê/altera `self._estado` quando o Middleware chama `obter_estado` ou `comandar_bomba`.
     2. A thread do cliente MQTT (`loop_forever`, linha 305), que altera `self._estado` quando chega mensagem de sensor em `_on_message` (linha 173).
     O `with self._lock:` evita condição de corrida (*race condition*) na memória e na escrita do arquivo JSON.

2. **Sequência de Boot e Transferência de Estado (linhas 74–105 e 265–305):**
   - Olhe o método `iniciar()` na **linha 265**:
     - **Etapa 1 (linhas 276–289):** Sobe o `SimpleXMLRPCServer` na porta da réplica (`8001`, `8002` ou `8003`) em uma thread *daemon*.
     - **Etapa 2 (linhas 291–294):** Chama `_sincronizar_estado_via_middleware()`.
     - **Etapa 3 (linhas 296–305):** Conecta ao Broker MQTT e entra em `loop_forever()`.
   - **Por que a Etapa 2 vem antes do MQTT?**
     Se o `ctrl_3` caiu, enquanto ele estava fora a bomba pode ter sido ligada manualmente pelo cliente. Quando o `ctrl_3` reinicia, o arquivo `data_ctrl_3.json` dele está desatualizado (`bomba_ligada: False`). Então, antes de começar a operar, ele chama `proxy.obter_estado()` no Middleware (`:9000`), recebe o estado vencedor do quórum (`ctrl_1` e `ctrl_2`) e sobrescreve seu estado local (**linhas 84–91**).
   - **E no primeiro boot de todos, quando as réplicas estão subindo?**
     Por isso o `ctrl_1` sobe seu XML-RPC primeiro (Etapa 1) e tenta sincronizar com o Middleware até 10 vezes (`max_tentativas=10`). Assim que pelo menos 2 réplicas já subiram o XML-RPC (Etapa 1), o Middleware consegue formar quórum 2/3 e libera a sincronização!

3. **Lógica de Decisão Autônoma e Hash Determinístico (linhas 107–144):**
   - Em `_decidir_atuacao()`, o controlador verifica os limiares com **histerese**:
     - Linha 122: Só manda ligar o exaustor se `temp > 35.0` **e** `not self._estado["exaustor_ligado"]` (evita mandar ligar repetidamente se já estiver ligado).
     - Linha 127: Só manda desligar se `temp < 15.0` **e** `self._estado["exaustor_ligado"]`.
   - **Geração do `comando_id` determinístico (linhas 117–119):**
     ```python
     def gerar_comando_id(acao_alvo: str) -> str:
         raw = f"{acao_alvo}_{sensor_ts}"
         return hashlib.md5(raw.encode("utf-8")).hexdigest()
     ```
     Como `acao_alvo` (ex.: `"bomba_ligar"`) e `sensor_ts` (o timestamp que veio no JSON do sensor) são iguais nos 3 controladores, os 3 geram **exatamente o mesmo MD5**.

4. **Métodos XML-RPC e Simulação de Falha Bizantina (linhas 186–263):**
   - `obter_estado()` (linhas 186–199): Se `self.byzantino` for `False`, devolve `dict(self._estado)`. Se for `True` (`--byzantino`), devolve `temperatura: 999.0`, `umidade_solo: -1.0` e inverte os booleanos `bomba_ligada` e `exaustor_ligado`.
   - `comandar_bomba(acao, comando_id)` (linhas 201–229) e `comandar_exaustor(acao, comando_id)` (linhas 231–259):
     - Nas réplicas honestas: atualiza `self._estado`, publica no MQTT repassando o `comando_id` recebido do Middleware, salva no JSON e retorna:
       `{"sucesso": True, "mensagem": "Bomba ligada com sucesso", "controlador_id": self.ctrl_id}`.
     - Na réplica bizantina (`if self.byzantino`, linhas 211–217): **não altera o estado nem publica no MQTT**, e retorna a mensagem com a ação oposta (`"Bomba desligada com sucesso"` quando o pedido foi `"ligar"`), simulando uma réplica defeituosa/maliciosa.

---

### Passo 4: [`estufa/middleware.py`](estufa/middleware.py) (119 linhas) e [`estufa/middleware_server.py`](estufa/middleware_server.py) (93 linhas)

- **Por que são dois arquivos?**
  - [`estufa/middleware_server.py`](estufa/middleware_server.py) sobe o servidor HTTP/XML-RPC na porta `9000` (`SimpleXMLRPCServer`) e registra a classe `MiddlewareService`. Quando ocorre `ErroQuorum`, ele lança uma exceção que o protocolo XML-RPC serializa como `xmlrpc.client.Fault` para o cliente.
  - [`estufa/middleware.py`](estufa/middleware.py) contém a classe `Middleware` com o algoritmo de votação puro, sem depender de abrir porta de rede (o que permite testar toda a lógica de quórum com *mocks*).

- **Como funciona `Middleware._votar(metodo, *args)` ([`estufa/middleware.py`](estufa/middleware.py), linhas 41–91):**
  1. **Chamada Paralela (linhas 49–61):** Cria um `ThreadPoolExecutor` com 3 *workers* e dispara `_chamar_controlador` para `ctrl_1`, `ctrl_2` e `ctrl_3` simultaneamente. Se um controlador estiver desligado (*crash*) ou demorar mais que `TIMEOUT_RPC_SEGUNDOS` (3s), a exceção é capturada no `except` (linha 59), registrada em `erros` e as demais respostas seguem normalmente.
  2. **Normalização (`_normalizar`, linhas 69–76):**
     ```python
     def _normalizar(valor: Any) -> str:
         if isinstance(valor, dict):
             copia = {
                 k: v for k, v in valor.items()
                 if k not in ("ultima_atualizacao", "controlador_id")
             }
             return json.dumps(copia, sort_keys=True)
         return str(valor)
     ```
     **Por que `_normalizar` existe?** Porque cada réplica grava seu próprio `controlador_id` (`"ctrl_1"`, `"ctrl_2"`, `"ctrl_3"`) e o instante exato (`ultima_atualizacao` via `time.time()`, que varia em microssegundos de um processo para outro). Removendo apenas esses dois metadados de instância e ordenando as chaves com `sort_keys=True`, duas réplicas honestas produzem **strings JSON idênticas**.
  3. **Apuração de Votos (linhas 78–91):**
     - `collections.Counter` conta quantas vezes cada JSON normalizado apareceu.
     - `mais_comum, votos = contagem.most_common(1)[0]` pega a resposta mais votada.
     - Se `votos < config.QUORUM_MINIMO` (isto é, menos de 2 votos concordantes), lança `ErroQuorum`.
     - Se `votos >= 2`, retorna o dicionário original correspondente ao voto vencedor.

- **Deduplicação em Comandos Manuais (linhas 97–107):**
  - Em `comandar_bomba` e `comandar_exaustor`, o Middleware gera **um único `uuid.uuid4()`** antes de chamar `self._votar(...)` e passa esse `comando_id` para os 3 controladores. Assim, os 3 controladores publicam no MQTT com o mesmo UUID.

---

### Passo 5: [`estufa/atuador.py`](estufa/atuador.py) (118 linhas)
Subscreve aos tópicos `estufa/atuadores/bomba` e `estufa/atuadores/exaustor`:
- **Cache LRU com `OrderedDict` (`_is_duplicado`, linhas 25–41):**
  - Na linha 22: `_dedup_cache = collections.OrderedDict()`.
  - Quando chega uma mensagem MQTT em `_on_message` (linha 88), extrai `comando_id = payload.get("comando_id", "")`.
  - Se `comando_id` **já está** em `_dedup_cache` (linha 33): chama `_dedup_cache.move_to_end(comando_id)` (marca como usado recentemente) e retorna `True` $\rightarrow$ o atuador imprime `"Comando duplicado descartado"` e ignora!
  - Se `comando_id` **não está** no cache (linha 37): insere no fim (`_dedup_cache[comando_id] = True`). Se o tamanho passar de `DEDUP_CACHE_SIZE` (50), remove o item mais antigo do início da fila com `_dedup_cache.popitem(last=False)` (linha 39) e retorna `False` $\rightarrow$ o atuador executa a ação e publica o status em `estufa/status/...`.

---

### Passo 6: [`estufa/cliente.py`](estufa/cliente.py) (134 linhas)
Interface CLI para o operador:
- Instancia `xmlrpc.client.ServerProxy("http://localhost:9000", allow_none=True)` (linhas 19–21).
- Tem dois modos de operação:
  1. **Menu interativo** (padrão, linhas 42–100): opções `1` a `6` para consultar estado, ligar/desligar bomba e exaustor, e verificar saúde (`verificar_saude`, que chama `ping()` em cada controlador).
  2. **Modo automático** (`--auto`, linhas 103–117): faz *polling* de `obter_estado()` a cada 3 segundos.

---

## 4. Os Dois Fluxos de Ponta a Ponta (Para Explicar Sem Hesitar)

### Fluxo A: Acionamento Autônomo (Via Sensor $\rightarrow$ MQTT)
1. **Sensor** (`sensor.py`) publica no tópico `estufa/sensores/temperatura`: `{"valor": 38.5, "unidade": "°C", "timestamp": 1700000100.25}`.
2. **Broker Mosquitto** entrega cópia dessa mensagem para `ctrl_1`, `ctrl_2` e `ctrl_3`.
3. **Cada Controlador** (`controlador.py`, `_on_message` $\rightarrow$ `_decidir_atuacao`) vê que `38.5 > 35.0` e que o exaustor está desligado.
4. **Cada Controlador** calcula `MD5("exaustor_ligar_1700000100.25")` $\rightarrow$ todos os 3 obtêm o mesmo hash (ex.: `a1b2c3d4...`) e publicam em `estufa/atuadores/exaustor`.
5. **Atuador** (`atuador.py`) recebe as 3 mensagens do broker:
   - Na 1ª (ex.: do `ctrl_1`): `a1b2c3d4...` não está no `_dedup_cache` $\rightarrow$ **liga o exaustor** e guarda no cache.
   - Na 2ª e 3ª (do `ctrl_2` e `ctrl_3`): `a1b2c3d4...` já está no `_dedup_cache` $\rightarrow$ **descarta silenciosamente**.

### Fluxo B: Acionamento Manual (Via Cliente $\rightarrow$ XML-RPC $\rightarrow$ MQTT)
1. **Cliente** (`cliente.py`) escolhe a opção `2` (Ligar bomba) $\rightarrow$ chama `proxy.comandar_bomba("ligar")` na porta `9000`.
2. **Middleware** (`middleware_server.py` $\rightarrow$ `middleware.py`) gera **um único UUID4** (ex.: `f47ac10b-...`) e chama em paralelo `comandar_bomba("ligar", "f47ac10b-...")` nas portas `8001`, `8002` e `8003`.
3. **Cada Controlador honesto** atualiza seu JSON, publica no tópico MQTT `estufa/atuadores/bomba` usando o `comando_id = "f47ac10b-..."` e retorna via XML-RPC: `{"sucesso": True, "mensagem": "Bomba ligada com sucesso", "controlador_id": "ctrl_X"}`.
4. **Atuador** recebe as publicações MQTT com `f47ac10b-...`, executa a primeira e descarta as demais pelo cache LRU.
5. **Middleware** normaliza as respostas XML-RPC (removendo `controlador_id`), contabiliza os votos (`>= 2` votos para `"Bomba ligada com sucesso"`) e devolve o resultado aprovado para o **Cliente**.

---

## 5. Como Funcionam os Testes Automatizados (`tests/`)

Se o professor pedir para rodar os testes (`pytest tests/ -v`) ou perguntar como eles funcionam sem precisar subir o Docker:

1. **[`tests/test_atuador.py`](tests/test_atuador.py) (7 testes):**
   - Importa diretamente `_is_duplicado` e `_dedup_cache` de `estufa.atuador`.
   - Usa uma *fixture* `limpar_cache` (`autouse=True`) que limpa o `OrderedDict` antes de cada teste.
   - Testa: ID inédito retorna `False`; mesmo ID na 2ª chamada retorna `True`; preenchimento de 50 itens + inserção do 51º item remove o `uuid-0000` (evicção FIFO/LRU); acesso a `uuid-0000` antes de inserir o 51º item usa `move_to_end` e preserva `uuid-0000` (removendo `uuid-0001`).
2. **[`tests/test_controlador.py`](tests/test_controlador.py) (29 testes):**
   - Usa a fixture nativa `tmp_path` do `pytest` para criar arquivos JSON temporários isolados em cada teste.
   - Injeta leituras diretamente em `ctrl._estado` (`_injetar_sensor`) e substitui `ctrl._publicar_comando` por uma *lambda* em memória para verificar que as 3 réplicas geram exatamente o mesmo hash MD5, respeitam a histerese e persistem o JSON.
   - Em `TestModoByantino`, verifica que um controlador com `byzantino=True` retorna `temperatura=999.0` e estados invertidos em `obter_estado()`, e retorna a mensagem oposta em `comandar_bomba`/`comandar_exaustor` sem alterar `self._estado`.
3. **[`tests/test_middleware.py`](tests/test_middleware.py) (15 testes):**
   - Usa `unittest.mock.patch.object(middleware, "_criar_proxy", ...)` para interceptar as chamadas XML-RPC sem abrir conexão de rede.
   - Testa: quórum 3/3 com `controlador_id` distintos; quórum 2/3 quando 1 controlador lança `ConnectionRefusedError`; `ErroQuorum` quando todos caem ou quando os 3 divergem; mascaramento de 1 controlador bizantino tanto em `obter_estado` quanto em `comandar_bomba`; e geração de UUID compartilhado entre as 3 réplicas na mesma chamada.

---

## 6. O Que Está no Relatório Técnico ([`relatorio/relatorio.md`](relatorio/relatorio.md))

O relatório segue uma estrutura acadêmica direta em 9 seções que espelha exatamente o código:
- **Seções 1 e 2:** Motivação e Arquitetura Híbrida (MQTT para fluxo contínuo de sensores/atuadores + XML-RPC para controle e leitura com quórum).
- **Seção 3:** Replicação Ativa e os 5 passos da Transferência de Estado (*State Transfer*) no boot dos controladores.
- **Seção 4:** Tolerância a Falhas por Parada (*Crash*) com quórum 2/3 e recuperação de réplicas.
- **Seção 5:** Tolerância a Falhas Bizantinas via Mascaramento por Votação Majoritária (TMR, $N = 2f + 1 = 3$) e explicação da função `_normalizar()`.
- **Seção 6:** Deduplicação no Atuador combinando hash MD5 determinístico (eventos de sensores) + UUID4 (comandos manuais) + Cache LRU.
- **Seções 7, 8 e 9:** Tabela de parâmetros (`config.py`), resumo da suíte de testes (`pytest`) e conclusão relacionando os conceitos da disciplina.

---

## 7. Perguntas Clássicas do Professor na Bancada (e Como Responder)

### P1: *"Por que você usou 3 réplicas ($2f+1$) para tolerar 1 falha bizantina? O problema dos Generais Bizantinos não exige $3f+1 = 4$ réplicas?"*
> **Resposta:** *"O limite $3f+1 = 4$ se aplica ao consenso bizantino distribuído entre pares (como PBFT), onde os próprios nós trocam mensagens entre si sem um votador confiável para chegar a um acordo. Aqui nós implementamos o modelo de **Mascaramento de Falhas por Votação Majoritária (TMR — Triple Modular Redundancy)**: os sensores entregam os mesmos dados para as 3 réplicas via broker, e o **Middleware atua como um votador confiável** que compara as respostas recebidas. Em um votador majoritário, para superar $f=1$ resposta falsa, bastam $2f+1 = 3$ réplicas (2 votos honestos contra 1 voto bizantino)."*

### P2: *"Por que o sistema usa MQTT e XML-RPC juntos em vez de usar só um deles?"*
> **Resposta:** *"Para aplicar o paradigma mais adequado à natureza de cada comunicação. A leitura de sensores é um fluxo contínuo de telemetria de 1-para-N (1 sensor para 3 controladores), onde o modelo publicar/assinar assíncrono do **MQTT** evita acoplamento: o sensor publica no tópico sem precisar saber quantos controladores existem ou em quais portas estão. Já a interação do Cliente com o Middleware e do Middleware com os Controladores é do tipo requisição-resposta imediata (consulta de estado ou comando com confirmação de quórum), cenário em que a chamada síncrona de procedimento remoto (**XML-RPC**) é muito mais direta."*

### P3: *"Se os 3 controladores tomam decisão sozinhos quando chega mensagem MQTT do sensor, onde entra a tolerância a falhas na decisão autônoma?"*
> **Resposta:** *"Na decisão autônoma ela ocorre por **replicação ativa**: como todos os 3 controladores assinam o broker MQTT, se 1 controlador sofrer crash, os outros 2 continuam recebendo as leituras do sensor e publicando o comando para o atuador. E enquanto os 3 estão vivos, o atuador filtra as 2 mensagens repetidas usando o cache LRU baseado no hash MD5 do timestamp do sensor."*

### P4: *"E se um controlador em modo `--byzantino` publicar comandos falsos direto no MQTT quando ler um sensor?"*
> **Resposta:** *"No nosso escopo, o modo `--byzantino` foi modelado na interface XML-RPC (`obter_estado`, `comandar_bomba` e `comandar_exaustor`) para demonstrar o motor de votação majoritária do Middleware. Se quiséssemos impedir que um controlador bizantino publicasse comandos autônomos falsos direto no MQTT, o Atuador também precisaria aguardar 2 mensagens concordantes (votação no atuador) antes de acionar o pino físico, ou toda atuação precisaria passar pelo votador do Middleware."* (Excelente resposta caso ele explore limites arquiteturais!).

### P5: *"Como você garante que dois comandos iguais enviados em momentos diferentes não sejam descartados como duplicados pelo atuador?"*
> **Resposta:** *"Porque o `comando_id` nunca depende apenas do nome da ação:
> 1. No modo manual, o Middleware gera um `uuid.uuid4()` novo a cada clique do usuário (`middleware.py`, linhas 99 e 105).
> 2. No modo autônomo, o controlador concatena a ação com o `sensor_timestamp` (`f'{acao}_{sensor_ts}'`, `controlador.py`, linha 118). Uma leitura futura terá outro timestamp e, portanto, outro hash MD5."*

---

## 8. Roteiro Rápido para Demonstração Prática ao Vivo

Se o professor pedir para ver funcionando na hora:

1. **Mostrar os testes unitários passando (leva 0.1s):**
   ```bash
   pytest tests/ -v
   ```
2. **Subir o sistema completo:**
   ```bash
   bash scripts/start_all.sh
   # E abrir o cliente:
   python3 -m estufa.cliente
   ```
3. **Demonstrar Tolerância a Crash (Quórum 2/3) e *State Transfer*:**
   - No cliente, digite `6` (Verificar saúde): mostrará `ctrl_1: ok`, `ctrl_2: ok`, `ctrl_3: ok`.
   - Mate o processo do `ctrl_3` (ou feche o terminal dele).
   - No cliente, digite `6`: mostrará `ctrl_3: OFFLINE`.
   - No cliente, digite `2` (Ligar bomba): o Middleware mostrará nos logs que `ctrl_3` falhou, mas o quórum 2/3 foi atingido com `ctrl_1` e `ctrl_2`, e a bomba ligará normalmente!
   - Suba o `ctrl_3` novamente:
     ```bash
     python3 -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
     ```
     Mostre no log do `ctrl_3` a mensagem: `[ctrl_3] Estado sincronizado na tentativa 1/10 (Bomba=True...)` — provando o *State Transfer*!
4. **Demonstrar Tolerância a Falha Bizantina:**
   - Pare o `ctrl_2` e suba-o com `--byzantino`:
     ```bash
     python3 -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
     ```
   - No cliente, digite `1` (Consultar estado) ou `2` (Ligar bomba): mostre no log do Middleware que houve `2` votos para o estado honesto e `1` voto para o estado adulterado (`999.0 °C`), e que o cliente recebeu o valor honesto!
