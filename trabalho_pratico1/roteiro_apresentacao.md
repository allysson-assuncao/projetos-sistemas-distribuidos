# Roteiro de Execução e Cenários de Teste — TP1

> Comandos de inicialização dos processos e cenários práticos de operação e tolerância a falhas do sistema.

---

## 1. Inicialização dos Terminais

Todos os comandos abaixo devem ser executados a partir do diretório `trabalho_pratico1/`:

```bash
cd trabalho_pratico1
```

### 1.1 Opção A — Automática (6 Janelas Independentes + Cliente)

```powershell
# 1. Limpar processos antigos e bancos JSON residuais
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/reset_demo.ps1

# 2. Subir os 6 serviços em janelas separadas
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/start_all.ps1

# 3. No terminal principal, iniciar o Cliente CLI (7º processo)
./.venv/Scripts/python.exe -m estufa.cliente
```

### 1.2 Opção B — Manual Agrupada nos Terminais Integrados do VS Code

Para organizar os terminais em grupos divididos (*Split Terminal* — `Ctrl+Shift+5`) dentro do próprio VS Code (ou via `Ctrl+Shift+B` → **Subir Todo o Sistema (Estufa TP1 - 7 Terminais)**):

#### Grupo 1 — Infraestrutura e Camada IoT (3 divisões lado a lado)

**Terminal 1 — Broker MQTT (`:1883`):**
```bash
./.venv/Scripts/python.exe -u -m estufa.broker_local
```

**Terminal 2 — Atuador (Bomba / Exaustor):**
```bash
./.venv/Scripts/python.exe -u -m estufa.atuador
```

**Terminal 3 — Sensor Contínuo:**
```bash
./.venv/Scripts/python.exe -u -m estufa.sensor --temp 28 --umidade 42 --intervalo 2
```

#### Grupo 2 — Cluster de Controladores (3 divisões lado a lado)

**Terminal 4 — Controlador 1 (`:8001` | `rank=1`):**
```bash
./.venv/Scripts/python.exe -u -m estufa.controlador 1
```

**Terminal 5 — Controlador 2 (`:8002` | `rank=2`):**
```bash
./.venv/Scripts/python.exe -u -m estufa.controlador 2
```

**Terminal 6 — Controlador 3 (`:8003` | `rank=3` | Líder padrão):**
```bash
./.venv/Scripts/python.exe -u -m estufa.controlador 3
```

#### Grupo 3 — Interação e Monitoramento

**Terminal 7 — Cliente CLI (RPC Direto):**
```bash
./.venv/Scripts/python.exe -m estufa.cliente
```

---

## 2. Cenários de Operação e Tolerância a Falhas

### Passo 1 — Cluster Saudável (3/3), Eleição Inicial e Replicação
- **Execução:** Aguardar ~4s após subir os terminais; no Cliente, executar opção `6` (Saúde) e opção `1` (Consultar estado). Verificar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`realizar_eleicao`, `L241–L302`; `commit_estado`, `L452–L476`).
- **Explicação:** Na inicialização, o algoritmo Bully elege `ctrl_3` (maior `rank`) como líder do cluster e os 3 bancos JSON gravam exatamente os mesmos valores via `commit_estado` síncrono após o consenso.

### Passo 2 — Alteração de Parâmetros do Sensor (Malha Fechada Autônoma)
- **Execução:** No terminal do **Sensor**, interromper com `Ctrl+C` e reiniciar com valores fora da faixa ideal:
  `./.venv/Scripts/python.exe -u -m estufa.sensor --temp 38 --umidade 24 --intervalo 2`
- **Referência no código:** `estufa/controlador.py` (`_avaliar_regras_atuacao`, `L57–L78`; `_coordenar_consenso_e_persistir`, `L490–L552`), `estufa/atuador.py` (`L42–L63`) e `estufa/sensor.py` (`L25–L88`).
- **Explicação:** Ao cruzar os limiares (`Temp > 35°C` e `Umidade < 30%`), os controladores votam a transição de estado, apenas o líder `ctrl_3` publica em `estufa/atuadores/*`, o Atuador aciona bomba e exaustor confirmando em `estufa/status/*`, e o Sensor passa a reduzir a temperatura (`-2.5°C/ciclo`) e elevar a umidade (`+6.0%/ciclo`) em malha fechada.

