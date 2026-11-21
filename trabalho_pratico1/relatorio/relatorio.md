# Relatório Técnico — Trabalho Prático 1: Sistemas Distribuídos
## Controle Automatizado de Estufa Agrícola com Middleware Distribuído, Eleição Bully e Consenso Replicado

**Disciplina:** Sistemas Distribuídos  
**Tema:** Controle Automatizado de Estufa Agrícola  
**Tecnologias:** Python 3.10+, MQTT v3.1.1 (QoS 1), XML-RPC  
**Modelos Aplicados:** Publicar/Assinar, RPC Direto, Eleição de Líder (Bully), Consenso com Quórum Dinâmico, Persistência Replicada Síncrona e Tolerância a Falhas Bizantinas

---

## 1. Introdução e Arquitetura

Este trabalho apresenta a implementação de um sistema distribuído tolerante a falhas para monitoramento e controle ambiental de uma estufa agrícola. Leituras contínuas de temperatura e umidade do solo são publicadas via MQTT para um cluster de 3 controladores de processo que elegem dinamicamente um líder, validam o estado oficial por consenso antes da persistência nos bancos locais replicados (`data_ctrl_1..3.json`) e acionam bomba de irrigação e exaustor em malha fechada.

### 1.1 Organização da Arquitetura Distribuída

A arquitetura é estruturada em três camadas integradas:

- **Comunicação indireta (MQTT QoS 1):** Sensor, controladores e atuador interagem por publicação e assinatura no broker MQTT (`127.0.0.1:1883`).
- **Camada Middleware (XML-RPC Direto e P2P):** Composta pelos 3 controladores (`127.0.0.1:8001..8003`) e pelo módulo `ClusterMiddleware`, permitindo invocação direta pelo cliente com descoberta de líder e failover automático.
- **Coordenação autônoma entre réplicas:** Os controladores comunicam-se via XML-RPC P2P para detecção de falhas por heartbeat, eleição de líder (Algoritmo Bully), votação de consenso e replicação síncrona de estado (`commit_estado`).

---

## 2. Componentes do Sistema (7 Processos)

```text
[Cliente CLI] <--- XML-RPC Direto (Failover) ---> +---------------------------------------+
                                                  | MIDDLEWARE (Controladores 8001..8003) |
                                                  |  ctrl_1 <-> ctrl_2 <-> ctrl_3 (Líder) |
                                                  |    |          |          |            |
                                                  |  JSON 1     JSON 2     JSON 3         |
                                                  +-------------------+-------------------+
                                                                      |
                                                         MQTT QoS 1 (:1883)
                                                                      |
                                                  [Sensor Contínuo] <---> [Broker] <---> [Atuador]
```

| Componente | Módulo | Porta | Responsabilidade |
|---|---|---|---|
| **Broker MQTT** | `estufa/broker_local.py` | `127.0.0.1:1883` | Broker MQTT v3.1.1 local (QoS 0 e 1) |
| **Controladores (×3)** | `estufa/controlador.py` | `8001`, `8002`, `8003` | Eleição Bully, consenso P2P, commit JSON replicado e atuação do Líder |
| **Camada Middleware** | `estufa/middleware.py` | embarcado | Proxy RPC com timeout explícito, failover do cliente e cálculo de quórum |
| **Sensor Contínuo** | `estufa/sensor.py` | — | Simulação determinística em malha fechada (`+2.0/-2.5°C` e `-3.0/+6.0%`) reativa aos atuadores |
| **Atuador** | `estufa/atuador.py` | — | Acionamento de bomba/exaustor e publicação de status QoS 1 |
| **Cliente CLI** | `estufa/cliente.py` | — | Interface interativa de consulta e comando direto ao cluster |

---

## 3. Liderança Dinâmica (Algoritmo Bully) e Failover

Cada controlador possui um identificador e prioridade numérica (`ctrl_1: rank=1`, `ctrl_2: rank=2`, `ctrl_3: rank=3`):

1. **Eleição no boot e sob falha (`realizar_eleicao`):** O controlador consulta sequencialmente os pares com `rank` superior via `iniciar_eleicao(rank)`. Se nenhum responder, assume a liderança (`lider_id = self.ctrl_id`), persiste o estado e anuncia `anunciar_lider` + `commit_estado` aos demais nós.
2. **Guarda de Rank (`anunciar_lider`):** Se um nó de rank inferior tentar se anunciar enquanto um nó superior está ativo, o nó superior recusa e inicia nova eleição Bully.
3. **Detecção de falha (`_loop_heartbeat`):** A cada `2.0s` (`INTERVALO_HEARTBEAT_SEGUNDOS`), os seguidores verificam o líder via `ping()`. Caso o líder caia, uma nova eleição promove automaticamente o próximo nó vivo de maior rank (`ctrl_3 -> ctrl_2 -> ctrl_1`).
4. **Transparência no Cliente (`ClusterMiddleware._chamar_com_failover`):** Se o nó contatado pelo cliente cair ou sofrer timeout, o cliente tenta o próximo controlador da lista automaticamente; se um seguidor receber o comando, encaminha-o ao líder atual.

