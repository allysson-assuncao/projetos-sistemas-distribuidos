# Roteiro Prático de Apresentação — TP1

> Cola rápida de execução nos terminais, localização dos trechos no código e falas para demonstrar cada mecanismo ao vivo.

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

**Comandos individuais (para abrir ou reiniciar manualmente com `Ctrl+C` + `↑`):**

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

## 2. Roteiro de Demonstração e Injeção de Falhas

### Passo 1 — Cluster Saudável (3/3), Eleição Inicial e Replicação
- **Ação no terminal:** Aguardar ~4s após subir os terminais; no Cliente, usar opção `6` (Saúde) e opção `1` (Consultar estado). Mostrar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Onde mostrar no código:** `estufa/controlador.py` (`realizar_eleicao`, `L257–L341`; `commit_estado`, `L539–L565`).
- **O que explicar:**
  - *Aqui vemos que na inicialização o algoritmo Bully elegeu `ctrl_3` (maior rank) como líder do cluster e os 3 bancos JSON gravaram exatamente os mesmos valores via `commit_estado` síncrono após consenso.*

### Passo 2 — Alteração de Parâmetros do Sensor (Malha Fechada Autônoma)
- **Ação no terminal:** Na janela do **Sensor**, dar `Ctrl+C`, apertar `Seta para Cima (↑)` e reiniciar com valores críticos:
  `.\.venv\Scripts\python.exe -u -m estufa.sensor --temp 38 --umidade 24 --intervalo 2`
- **Onde mostrar no código:** `estufa/controlador.py` (`_avaliar_regras_atuacao`, `L58–L79`; `_coordenar_consenso_e_persistir`, `L578–L670`), `estufa/atuador.py` (`L42–L63`) e `estufa/sensor.py` (`L37–L103`).
- **O que explicar:**
  - *Ao cruzar `Temp > 35°C` e `Umidade < 30%`, os controladores votam a mudança de estado, apenas o líder `ctrl_3` publica no tópico `estufa/atuadores/*`, o Atuador aciona bomba e exaustor e publica em `estufa/status/*`, fazendo o Sensor inverter a temperatura (caindo) e a umidade (subindo).*

### Passo 3 — Comando Manual Direto pelo Cliente
- **Ação no terminal:** No **Cliente**, escolher opção `3` (Desligar bomba) ou `4` (Ligar exaustor) e conferir com opção `1` (Consultar estado).
- **Onde mostrar no código:** `estufa/middleware.py` (`_chamar_com_failover`, `L194–L227`) e `estufa/controlador.py` (`_executar_comando_atuador`, `L747–L818`).
- **O que explicar:**
  - *O Cliente chama diretamente os controladores via `ClusterMiddleware`; o comando passa pela mesma votação de consenso no cluster antes de ser salvo nos 3 JSONs e enviado ao atuador.*

### Passo 4 — Queda do Líder (`ctrl_3`) → Eleição de `ctrl_2` (2/2)
- **Ação no terminal:** Fechar ou dar `Ctrl+C` na janela do **Controlador 3 (`:8003`)**. Aguardar ~2–3s e rodar opções `6` e `2` no Cliente.
- **Onde mostrar no código:** `estufa/controlador.py` (`_loop_heartbeat`, `L352–L387`; `realizar_eleicao`, `L257–L341`).
- **O que explicar:**
  - *Ao encerrar `ctrl_3`, o heartbeat dos seguidores detecta a queda e dispara uma nova eleição Bully; `ctrl_2` assume a liderança (`rank 2 > 1`) e o failover do `ClusterMiddleware` mantém o cliente funcionando sem erro.*

### Passo 5 — Queda de `ctrl_2` → Modo Degradado 1/1 em `ctrl_1`
- **Ação no terminal:** Dar `Ctrl+C` na janela do **Controlador 2 (`:8002`)**. Rodar opções `6`, `1` e `4` no Cliente.
- **Onde mostrar no código:** `estufa/middleware.py` (`calcular_consenso`, `L137–L170`).
- **O que explicar:**
  - *Com apenas 1 controlador vivo, o mecanismo de quórum dinâmico entra em modo degradado `1/1`, mantendo a estufa e o cliente operacionais em `ctrl_1`.*

### Passo 6 — Reconexão e Ressincronização Automática dos Bancos
- **Ação no terminal:** Alterar o estado no Cliente enquanto só `ctrl_1` está rodando (ex.: ligar bomba com opção `2`). Depois, nas janelas de `ctrl_2` e `ctrl_3`, apertar `↑` e `Enter` para religá-los. Conferir opção `6` e comparar `data_ctrl_1.json`, `data_ctrl_2.json` e `data_ctrl_3.json`.
- **Onde mostrar no código:** `estufa/controlador.py` (`_sincronizar_com_cluster`, `L394–L482`; `anunciar_lider`, `L237–L254`).
- **O que explicar:**
  - *Ao retomar `ctrl_2` e `ctrl_3`, o método `_sincronizar_com_cluster` copia o estado atualizado de `ctrl_1` para os bancos locais antes de qualquer nova votação, e o Bully devolve a liderança a `ctrl_3` mantendo os 3 JSONs idênticos.*

### Passo 7 — Falha Bizantina (`--byzantino`) e `ErroQuorum`
- **Ação A (3 ativos com 1 bizantino):** Dar `Ctrl+C` no `ctrl_2`, apertar `↑` e reiniciar com `--byzantino`:
  `.\.venv\Scripts\python.exe -u -m estufa.controlador 2 --byzantino`
  No Cliente, consultar estado (`1`) e enviar comando (`3`); comparar `data_ctrl_1.json` e `data_ctrl_3.json`.
- **Onde mostrar no código:** `estufa/controlador.py` (`coletar_voto_estado`, `L489–L502`) e `estufa/middleware.py` (`calcular_consenso`, `L156–L165`).
- **O que explicar A:**
  - *Mesmo com `ctrl_2` enviando `999.9°C`, `-50%` e atuadores invertidos, a maioria `2/3` (`ctrl_1` + `ctrl_3`) descarta o voto adulterado antes do `commit_estado`, protegendo os bancos honestos e a resposta ao cliente.*
- **Ação B (2 ativos em empate `1 vs 1`):** Dar `Ctrl+C` no `ctrl_1` (deixando só `ctrl_2 --byzantino` e `ctrl_3` honesto) e consultar opção `1` no Cliente.
- **O que explicar B:**
  - *Com 1 nó honesto e 1 bizantino em empate `1 vs 1`, `calcular_consenso` não atinge concordância `2/2` e levanta `ErroQuorum` para não aceitar nem gravar dado corrompido.*
