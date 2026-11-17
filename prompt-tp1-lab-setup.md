# Prompt Autossuficiente de Preparação e Validação (Máquina do Laboratório)

> **Como usar no laboratório:** Abra uma nova conversa no Antigravity (`agy`) e passe este arquivo como contexto (`@prompt-tp1-lab-setup.md`). Ele prepara a `.venv`, executa os 34 testes unitários/de integração + validação E2E em 6 etapas e deixa o ambiente pronto para rodar o sistema em janelas independentes ou via VS Code Tasks.

---

## Instruções para o Agente (`agy`)

Você está preparando e validando o ambiente para a apresentação ao vivo do `trabalho_pratico1` (Estufa Agrícola Distribuída com Middleware XML-RPC embarcado, Eleição Bully, Consenso Replicado e MQTT QoS 1) em uma máquina **Windows 11 sem Docker e sem permissões de Administrador**.

Execute os passos abaixo em sequência:

### PASSO 1 — Sincronização Git e Verificação de Arquivos
Confirme no workspace a presença dos módulos atualizados:
- `trabalho_pratico1/estufa/broker_local.py` (Broker MQTT v3.1.1 em Python puro em `127.0.0.1:1883`)
- `trabalho_pratico1/estufa/config.py`, `middleware.py`, `controlador.py`, `cliente.py`, `sensor.py`, `atuador.py` (7 processos sem servidor `:9000`)
- `trabalho_pratico1/scripts/start_all.ps1`, `reset_demo.ps1`, `validate_e2e.py`
- `.vscode/tasks.json` e `trabalho_pratico1/.vscode/tasks.json`

### PASSO 2 — Ambiente Virtual Python (`.venv`) em User-Space (Sem Admin)
1. Teste `.\trabalho_pratico1\.venv\Scripts\python.exe -c "import paho.mqtt.client, pytest; print('OK')"`.
2. Se não existir `.venv` funcional na máquina do laboratório, crie e instale:
   ```powershell
   python -m venv trabalho_pratico1\.venv
   .\trabalho_pratico1\.venv\Scripts\python.exe -m pip install -r .\trabalho_pratico1\requirements.txt
   ```

### PASSO 3 — Limpeza de Portas e Estados Residuais
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\trabalho_pratico1\scripts\reset_demo.ps1
```
Confirme que as portas `1883`, `8001`, `8002` e `8003` estão livres e que não há `data_ctrl_*.json` antigos.

### PASSO 4 — Execução da Suíte de Testes (`pytest` — 34 Testes)
```powershell
.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider
```
Todos os 34 testes (`test_atuador.py`, `test_broker_local.py`, `test_controlador.py`, `test_middleware.py`, `test_sensor.py`) devem passar.

### PASSO 5 — Execução da Validação End-to-End Real (`validate_e2e.py`)
```powershell
.\trabalho_pratico1\.venv\Scripts\python.exe -B .\trabalho_pratico1\scripts\validate_e2e.py
```
Confirme que todas as 6 etapas finalizam com `[SUCESSO TOTAL]` (em `< 45s`) e os arquivos `data_ctrl_*.json` são limpos ao final:
1. Cluster 3/3 online e eleição Bully (`ctrl_3` líder)
2. Telemetria MQTT em malha fechada + consenso + `data_ctrl_1..3.json` idênticos
3. Queda de `ctrl_3` -> failover automático para `ctrl_2` (`2/2`)
4. Queda de `ctrl_2` -> modo degradado `1/1` em `ctrl_1`
5. Reconexão de `ctrl_2` e `ctrl_3` -> ressincronização automática dos bancos JSON e retomada Bully em `ctrl_3`
6. `ctrl_2 --byzantino` mascarado pela maioria `2/3` e `ErroQuorum` em conflito `1 honesto vs 1 bizantino`

### PASSO 6 — Prontidão para Apresentação ao Vivo
Apresente ao usuário o resumo de validação e informe o comando interativo para abrir os terminais independentes (com histórico pronto para `Ctrl+C` + `↑`):
```powershell
cd trabalho_pratico1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_all.ps1
.\.venv\Scripts\python.exe -m estufa.cliente
```