### Passo 3 — Comando Manual Direto pelo Cliente
- **Execução:** No **Cliente**, selecionar opção `3` (Desligar bomba) ou `4` (Ligar exaustor) e consultar o estado com a opção `1`.
- **Referência no código:** `estufa/middleware.py` (`_chamar_com_failover`, `L170–L202`) e `estufa/controlador.py` (`_executar_comando_atuador`, `L627–L686`).
- **Explicação:** O Cliente invoca diretamente os controladores via `ClusterMiddleware`; o comando passa pela votação de consenso no cluster antes de ser persistido nos 3 arquivos JSON e publicado ao atuador.

### Passo 4 — Queda do Líder (`ctrl_3`) → Eleição de `ctrl_2` (2/2)
- **Execução:** Encerrar (`Ctrl+C`) o **Controlador 3 (`:8003`)**. Aguardar ~2–3s e executar as opções `6` e `2` no Cliente.
- **Referência no código:** `estufa/controlador.py` (`_loop_heartbeat`, `L313–L348`; `realizar_eleicao`, `L241–L302`).
- **Explicação:** Com a parada de `ctrl_3`, o heartbeat dos seguidores detecta a falha e inicia nova eleição Bully; `ctrl_2` assume a liderança (`rank 2 > 1`) e o failover automático do `ClusterMiddleware` redireciona as chamadas do cliente sem interrupção.

### Passo 5 — Queda de `ctrl_2` → Modo Degradado 1/1 em `ctrl_1`
- **Execução:** Encerrar (`Ctrl+C`) o **Controlador 2 (`:8002`)**. Executar as opções `6`, `1` e `4` no Cliente.
- **Referência no código:** `estufa/middleware.py` (`calcular_consenso`, `L118–L146`).
- **Explicação:** Com apenas 1 controlador ativo, o cálculo de quórum dinâmico opera em modo degradado `1/1`, mantendo a disponibilidade do controle ambiental e do cliente em `ctrl_1`.

### Passo 6 — Reconexão e Ressincronização Automática dos Bancos
- **Execução:** Alterar o estado pelo Cliente enquanto apenas `ctrl_1` está ativo (ex.: opção `2`). Em seguida, religar `ctrl_2` e `ctrl_3`, consultar a opção `6` e comparar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`_sincronizar_com_cluster`, `L355–L402`; `anunciar_lider`, `L221–L238`).
- **Explicação:** Na inicialização de `ctrl_2` e `ctrl_3`, `_sincronizar_com_cluster` copia o estado atualizado do cluster para os bancos locais antes de retomar as votações, e a eleição Bully restabelece `ctrl_3` como líder mantendo os 3 arquivos JSON consistentes.

### Passo 7 — Falha Bizantina (`--byzantino`) e `ErroQuorum`
- **Execução (Cenário A — 3 ativos com 1 bizantino):** Interromper `ctrl_2` com `Ctrl+C` e reiniciá-lo com a flag `--byzantino`:
  `./.venv/Scripts/python.exe -u -m estufa.controlador 2 --byzantino`
  No Cliente, consultar estado (`1`), enviar comando (`3`) e comparar `data_ctrl_1.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`coletar_voto_estado`, `L409–L420`) e `estufa/middleware.py` (`calcular_consenso`, `L133–L140`).
- **Explicação (Cenário A):** Mesmo com `ctrl_2` respondendo valores adulterados (`999.9°C`, `-50%` e atuadores invertidos), o quórum majoritário `2/3` formado por `ctrl_1` e `ctrl_3` descarta o voto divergente antes do `commit_estado`, preservando os bancos honestos e a leitura do cliente.
- **Execução (Cenário B — 2 ativos em empate `1 vs 1`):** Encerrar `ctrl_1` (mantendo apenas `ctrl_2 --byzantino` e `ctrl_3` honesto) e consultar a opção `1` no Cliente.
- **Explicação (Cenário B):** Com 2 nós ativos divergindo (`1 vs 1`), `calcular_consenso` exige unanimidade `2/2` e lança `ErroQuorum`, bloqueando a persistência e o retorno de estado inconsistente.
