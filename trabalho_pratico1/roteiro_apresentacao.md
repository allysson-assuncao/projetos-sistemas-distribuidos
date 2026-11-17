# Roteiro de Execução e Cenários de Teste — TP1

> Comandos de inicialização dos processos e cenários práticos de operação e tolerância a falhas do sistema.

---

## 1. Inicialização dos Terminais

No diretório `trabalho_pratico1/`:

```powershell
# 1. Limpar processos antigos e bancos JSON residuais
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/reset_demo.ps1

# 2. Subir os 6 serviços em janelas independentes
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/start_all.ps1

# 3. No terminal principal, abrir o Cliente CLI (7º processo)
./.venv/Scripts/python.exe -m estufa.cliente
```

**Comandos individuais por processo:**

| Processo | Comando |
|---|---|
| Broker MQTT (`:1883`) | `./.venv/Scripts/python.exe -u -m estufa.broker_local` |
| Controlador 1 (`:8001`) | `./.venv/Scripts/python.exe -u -m estufa.controlador 1` |
| Controlador 2 (`:8002`) | `./.venv/Scripts/python.exe -u -m estufa.controlador 2` |
| Controlador 3 (`:8003`) | `./.venv/Scripts/python.exe -u -m estufa.controlador 3` |
| Atuador MQTT | `./.venv/Scripts/python.exe -u -m estufa.atuador` |
| Sensor Contínuo | `./.venv/Scripts/python.exe -u -m estufa.sensor --temp 28 --umidade 42 --intervalo 2` |
| Cliente CLI | `./.venv/Scripts/python.exe -m estufa.cliente` |

---

## 2. Cenários de Operação e Tolerância a Falhas

### Passo 1 — Cluster Saudável (3/3), Eleição Inicial e Replicação
- **Execução:** Aguardar ~4s após subir os terminais; no Cliente, executar opção `6` (Saúde) e opção `1` (Consultar estado). Verificar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`realizar_eleicao`, `L257–L341`; `commit_estado`, `L539–L565`).
- **Explicação:** Na inicialização, o algoritmo Bully elege `ctrl_3` (maior `rank`) como líder do cluster e os 3 bancos JSON gravam exatamente os mesmos valores via `commit_estado` síncrono após o consenso.

### Passo 2 — Alteração de Parâmetros do Sensor (Malha Fechada Autônoma)
- **Execução:** No terminal do **Sensor**, interromper com `Ctrl+C` e reiniciar com valores fora da faixa ideal:
  `./.venv/Scripts/python.exe -u -m estufa.sensor --temp 38 --umidade 24 --intervalo 2`
- **Referência no código:** `estufa/controlador.py` (`_avaliar_regras_atuacao`, `L58–L79`; `_coordenar_consenso_e_persistir`, `L578–L670`), `estufa/atuador.py` (`L42–L63`) e `estufa/sensor.py` (`L37–L103`).
- **Explicação:** Ao cruzar os limiares (`Temp > 35°C` e `Umidade < 30%`), os controladores votam a transição de estado, apenas o líder `ctrl_3` publica em `estufa/atuadores/*`, o Atuador aciona bomba e exaustor confirmando em `estufa/status/*`, e o Sensor passa a reduzir a temperatura e elevar a umidade em malha fechada.

### Passo 3 — Comando Manual Direto pelo Cliente
- **Execução:** No **Cliente**, selecionar opção `3` (Desligar bomba) ou `4` (Ligar exaustor) e consultar o estado com a opção `1`.
- **Referência no código:** `estufa/middleware.py` (`_chamar_com_failover`, `L194–L227`) e `estufa/controlador.py` (`_executar_comando_atuador`, `L747–L818`).
- **Explicação:** O Cliente invoca diretamente os controladores via `ClusterMiddleware`; o comando passa pela votação de consenso no cluster antes de ser persistido nos 3 arquivos JSON e publicado ao atuador.

### Passo 4 — Queda do Líder (`ctrl_3`) → Eleição de `ctrl_2` (2/2)
- **Execução:** Encerrar (`Ctrl+C`) o **Controlador 3 (`:8003`)**. Aguardar ~2–3s e executar as opções `6` e `2` no Cliente.
- **Referência no código:** `estufa/controlador.py` (`_loop_heartbeat`, `L352–L387`; `realizar_eleicao`, `L257–L341`).
- **Explicação:** Com a parada de `ctrl_3`, o heartbeat dos seguidores detecta a falha e inicia nova eleição Bully; `ctrl_2` assume a liderança (`rank 2 > 1`) e o failover automático do `ClusterMiddleware` redireciona as chamadas do cliente sem interrupção.

### Passo 5 — Queda de `ctrl_2` → Modo Degradado 1/1 em `ctrl_1`
- **Execução:** Encerrar (`Ctrl+C`) o **Controlador 2 (`:8002`)**. Executar as opções `6`, `1` e `4` no Cliente.
- **Referência no código:** `estufa/middleware.py` (`calcular_consenso`, `L137–L170`).
- **Explicação:** Com apenas 1 controlador ativo, o cálculo de quórum dinâmico opera em modo degradado `1/1`, mantendo a disponibilidade do controle ambiental e do cliente em `ctrl_1`.

### Passo 6 — Reconexão e Ressincronização Automática dos Bancos
- **Execução:** Alterar o estado pelo Cliente enquanto apenas `ctrl_1` está ativo (ex.: opção `2`). Em seguida, religar `ctrl_2` e `ctrl_3`, consultar a opção `6` e comparar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`_sincronizar_com_cluster`, `L394–L482`; `anunciar_lider`, `L237–L254`).
- **Explicação:** Na inicialização de `ctrl_2` e `ctrl_3`, `_sincronizar_com_cluster` copia o estado atualizado do cluster para os bancos locais antes de retomar as votações, e a eleição Bully restabelece `ctrl_3` como líder mantendo os 3 arquivos JSON consistentes.

### Passo 7 — Falha Bizantina (`--byzantino`) e `ErroQuorum`
- **Execução (Cenário A — 3 ativos com 1 bizantino):** Interromper `ctrl_2` com `Ctrl+C` e reiniciá-lo com a flag `--byzantino`:
  `./.venv/Scripts/python.exe -u -m estufa.controlador 2 --byzantino`
  No Cliente, consultar estado (`1`), enviar comando (`3`) e comparar `data_ctrl_1.json` e `data_ctrl_3.json`.
- **Referência no código:** `estufa/controlador.py` (`coletar_voto_estado`, `L489–L502`) e `estufa/middleware.py` (`calcular_consenso`, `L156–L165`).
- **Explicação (Cenário A):** Mesmo com `ctrl_2` respondendo valores adulterados (`999.9°C`, `-50%` e atuadores invertidos), o quórum majoritário `2/3` formado por `ctrl_1` e `ctrl_3` descarta o voto divergente antes do `commit_estado`, preservando os bancos honestos e a leitura do cliente.
- **Execução (Cenário B — 2 ativos em empate `1 vs 1`):** Encerrar `ctrl_1` (mantendo apenas `ctrl_2 --byzantino` e `ctrl_3` honesto) e consultar a opção `1` no Cliente.
- **Explicação (Cenário B):** Com 2 nós ativos divergindo (`1 vs 1`), `calcular_consenso` exige unanimidade `2/2` e lança `ErroQuorum`, bloqueando a persistência e o retorno de estado inconsistente.
