# Prompt Autossuficiente de Preparação e Validação (Máquina do Laboratório)

> **Como usar no laboratório:** Abra uma nova conversa do zero no Antigravity (`agy`) e passe este arquivo como contexto (`@prompt-tp1-lab-setup.md`) ou cole o texto abaixo. Ele é **100% autossuficiente**: prepara a `.venv`, valida todos os 58 testes unitários + 6 estágios E2E reais e deixa o ambiente limpo para você disparar a task `🚀 [DEMO] 1. Subir Todo o Sistema (Estufa TP1)`.

---

## Instruções para o Agente (`agy`)

Você está preparando e validando o ambiente para a apresentação ao vivo do `trabalho_pratico1` (Controle Automatizado de Estufa Agrícola com MQTT e XML-RPC) em uma máquina Windows de laboratório **sem Docker e sem permissões de Administrador**, usando o **Antigravity IDE (baseado em VS Code)**.

> **Nota de Governança SDD:** A especificação desta mudança já existe, foi auditada e está aprovada em `openspec/changes/prepare-tp1-lab-presentation/proposal.md` e `openspec/changes/prepare-tp1-lab-presentation/tasks.md`. Não é necessário criar novas propostas SDD; execute diretamente a validação operacional e preparação do ambiente abaixo.

Execute os passos abaixo em sequência até confirmar que tudo está 100% operacional:

### PASSO 1 — Sincronização Git e Verificação de Arquivos
1. Verifique `git status` e, se necessário, execute `git pull` para garantir que os arquivos abaixo estão presentes no workspace:
   - `trabalho_pratico1/estufa/broker_local.py` (Broker MQTT v3.1.1 Híbrido: Mosquitto portátil + fallback Python puro na porta `1883`)
   - `trabalho_pratico1/estufa/middleware.py` (Com `_TimeoutTransport` e tratamento de `TimeoutError` no `as_completed` para Windows)
   - `trabalho_pratico1/scripts/validate_e2e.py` (Smoke Test End-to-End das Etapas 2 a 7)
   - `trabalho_pratico1/scripts/reset_demo.ps1` e `trabalho_pratico1/scripts/start_all.ps1`
   - `.vscode/tasks.json` e `trabalho_pratico1/.vscode/tasks.json` (com `shell.executable: "powershell.exe"` explícito)

### PASSO 2 — Ambiente Virtual Python (`.venv`) em User-Space (Sem Admin)
1. Teste se `.\trabalho_pratico1\.venv\Scripts\python.exe --version` e `.\trabalho_pratico1\.venv\Scripts\python.exe -c "import paho.mqtt.client, pytest; print('OK')"` funcionam nesta máquina.
2. **Atenção:** Como ambientes `.venv` contêm caminhos absolutos da máquina onde foram criados (ou não são versionados no Git), se `.venv\Scripts\python.exe` não existir ou falhar ao executar:
   - Remova a pasta `trabalho_pratico1/.venv` antiga (se existir corrompida).
   - Localize um Python >= 3.10 instalado na máquina (`python --version`, `py -3 --version`, ou em `$env:LOCALAPPDATA\Programs\Python`).
   - Crie a `.venv` limpa:
     ```powershell
     python -m venv trabalho_pratico1\.venv
     ```
   - Instale as dependências de `requirements.txt` (`paho-mqtt==2.1.0`, `pytest==8.3.3`, `pytest-timeout==2.3.1`):
     ```powershell
     .\trabalho_pratico1\.venv\Scripts\python.exe -m pip install -r .\trabalho_pratico1\requirements.txt
     ```

### PASSO 3 — Limpeza de Portas e Estados Residuais
Execute o script de reset para garantir que as portas `1883`, `8001`, `8002`, `8003` e `9000` estejam livres e que nenhum `data_ctrl_*.json` antigo interfira:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\trabalho_pratico1\scripts\reset_demo.ps1
```

### PASSO 4 — Execução da Suíte de Testes Unitários (58 Testes)
Execute o `pytest` usando o interpretador da `.venv`:
```powershell
.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider
```
- Todos os **58 testes** (`test_atuador.py`, `test_broker_local.py`, `test_controlador.py`, `test_middleware.py`) devem passar (`PASSED`).

### PASSO 5 — Execução do Smoke Test End-to-End Real (`validate_e2e.py`)
Execute o script de validação End-to-End que sobe processos reais do Broker MQTT Local (`:1883`), Middleware XML-RPC (`:9000`), 3 Réplicas (`:8001..8003`) e Atuador (nota: como o teste faz bind e conexões TCP em `127.0.0.1`, se o sandbox bloquear sockets com `WinError 10013`, execute com `BypassSandbox: true`):
```powershell
.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py
```
Confirme que todas as 6 verificações reais imprimem `[OK]` e finalizam com `[SUCESSO TOTAL]`:
1. `[ETAPA 2]` Cluster 3/3 online e saudável via Middleware XML-RPC (`:9000`)
2. `[ETAPA 3]` Acionamento autônomo MQTT (`Umidade=18.5% < 30%`) + MD5 determinístico + 2 descartes no Cache LRU do Atuador
3. `[ETAPA 4]` Tolerância a falha por parada (`ctrl_3` derrubado, quórum 2/3 mantido)
4. `[ETAPA 5]` Recuperação de falha (`ctrl_3` reiniciado sem JSON local sincroniza estado no boot via Middleware)
5. `[ETAPA 6]` Tolerância a falha bizantina (`ctrl_2 --byzantino` enviando `temp=999.0` mascarado por `ctrl_1 + ctrl_3`)
6. `[ETAPA 7]` Perda de quórum (`f=2` falhas simultâneas levanta `ERRO_QUORUM` com segurança)

### PASSO 6 — Confirmação Final de Prontidão
Verifique novamente que os arquivos `data_ctrl_*.json` foram limpos pelo `validate_e2e.py` e apresente ao usuário um resumo enxuto confirmando que o ambiente está pronto e listando o atalho para abrir os 8 terminais na chegada do professor:
- `Ctrl+Shift+P` -> `Tasks: Run Task` -> `🚀 [DEMO] 1. Subir Todo o Sistema (Estufa TP1)`