---

## 4. Consenso Dinâmico e Persistência Replicada

Para impedir divergência entre `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`:

1. **Validação antes da persistência:** Ao receber leitura MQTT de sensor ou comando manual RPC, os controladores **não** alteram nem gravam o estado em disco de forma isolada. O Líder coleta os votos das réplicas ativas (`coletar_voto_estado`), onde cada nó avalia independentemente as regras de histerese.
2. **Quórum dinâmico sobre nós ativos (`ClusterMiddleware.calcular_consenso`):**
   - **3 ativos:** exige maioria ($\ge 2/3$), mascarando até $f = 1$ controlador em falha bizantina (`--byzantino`).
   - **2 ativos:** exige concordância ($2/2$); qualquer divergência (`1 vs 1`) dispara `ErroQuorum` e aborta a gravação.
   - **1 ativo:** modo degradado ($1/1$), mantendo a disponibilidade da estufa mesmo após duas quedas consecutivas.
3. **Commit síncrono e publicação única:** Definido o estado oficial, o Líder executa `commit_estado` síncrono em si e nos seguidores alcançáveis (persistência JSON protegida por `RLock`) e **somente o Líder** publica o comando no tópico MQTT do atuador.
4. **Ressincronização ao reconectar (`_sincronizar_com_cluster`):** Ao subir novamente após queda, o controlador consulta os pares ativos, valida o estado oficial via `ClusterMiddleware.calcular_consenso()`, atualiza seu banco JSON local e só então retoma sua posição na eleição Bully.

---

## 5. Tolerância a Falhas Bizantinas (`--byzantino`)

Ao iniciar um controlador com `python -m estufa.controlador 2 --byzantino`, ele retorna valores adulterados (`temperatura = 999.9`, `umidade = -50.0` e estados booleanos invertidos) em `coletar_voto_estado()` e `obter_estado()`. Com 3 nós ativos, a maioria `2/3` formada por `ctrl_1` e `ctrl_3` rejeita o voto adulterado antes do `commit_estado`, mantendo os bancos locais honestos íntegros e exibindo ao cliente somente os valores corretos. Caso `ctrl_1` também seja encerrado, restando apenas `ctrl_2 --byzantino` e `ctrl_3` honesto, o empate `1 vs 1` dispara `ErroQuorum` com segurança.

---

## 6. Parâmetros de Configuração (`estufa/config.py`)

| Parâmetro | Valor Padrão | Descrição |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1:1883` | Endereço do broker MQTT local |
| `MAPA_CONTROLADORES` | `1..3 -> 8001..8003` | Portas XML-RPC, ranks Bully e arquivos JSON replicados |
| `TEMP_MAX_CELSIUS` / `TEMP_MIN_CELSIUS` | `35.0 °C` / `15.0 °C` | Faixa de histerese do exaustor |
| `UMIDADE_MIN_PERCENT` / `UMIDADE_MAX_PERCENT` | `30.0 %` / `70.0 %` | Faixa de histerese da bomba de irrigação |
| `TIMEOUT_RPC_SEGUNDOS` | `0.6 s` | Timeout de socket XML-RPC entre pares (`1.5s` no cliente) |
| `INTERVALO_HEARTBEAT_SEGUNDOS` | `2.0 s` | Intervalo de verificação do líder pelos seguidores |

---

## 7. Validação Automatizada

A suíte automatizada cobre testes unitários, de integração em portas locais e End-to-End com subprocessos reais:

- `tests/` (`34` testes via `pytest`): valida sensor em malha fechada, atuador, broker MQTT local, camada `ClusterMiddleware`, eleição Bully, consenso, failover `3 -> 2 -> 1`, mascaramento bizantino e ressincronização de réplica.
- `scripts/validate_e2e.py`: sobe os processos reais em `127.0.0.1` e valida todas as 6 etapas da arquitetura, limpando os arquivos JSON temporários ao final.

---

## 8. Conclusão

A combinação da eleição de líder via algoritmo Bully, da validação por consenso com quórum dinâmico antes da persistência e da ressincronização automática na reconexão garante disponibilidade contínua e consistência entre as réplicas diante de quedas sequenciais e falhas bizantinas.
