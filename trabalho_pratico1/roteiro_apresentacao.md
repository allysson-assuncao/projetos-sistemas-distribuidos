# Roteiro Prático de Apresentação — TP1 (Windows 11 / Laboratório)

> Guia objetivo para executar os terminais no laboratório (sem Docker e sem Admin) e demonstrar cada mecanismo exigido pelo professor ao vivo.

---

## 1. Preparação e Inicialização dos Terminais

No diretório `trabalho_pratico1/`:

```powershell
# 1. Limpar processos antigos e bancos JSON residuais
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\reset_demo.ps1

# 2. Subir os 6 serviços em janelas independentes (já com histórico de comandos pronto)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_all.ps1

# 3. No terminal principal, abrir o Cliente CLI (7º processo)
.\.venv\Scripts\python.exe -m estufa.cliente
```

**Comandos individuais (caso prefira abrir ou reiniciar manualmente qualquer janela após `Ctrl+C` + `↑`):**

| Janela | Comando |
|---|---|
| Broker MQTT (`:1883`) | `.\.venv\Scripts\python.exe -u -m estufa.broker_local` |
| Controlador 1 (`:8001`) | `.\.venv\Scripts\python.exe -u -m estufa.controlador 1` |
| Controlador 2 (`:8002`) | `.\.venv\Scripts\python.exe -u -m estufa.controlador 2` |
| Controlador 3 (`:8003`) | `.\.venv\Scripts\python.exe -u -m estufa.controlador 3` |
| Atuador MQTT | `.\.venv\Scripts\python.exe -u -m estufa.atuador` |
| Sensor Contínuo | `.\.venv\Scripts\python.exe -u -m estufa.sensor --temp 28 --umidade 42 --intervalo 2` |
| Cliente CLI | `.\.venv\Scripts\python.exe -m estufa.cliente` |

---

## 2. Passo a Passo de Demonstração e Injeção de Falhas

### Passo 1 — Cluster Saudável (3/3), Eleição Inicial e Malha Fechada
- **Ação:** Aguardar ~4s após iniciar todos os terminais; no Cliente, escolher opção `6` (Saúde) e opção `1` (Consultar estado). Abrir `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **O que demonstrar:**
  - *Aqui podemos ver que ao iniciar o cluster, o algoritmo Bully (`realizar_eleicao`) elegeu `ctrl_3` (maior rank) como líder sem nenhum servidor intermediário na porta `9000`, e os 3 bancos JSON gravaram exatamente os mesmos valores via `commit_estado` síncrono.*

### Passo 2 — Alteração de Parâmetros do Sensor em Tempo Real (Acionamento Autônomo)
- **Ação:** Na janela do **Sensor**, pressionar `Ctrl+C`, apertar `Seta para Cima (↑)` e reiniciar com valores críticos:
  `.\.venv\Scripts\python.exe -u -m estufa.sensor --temp 38 --umidade 24 --intervalo 2`
- **O que demonstrar:**
  - *Aqui podemos ver que ao cruzar os limiares (`Temp > 35°C` e `Umidade < 30%`), apenas o Líder (`ctrl_3`) publica os comandos MQTT após o consenso, o Atuador aciona bomba e exaustor uma única vez e envia feedback em `estufa/status/*`, fazendo o Sensor inverter naturalmente a temperatura (caindo) e a umidade (subindo).*

### Passo 3 — Comando Direto pelo Cliente
- **Ação:** No **Cliente**, escolher opção `3` (Desligar bomba) ou `4` (Ligar exaustor) e depois `1` (Consultar estado).
- **O que demonstrar:**
  - *Aqui podemos ver que o Cliente se comunica diretamente com os controladores via `ClusterMiddleware`, que o comando é validado por consenso antes de ser persistido e replicado para os 3 arquivos `data_ctrl_*.json`.*

### Passo 4 — Queda do Líder (`ctrl_3`) → Failover Automático para `ctrl_2` (2/2)
- **Ação:** Fechar ou dar `Ctrl+C` na janela do **Controlador 3 (`:8003`)**. Aguardar ~2–3s e usar opção `6` e opção `2` no Cliente.
- **O que demonstrar:**
  - *Aqui podemos ver que ao encerrar o líder `ctrl_3`, o mecanismo de heartbeat (`_loop_heartbeat`) + algoritmo Bully garante que `ctrl_2` assuma a liderança automaticamente por conta da prioridade de rank (`2 > 1`), e o failover no `ClusterMiddleware` mantém o Cliente operando sem interrupção.*

### Passo 5 — Queda de `ctrl_2` → Modo Degradado 1/1 em `ctrl_1`
- **Ação:** Dar `Ctrl+C` na janela do **Controlador 2 (`:8002`)**. Usar opções `6`, `1` e `4` no Cliente.
- **O que demonstrar:**
  - *Aqui podemos ver que mesmo com 2 dos 3 controladores fora do ar, o mecanismo de quórum dinâmico permite que o último sobrevivente (`ctrl_1`) assuma a liderança isolada em modo degradado `1/1`, mantendo o controle da estufa disponível.*

### Passo 6 — Reconexão e Ressincronização Automática dos Bancos
- **Ação:** Alterar o estado no Cliente enquanto só `ctrl_1` está vivo (ex.: ligar bomba com opção `2`). Em seguida, na janela de `ctrl_2` e `ctrl_3`, apertar `↑` e `Enter` para religá-los normalmente. Conferir opção `6` no Cliente e comparar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **O que demonstrar:**
  - *Aqui podemos ver que ao retomar os processos `ctrl_2` e `ctrl_3`, o mecanismo de sincronização no boot (`_sincronizar_com_cluster`) garante que eles copiem o estado oficial atualizado de `ctrl_1` para seus bancos locais antes de operar, e o algoritmo Bully devolve a liderança a `ctrl_3` sem divergência nos arquivos JSON.*

### Passo 7 — Falha Bizantina (`--byzantino`) e Detecção de Conflito (`ErroQuorum`)
- **Ação A (3 ativos com 1 bizantino):** Dar `Ctrl+C` no `ctrl_2`, apertar `↑` e iniciar com `--byzantino`:
  `.\.venv\Scripts\python.exe -u -m estufa.controlador 2 --byzantino`
  Consultar opção `1` e enviar comando `3` no Cliente; comparar `data_ctrl_1.json` e `data_ctrl_3.json`.
- **O que demonstrar A:**
  - *Aqui podemos ver que embora `ctrl_2` esteja enviando leituras absurdas (`999.9°C`, `-50%`) e atuadores invertidos, o consenso majoritário (`2/3`) de `ctrl_1` e `ctrl_3` rejeita os dados bizantinos antes da persistência e mantém os bancos honestos intactos.*
- **Ação B (2 ativos em conflito):** Dar `Ctrl+C` no `ctrl_1` (deixando apenas `ctrl_2 --byzantino` e `ctrl_3` honesto) e consultar opção `1` no Cliente.
- **O que demonstrar B:**
  - *Aqui podemos ver que com apenas 1 nó honesto e 1 bizantino ativos (empate `1 vs 1`), o mecanismo de quórum dinâmico dispara `ErroQuorum` para impedir que um dado corrompido seja aceito como oficial.*
