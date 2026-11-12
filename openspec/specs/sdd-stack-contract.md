# SDD Stack Contract

> This file declares the technology stack and architectural constraints of this project.
> It is read by skills and subagents to make stack-aware decisions.
> Fill in each section and commit this file to version control.

---

## Stack Identity

- **Project Name:** projetos-sistemas-distribuidos (`trabalho_pratico1` — Estufa Agrícola Distribuída)
- **Primary Language:** Python
- **Runtime / Platform:** Python 3.10+ (Windows / Linux / macOS)
- **Framework:** `paho-mqtt` 2.1.0 (MQTT v3.1.1 QoS 1), Python `xmlrpc.server` / `xmlrpc.client` (XML-RPC)
- **Package Manager:** `pip` + `venv` (`requirements.txt`)

---

## Project Structure

- **Source Root:** `trabalho_pratico1/estufa/`
- **Test Root:** `trabalho_pratico1/tests/`
- **Entry Point:** `python -m estufa.<module>` (`broker_local`, `middleware_server`, `controlador`, `atuador`, `sensor`, `cliente`)
- **Build Output:** N/A (interpreted Python modules; runtime JSON state files `data_ctrl_*.json` in `trabalho_pratico1/`)

---

## Test Runner

- **Command:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v`
- **Test Framework:** `pytest==8.3.3` + `pytest-timeout==2.3.1` + `unittest.mock`
- **Coverage Command:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v && .\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py`

---

## Code Style

- **Linter:** Python standard syntax / `py_compile`
- **Formatter:** PEP 8 conventions
- **Format Command:** `python -m py_compile`

---

## API Contract (if applicable)

- **API Type:** XML-RPC (`http://localhost:9000`, `http://localhost:8001..8003`) & MQTT v3.1.1 (`localhost:1883`)
- **Spec Location:** `trabalho_pratico1/estufa/config.py` and `trabalho_pratico1/README.md`
- **Base URL (dev):** `http://localhost:9000` (Middleware XML-RPC), `mqtt://localhost:1883` (MQTT Broker)

---

## Database (if applicable)

- **Engine:** Local JSON state persistence (`data_ctrl_1.json`, `data_ctrl_2.json`, `data_ctrl_3.json`)
- **Migration Tool:** N/A (state auto-initialized from `ESTADO_INICIAL` in `estufa/controlador.py`)
- **Migration Command:** N/A

---

## Notes

- Lab environment constraint: Windows machines without Docker and without Administrator privileges.
- All services must bind strictly to `localhost` (`127.0.0.1`) on user-space ports (`1883`, `8001`, `8002`, `8003`, `9000`).
