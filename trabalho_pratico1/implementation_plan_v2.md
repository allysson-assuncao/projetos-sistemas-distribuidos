# Updated Implementation Plan v2 — Trabalho Prático 1 (SD)
## Estufa Agrícola Automatizada — Distributed System with MQTT + XML-RPC
### Architectural Redesign: Standalone Middleware, State Transfer & MQTT Deduplication

---

## Overview of Architectural Changes

This plan supersedes the original `implementation_plan.md`. It corrects three critical architectural flaws identified in the original design:

### Flaw 1 → Fix: Middleware Topology (CRITICAL)
| Before | After |
|---|---|
| `middleware.py` is a Python library imported by `cliente.py` | `middleware_server.py` is a **standalone XML-RPC server process** (port 9000) |
| Client directly instantiates `Middleware()` and calls methods | Client connects to `http://localhost:9000` via `xmlrpc.client.ServerProxy` |
| BFT voting logic lives in the client process | BFT voting logic lives inside the autonomous middleware process |

**Architectural justification:** The assignment diagram explicitly shows the Middleware as a structural box that *contains* the process controllers. Clients connect *to* the Middleware, not to controllers directly. The Middleware is the single point of contact that exposes **Method Invocation** to clients and internally handles **Synchronization and Fault Tolerance**.

### Flaw 2 → Fix: Boot-time State Synchronization (State Transfer)
| Before | After |
|---|---|
| Controller starts with local JSON file state (may be stale) or empty state | Controller queries the Middleware Server via XML-RPC at boot to get majority-approved state |
| Recovering controller diverges from the cluster immediately | Recovering controller converges to cluster state before consuming MQTT messages |

**Boot sequence:** `Middleware Server` must be running before controllers attempt state transfer. Controllers execute a `sincronizar_estado()` method at startup that calls `middleware:9000.obter_estado()` and overwrites local JSON.

### Flaw 3 → Fix: MQTT Command Deduplication (Write Coordination)
| Before | After |
|---|---|
| All 3 controllers publish identical MQTT commands simultaneously | Middleware generates a UUID `comando_id` per command; all 3 controllers include it in the MQTT payload |
| Actuator processes the same physical command 3 times | Actuator maintains an LRU cache of the last 50 `comando_id` values and silently discards duplicates |

---

## Final File Structure

```
trabalho_pratico1/
│
├── .gitignore                          # [NEW] Ignores __pycache__, broker data, .env
├── docker-compose.yml                  # Broker Mosquitto
├── mosquitto/
│   └── mosquitto.conf
│
├── requirements.txt                    # paho-mqtt, pytest
│
├── estufa/                             # Main package
│   ├── __init__.py
│   ├── config.py                       # [MODIFIED] Adds MIDDLEWARE_PORT = 9000
│   ├── sensor.py                       # Unchanged
│   ├── atuador.py                      # [MODIFIED] LRU deduplication cache
│   ├── controlador.py                  # [MODIFIED] Boot-time state sync via Middleware
│   ├── middleware.py                   # [MODIFIED] Voting logic (now internal module)
│   ├── middleware_server.py            # [NEW] Standalone XML-RPC server (port 9000)
│   └── cliente.py                      # [MODIFIED] Connects to middleware:9000
│
├── tests/
│   ├── __init__.py
│   ├── test_middleware.py              # [MODIFIED] Tests against middleware server
│   ├── test_controlador.py            # [MODIFIED] Tests with state sync mock
│   ├── test_atuador.py                # [NEW] Tests for LRU deduplication
│   └── test_integracao.py             # Integration tests (broker required)
│
├── scripts/
│   ├── start_all.sh                   # [MODIFIED] Adds middleware_server step
│   ├── start_all.ps1                  # [MODIFIED] Adds middleware_server step
│   └── demo_byzantino.py              # Unchanged
│
└── README.md
```

---

## Phase 0 — Repository Initialization & .gitignore

**Responsible Agent:** Phase 0  
**Prerequisites:** Git initialized on `main` branch (already done)  
**Goal:** Add `.gitignore` to prevent noise files from polluting the repository.

### 0.1 — Create `.gitignore`

Create `trabalho_pratico1/.gitignore` with exact content:

```gitignore
# Python bytecode
__pycache__/
*.py[cod]
*$py.class
*.pyc

# Virtual environments
.venv/
venv/
env/
*.egg-info/

# Mosquitto broker persistent data (Docker volume artifacts)
mosquitto/data/
mosquitto/log/

# Controller JSON state files (runtime artifacts, not source)
data_ctrl_*.json

# Test artifacts
.pytest_cache/
.coverage
htmlcov/

# OS artifacts
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
```

### 0.2 — Git Commit

```bash
cd /path/to/projetos-sistemas-distribuidos
git add trabalho_pratico1/.gitignore
git commit -m "chore(phase-0): add .gitignore for python, broker data and runtime artifacts"
```

---

## Phase 1 — Infrastructure (Broker + Dependencies)

**Responsible Agent:** Phase 1  
**Prerequisites:** Docker installed and running; Python 3.9+  
**Goal:** Verify Docker availability, set up the MQTT broker, and install dependencies.

### 1.1 — Verify Docker Availability

```bash
# Verify Docker is installed and daemon is running
docker --version  # Must output Docker version X.Y.Z
docker info       # Must NOT output "Cannot connect to the Docker daemon"

# If Docker daemon is not running:
# Linux: sudo systemctl start docker
# macOS/Windows: Start Docker Desktop
```

### 1.2 — Create `docker-compose.yml`

Create `trabalho_pratico1/docker-compose.yml`:

```yaml
version: "3.8"

services:
  mosquitto:
    image: eclipse-mosquitto:2.0
    container_name: estufa_mqtt_broker
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf
      - mosquitto_data:/mosquitto/data
    restart: unless-stopped

volumes:
  mosquitto_data:
```

### 1.3 — Create `mosquitto/mosquitto.conf`

Create `trabalho_pratico1/mosquitto/mosquitto.conf`:

```
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

### 1.4 — Create `requirements.txt`

Create `trabalho_pratico1/requirements.txt`:

```
paho-mqtt==2.1.0
pytest==8.3.3
pytest-timeout==2.3.1
```

> **Note:** The LRU cache for deduplication uses `collections.OrderedDict` from the Python standard library. No additional dependencies are needed.

### 1.5 — Create Package Init Files

Create `trabalho_pratico1/estufa/__init__.py` (empty).  
Create `trabalho_pratico1/tests/__init__.py` (empty).  
Create `trabalho_pratico1/scripts/.gitkeep` (empty).

### 1.6 — Verification

```bash
# From trabalho_pratico1/
docker compose up -d
docker ps  # Must show "estufa_mqtt_broker" with status "Up"
docker compose down

pip install -r requirements.txt
python -c "import paho.mqtt.client; print('paho-mqtt OK')"
```

### 1.7 — Git Commit

```bash
git add trabalho_pratico1/
git commit -m "feat(phase-1): bootstrap infrastructure — mosquitto broker, requirements, package skeleton"
```

---

## Phase 2 — Global Configuration Module

**Responsible Agent:** Phase 2  
**Prerequisite:** Phase 1 completed

### 2.1 — Create `estufa/config.py`

Create `trabalho_pratico1/estufa/config.py` with **exact** content:

```python
"""
config.py — Global constants for the Distributed Agricultural Greenhouse System.

All MQTT topics, XML-RPC ports, and control thresholds are centralized here.
"""

# ──────────────────────────────────────────────
# MQTT — Broker
# ──────────────────────────────────────────────
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# ──────────────────────────────────────────────
# MQTT — Topics
# ──────────────────────────────────────────────
TOPIC_TEMPERATURA   = "estufa/sensores/temperatura"
TOPIC_UMIDADE_SOLO  = "estufa/sensores/umidade_solo"
TOPIC_ATUADOR_BOMBA = "estufa/atuadores/bomba"
TOPIC_ATUADOR_EXAUSTOR = "estufa/atuadores/exaustor"
TOPIC_STATUS_BOMBA  = "estufa/status/bomba"
TOPIC_STATUS_EXAUSTOR = "estufa/status/exaustor"

# ──────────────────────────────────────────────
# XML-RPC — Controllers (internal cluster)
# ──────────────────────────────────────────────
CONTROLADORES = [
    {"id": "ctrl_1", "host": "localhost", "port": 8001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 8002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 8003, "data_file": "data_ctrl_3.json"},
]

# ──────────────────────────────────────────────
# XML-RPC — Middleware Server (external-facing)
# ──────────────────────────────────────────────
MIDDLEWARE_HOST = "localhost"
MIDDLEWARE_PORT = 9000   # Single entry point for all clients

# ──────────────────────────────────────────────
# Greenhouse Control Thresholds
# ──────────────────────────────────────────────
TEMP_MAX_CELSIUS     = 35.0   # Above: turn on exhaust fan
TEMP_MIN_CELSIUS     = 15.0   # Below: turn off exhaust fan
UMIDADE_MIN_PERCENT  = 30.0   # Below: turn on irrigation pump
UMIDADE_MAX_PERCENT  = 70.0   # Above: turn off irrigation pump

# ──────────────────────────────────────────────
# Middleware — Voting Parameters
# ──────────────────────────────────────────────
TIMEOUT_RPC_SEGUNDOS = 3       # Per XML-RPC call timeout
QUORUM_MINIMO        = 2       # Minimum concordant responses for quorum

# ──────────────────────────────────────────────
# Actuator Deduplication
# ──────────────────────────────────────────────
DEDUP_CACHE_SIZE     = 50      # LRU cache size for comando_id deduplication
```

### 2.2 — Git Commit

```bash
git add trabalho_pratico1/estufa/config.py
git commit -m "feat(phase-2): add global config with MIDDLEWARE_PORT=9000 and DEDUP_CACHE_SIZE"
```

---

## Phase 3 — Sensor (Unchanged)

**Responsible Agent:** Phase 3  
**Prerequisite:** Phase 2 completed  
**Note:** The sensor is architecturally correct as-is. Copy `sensor.py` from the original plan v1 verbatim. No changes needed.

### 3.1 — Git Commit

```bash
git add trabalho_pratico1/estufa/sensor.py
git commit -m "feat(phase-3): add sensor process (MQTT publisher, unchanged from v1)"
```

---

## Phase 4 — Actuator with LRU Deduplication

**Responsible Agent:** Phase 4  
**Prerequisite:** Phase 3 completed

### 4.1 — Deduplication Architecture

The actuator maintains an LRU cache using `collections.OrderedDict` bounded to `DEDUP_CACHE_SIZE` entries. When a MQTT message arrives:

1. Parse the `payload.get("comando_id")` field (a UUID string generated by the Middleware)
2. Check if `comando_id` is already in the LRU cache → **discard silently** if yes
3. If new → add `comando_id` to cache (evict oldest if at capacity) → **process the command**

This strategy handles the case where all 3 controllers publish the same command simultaneously (same `comando_id`).

### 4.2 — Create `estufa/atuador.py`

Create `trabalho_pratico1/estufa/atuador.py` with **exact** content:

```python
"""
atuador.py — Actuator Process for the Greenhouse System.

Subscribes to command topics on MQTT and simulates:
  - Irrigation pump (on/off)
  - Exhaust fan (on/off)

DEDUPLICATION: Since the Middleware sends the same command to all 3 controllers,
all 3 may publish to MQTT simultaneously. The actuator deduplicates using a
UUID-based 'comando_id' included in the payload. An LRU cache tracks the last
DEDUP_CACHE_SIZE processed IDs and silently discards duplicates.

Usage:
    python -m estufa.atuador
"""

import json
import time
import collections
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────────────────────────
# Internal State
# ─────────────────────────────────────────────────────────────
_estado_bomba    = {"ligado": False}
_estado_exaustor = {"ligado": False}

# LRU Cache for comando_id deduplication
# Uses OrderedDict: newest at end, oldest at front (evicted when full)
_dedup_cache: collections.OrderedDict = collections.OrderedDict()


def _is_duplicado(comando_id: str) -> bool:
    """
    Checks if a comando_id has already been processed (LRU cache lookup).

    Returns True if the command is a duplicate and should be discarded.
    Side effect: adds new IDs to the cache and evicts oldest if at capacity.
    """
    if not comando_id:
        # No ID provided — cannot deduplicate, process the command
        return False

    if comando_id in _dedup_cache:
        # Move to end to mark as recently seen (LRU refresh)
        _dedup_cache.move_to_end(comando_id)
        return True  # Duplicate — discard

    # New ID: add to cache
    _dedup_cache[comando_id] = True
    _dedup_cache.move_to_end(comando_id)

    # Evict oldest entry if cache exceeds capacity
    if len(_dedup_cache) > config.DEDUP_CACHE_SIZE:
        _dedup_cache.popitem(last=False)

    return False  # Not a duplicate — process


def _on_connect(client, userdata, flags, reason_code, properties):
    """Connection callback: subscribe to actuator command topics."""
    if reason_code == 0:
        print("[ATUADOR] Conectado ao broker MQTT.")
        client.subscribe(config.TOPIC_ATUADOR_BOMBA,    qos=1)
        client.subscribe(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_BOMBA}")
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_EXAUSTOR}")
    else:
        print(f"[ATUADOR] Falha na conexão: {reason_code}")


def _processar_bomba(client: mqtt.Client, payload: dict) -> None:
    """Processes pump command and publishes confirmation status."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_bomba["ligado"] = novo_estado
    status = "LIGADA" if novo_estado else "DESLIGADA"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] 💧 Bomba de Irrigação → {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_BOMBA, "bomba", novo_estado)


def _processar_exaustor(client: mqtt.Client, payload: dict) -> None:
    """Processes exhaust fan command and publishes confirmation status."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_exaustor["ligado"] = novo_estado
    status = "LIGADO" if novo_estado else "DESLIGADO"
    origem = payload.get("origem", "desconhecido")
    print(f"[ATUADOR] 🌬️ Exaustor → {status} (origem: {origem})")
    _publicar_status(client, config.TOPIC_STATUS_EXAUSTOR, "exaustor", novo_estado)


def _publicar_status(client: mqtt.Client, topico: str, nome: str, ligado: bool) -> None:
    """Publishes execution confirmation on the status topic."""
    payload = json.dumps({
        "atuador": nome,
        "ligado": ligado,
        "timestamp": time.time(),
    })
    client.publish(topico, payload, qos=1)


def _on_message(client, userdata, msg):
    """
    Message callback: deduplicates via LRU cache, then routes to handler.

    Deduplication flow:
    1. Parse payload and extract 'comando_id'
    2. If 'comando_id' is in LRU cache → discard (duplicate from another controller)
    3. If new → process and add to cache
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[ATUADOR] Payload inválido em {msg.topic}: {msg.payload}")
        return

    # ── Deduplication Check ────────────────────────────────────
    comando_id = payload.get("comando_id", "")
    if _is_duplicado(comando_id):
        print(f"[ATUADOR] 🔁 Comando duplicado ignorado: {comando_id[:8]}... (tópico: {msg.topic})")
        return

    # ── Route to handler ───────────────────────────────────────
    if msg.topic == config.TOPIC_ATUADOR_BOMBA:
        _processar_bomba(client, payload)
    elif msg.topic == config.TOPIC_ATUADOR_EXAUSTOR:
        _processar_exaustor(client, payload)


def executar_atuador():
    """Starts the actuator and waits for commands indefinitely."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="atuador_estufa")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print("[ATUADOR] Aguardando comandos... (deduplicação LRU ativa)")
    client.loop_forever()


if __name__ == "__main__":
    executar_atuador()
```

### 4.3 — Git Commit

```bash
git add trabalho_pratico1/estufa/atuador.py
git commit -m "feat(phase-4): add actuator with LRU deduplication cache for MQTT commands"
```

---

## Phase 5 — Controller with Boot-time State Synchronization

**Responsible Agent:** Phase 5  
**Prerequisite:** Phase 4 completed

### 5.1 — State Synchronization Architecture

**Critical Boot Sequence Dependency:**
```
[Broker UP] → [Middleware Server UP @ :9000] → [Controller boots + STATE SYNC] → [Sensor/Actuator] → [Client]
```

The controller **cannot** perform state sync if the Middleware is not running yet. The `iniciar()` method must:

1. Start the XML-RPC server in a **background thread**
2. Attempt state sync in the **main thread** with retry logic
3. On sync success: overwrite local JSON with the majority state
4. On sync failure (middleware not yet up): **wait and retry** up to N times
5. After sync: start the MQTT client to begin consuming sensor data

**Important:** During state sync, the controller temporarily connects as an XML-RPC **client** to the Middleware Server at port 9000. After sync, it switches to full server mode serving the Middleware.

### 5.2 — Create `estufa/controlador.py`

Create `trabalho_pratico1/estufa/controlador.py` with **exact** content:

```python
"""
controlador.py — Controller Process for the Greenhouse System.

Responsibilities:
  1. Boot-time State Transfer: queries the Middleware Server for the
     majority-approved state before consuming MQTT messages.
  2. MQTT Subscription: receives temperature and humidity readings.
  3. Decision Logic: activates pump and exhaust fan per thresholds.
  4. JSON Persistence: saves current state to a local file.
  5. XML-RPC Server: exposes remote methods to the Middleware (internal cluster API).

MQTT Deduplication: Each MQTT command payload includes a 'comando_id' (UUID)
generated by the Middleware. The actuator deduplicates using this ID.

Startup Sequence:
    1. Start XML-RPC server in a background thread (so Middleware can reach us)
    2. Query Middleware Server to sync state (with retries)
    3. Start MQTT client to consume sensor data

Usage:
    python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
    python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json

    # Byzantine mode (for fault demonstration):
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
"""

import argparse
import json
import os
import threading
import time
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────
# Default state
# ─────────────────────────────────────────
ESTADO_INICIAL = {
    "temperatura": None,
    "umidade_solo": None,
    "bomba_ligada": False,
    "exaustor_ligado": False,
    "ultima_atualizacao": None,
    "controlador_id": None,
}


class Controlador:
    """
    Greenhouse process controller node.

    Thread-safe: lock protects shared state between MQTT thread (writes)
    and XML-RPC server thread (reads).
    """

    def __init__(self, ctrl_id: str, data_file: str, byzantino: bool = False):
        """
        Args:
            ctrl_id: Unique identifier for this controller (e.g. 'ctrl_1').
            data_file: Path to the JSON persistence file.
            byzantino: If True, returns deliberately wrong data (fault simulation).
        """
        self.ctrl_id = ctrl_id
        self.data_file = data_file
        self.byzantino = byzantino
        self._lock = threading.Lock()
        self._mqtt_client = None

        # Load state from disk or use initial state
        self._estado = self._carregar_estado()
        self._estado["controlador_id"] = ctrl_id

    # ─── Persistence ────────────────────────────────────────────

    def _carregar_estado(self) -> dict:
        """Reads current state from JSON file. Returns initial state if file missing."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return dict(ESTADO_INICIAL)

    def _salvar_estado(self) -> None:
        """Persists current state to JSON file (must be called with lock held)."""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._estado, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[{self.ctrl_id}] Erro ao salvar estado: {e}")

    # ─── Boot-time State Synchronization ────────────────────────

    def _sincronizar_estado_via_middleware(self, max_tentativas: int = 10, intervalo: float = 2.0) -> bool:
        """
        Queries the Middleware Server for the majority-approved state and
        overwrites local JSON with it.

        This is called ONCE at startup before MQTT consumption begins.
        The Middleware must already be running on MIDDLEWARE_PORT.

        Args:
            max_tentativas: Maximum retry attempts if Middleware is unreachable.
            intervalo: Seconds to wait between retries.

        Returns:
            True if sync succeeded, False if all retries failed.
        """
        mw_url = f"http://{config.MIDDLEWARE_HOST}:{config.MIDDLEWARE_PORT}"
        print(f"[{self.ctrl_id}] 🔄 Iniciando sincronização de estado via Middleware ({mw_url})...")

        for tentativa in range(1, max_tentativas + 1):
            try:
                proxy = xmlrpc.client.ServerProxy(mw_url, allow_none=True)
                # Use the middleware's internal quorum-read (excludes this node if down)
                estado_majoritario = proxy.obter_estado()

                with self._lock:
                    # Preserve our controller_id, update everything else
                    estado_majoritario["controlador_id"] = self.ctrl_id
                    self._estado = estado_majoritario
                    self._salvar_estado()

                print(f"[{self.ctrl_id}] ✅ Estado sincronizado com sucesso (tentativa {tentativa}/{max_tentativas}).")
                print(f"[{self.ctrl_id}]    Bomba={self._estado.get('bomba_ligada')}, "
                      f"Exaustor={self._estado.get('exaustor_ligado')}, "
                      f"Temp={self._estado.get('temperatura')}")
                return True

            except Exception as e:
                print(f"[{self.ctrl_id}] ⚠️  Tentativa {tentativa}/{max_tentativas} — Middleware indisponível: {e}")
                if tentativa < max_tentativas:
                    time.sleep(intervalo)

        print(f"[{self.ctrl_id}] ⚠️  Sincronização falhou após {max_tentativas} tentativas. "
              f"Iniciando com estado local (pode estar desatualizado).")
        return False

    # ─── Decision Logic ──────────────────────────────────────────

    def _decidir_atuacao(self) -> None:
        """
        Evaluates current state and decides whether to activate/deactivate actuators.
        Publishes MQTT commands with a 'comando_id' generated by this controller.
        Must be called with the lock held.

        NOTE: The 'comando_id' is generated here at the controller level.
        The Middleware generates a shared 'comando_id' for manual commands
        (via comandar_bomba/comandar_exaustor). For sensor-driven decisions,
        each controller generates its own UUID — the actuator's LRU cache
        handles deduplication of any identical concurrent publishes.
        """
        import uuid
        temp    = self._estado.get("temperatura")
        umidade = self._estado.get("umidade_solo")

        if temp is not None:
            if temp > config.TEMP_MAX_CELSIUS and not self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = True
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "ligar", str(uuid.uuid4()))
                print(f"[{self.ctrl_id}] 🌡️  Temp={temp:.1f}°C > {config.TEMP_MAX_CELSIUS}°C → LIGAR exaustor")
            elif temp < config.TEMP_MIN_CELSIUS and self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = False
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "desligar", str(uuid.uuid4()))
                print(f"[{self.ctrl_id}] 🌡️  Temp={temp:.1f}°C < {config.TEMP_MIN_CELSIUS}°C → DESLIGAR exaustor")

        if umidade is not None:
            if umidade < config.UMIDADE_MIN_PERCENT and not self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = True
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "ligar", str(uuid.uuid4()))
                print(f"[{self.ctrl_id}] 💧 Umidade={umidade:.1f}% < {config.UMIDADE_MIN_PERCENT}% → LIGAR bomba")
            elif umidade > config.UMIDADE_MAX_PERCENT and self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = False
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "desligar", str(uuid.uuid4()))
                print(f"[{self.ctrl_id}] 💧 Umidade={umidade:.1f}% > {config.UMIDADE_MAX_PERCENT}% → DESLIGAR bomba")

    def _publicar_comando(self, topico: str, acao: str, comando_id: str) -> None:
        """Publishes a command to an actuator via MQTT, including the comando_id for deduplication."""
        payload = json.dumps({
            "acao": acao,
            "origem": self.ctrl_id,
            "comando_id": comando_id,
            "timestamp": time.time(),
        })
        if self._mqtt_client:
            self._mqtt_client.publish(topico, payload, qos=1)

    # ─── MQTT Callbacks ──────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(config.TOPIC_TEMPERATURA,  qos=1)
            client.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)
            print(f"[{self.ctrl_id}] Conectado ao MQTT. Assinando tópicos de sensores.")
        else:
            print(f"[{self.ctrl_id}] Falha na conexão MQTT: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            valor   = float(payload["valor"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[{self.ctrl_id}] Mensagem inválida: {e}")
            return

        with self._lock:
            if msg.topic == config.TOPIC_TEMPERATURA:
                self._estado["temperatura"] = valor
                print(f"[{self.ctrl_id}] 🌡️  Temperatura recebida: {valor:.2f}°C")
            elif msg.topic == config.TOPIC_UMIDADE_SOLO:
                self._estado["umidade_solo"] = valor
                print(f"[{self.ctrl_id}] 💧 Umidade do solo recebida: {valor:.2f}%")

            self._estado["ultima_atualizacao"] = time.time()
            self._decidir_atuacao()
            self._salvar_estado()

    # ─── XML-RPC Methods (exposed to Middleware) ─────────────────

    def obter_estado(self) -> dict:
        """
        Returns the current greenhouse state.
        If in Byzantine mode, returns deliberately falsified data.
        """
        with self._lock:
            if self.byzantino:
                return {
                    "temperatura": 999.0,
                    "umidade_solo": -1.0,
                    "bomba_ligada": not self._estado.get("bomba_ligada", False),
                    "exaustor_ligado": not self._estado.get("exaustor_ligado", False),
                    "ultima_atualizacao": time.time(),
                    "controlador_id": self.ctrl_id,
                    "_byzantino": True,
                }
            return dict(self._estado)

    def comandar_bomba(self, acao: str, comando_id: str = "") -> dict:
        """
        Manual command: turn pump on or off.

        Args:
            acao: 'ligar' or 'desligar'
            comando_id: UUID generated by Middleware for deduplication at actuator level.

        Returns:
            dict with 'sucesso' (bool) and 'mensagem' (str).
        """
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {"sucesso": False, "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'."}

        if self.byzantino:
            return {"sucesso": True, "mensagem": f"[BYZANTINO] Bomba {acao}da (FALSO)", "byzantino": True}

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["bomba_ligada"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, acao, comando_id)
            self._salvar_estado()
            return {"sucesso": True, "mensagem": f"Bomba {acao}da com sucesso pelo {self.ctrl_id}"}

    def comandar_exaustor(self, acao: str, comando_id: str = "") -> dict:
        """
        Manual command: turn exhaust fan on or off.

        Args:
            acao: 'ligar' or 'desligar'
            comando_id: UUID generated by Middleware for deduplication.

        Returns:
            dict with 'sucesso' (bool) and 'mensagem' (str).
        """
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {"sucesso": False, "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'."}

        if self.byzantino:
            return {"sucesso": True, "mensagem": f"[BYZANTINO] Exaustor {acao}do (FALSO)", "byzantino": True}

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["exaustor_ligado"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, acao, comando_id)
            self._salvar_estado()
            return {"sucesso": True, "mensagem": f"Exaustor {acao}do com sucesso pelo {self.ctrl_id}"}

    def ping(self) -> str:
        """Health-check used by the Middleware to detect alive replicas."""
        return f"pong:{self.ctrl_id}"

    # ─── Initialization ──────────────────────────────────────────

    def iniciar(self, host: str, port: int, skip_sync: bool = False) -> None:
        """
        Starts the controller in the correct boot sequence:

        1. Start XML-RPC server in a daemon thread (must be up so Middleware can see it)
        2. Perform boot-time state synchronization via Middleware (with retries)
        3. Connect to MQTT broker and begin consuming sensor data

        Args:
            host: Host for the XML-RPC server.
            port: Port for the XML-RPC server.
            skip_sync: If True, skip state sync (useful for testing or first boot before Middleware starts).
        """
        # ── Step 1: Start XML-RPC server in background ────────────────────────
        class SilentHandler(SimpleXMLRPCRequestHandler):
            """Suppresses HTTP logs from the XML-RPC server."""
            def log_message(self, fmt, *args):
                pass

        server = SimpleXMLRPCServer(
            (host, port),
            requestHandler=SilentHandler,
            allow_none=True,
            logRequests=False,
        )
        server.register_instance(self)
        server.register_introspection_functions()

        modo = " [MODO BYZANTINO]" if self.byzantino else ""
        print(f"[{self.ctrl_id}] XML-RPC server iniciado em {host}:{port}{modo}")

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # ── Step 2: Boot-time State Synchronization ───────────────────────────
        if not skip_sync:
            self._sincronizar_estado_via_middleware()
        else:
            print(f"[{self.ctrl_id}] ⚠️  Sincronização de estado ignorada (--skip-sync ativo).")

        # ── Step 3: Connect to MQTT broker ────────────────────────────────────
        self._mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"controlador_{self.ctrl_id}"
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)

        print(f"[{self.ctrl_id}] ✅ Controlador totalmente inicializado. Consumindo sensores MQTT.")
        self._mqtt_client.loop_forever()  # Blocks here (main thread)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Controlador da Estufa")
    parser.add_argument("--id",        required=True,        help="Controller ID (e.g. ctrl_1)")
    parser.add_argument("--port",      required=True,        type=int, help="XML-RPC port")
    parser.add_argument("--data",      required=True,        help="JSON persistence file")
    parser.add_argument("--host",      default="localhost",  help="XML-RPC server host")
    parser.add_argument("--byzantino", action="store_true",  help="Byzantine mode (returns false data)")
    parser.add_argument("--skip-sync", action="store_true",  help="Skip boot-time state synchronization")
    args = parser.parse_args()

    ctrl = Controlador(ctrl_id=args.id, data_file=args.data, byzantino=args.byzantino)
    ctrl.iniciar(host=args.host, port=args.port, skip_sync=args.skip_sync)
```

### 5.3 — Git Commit

```bash
git add trabalho_pratico1/estufa/controlador.py
git commit -m "feat(phase-5): add controller with boot-time state sync via middleware server"
```

---

## Phase 6 — Middleware (Internal Voting Module + Standalone Server)

**Responsible Agent:** Phase 6  
**Prerequisite:** Phase 5 completed

This phase creates **two files**:
1. `middleware.py` — Internal voting logic module (used **only** by `middleware_server.py`)
2. `middleware_server.py` — **NEW** standalone XML-RPC server process (port 9000)

### 6.1 — Create `estufa/middleware.py` (Internal Voting Logic)

Create `trabalho_pratico1/estufa/middleware.py` with **exact** content:

```python
"""
middleware.py — Internal Middleware Voting Engine.

This module is used INTERNALLY by middleware_server.py only.
External clients MUST NOT import or instantiate this class directly.
They should connect to middleware_server.py via XML-RPC on MIDDLEWARE_PORT.

Voting Algorithm (Simplified Byzantine Fault Tolerance):
  - Sends XML-RPC call to ALL controllers in parallel.
  - Collects responses within configured timeout.
  - If >= QUORUM_MINIMO concordant responses: returns the majority result.
  - If quorum not reached: raises ErroQuorum.

Fault Models Handled:
  1. Controller crash: timeout on call → controller ignored.
  2. Byzantine controller: discrepant response → outvoted by honest majority.
"""

import concurrent.futures
import collections
import json
import uuid
import xmlrpc.client
from typing import Any
from estufa import config


class ErroQuorum(Exception):
    """Raised when quorum of concordant responses cannot be reached."""
    pass


class Middleware:
    """
    Distributed invocation middleware for the controller cluster.

    Used internally by MiddlewareServer. Not a public API.
    """

    def __init__(self, controladores: list = None, timeout: int = None):
        self._controladores = controladores or config.CONTROLADORES
        self._timeout = timeout or config.TIMEOUT_RPC_SEGUNDOS

    def _criar_proxy(self, controlador: dict) -> xmlrpc.client.ServerProxy:
        """Creates an XML-RPC proxy for the specified controller."""
        url = f"http://{controlador['host']}:{controlador['port']}"
        return xmlrpc.client.ServerProxy(url, allow_none=True)

    def _chamar_controlador(self, controlador: dict, metodo: str, *args) -> Any:
        """Performs a single XML-RPC call to a controller."""
        proxy = self._criar_proxy(controlador)
        func = getattr(proxy, metodo)
        return func(*args)

    def _votar(self, metodo: str, *args) -> Any:
        """
        Core majority voting algorithm.

        Sends call to all controllers in parallel (ThreadPoolExecutor),
        waits for timeout, checks if concordant quorum exists.
        """
        resultados = []
        erros      = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._controladores)) as executor:
            futures = {
                executor.submit(self._chamar_controlador, ctrl, metodo, *args): ctrl
                for ctrl in self._controladores
            }
            for future in concurrent.futures.as_completed(futures, timeout=self._timeout + 1):
                ctrl = futures[future]
                try:
                    resultado = future.result(timeout=self._timeout)
                    resultados.append((ctrl["id"], resultado))
                except Exception as e:
                    erros.append((ctrl["id"], str(e)))
                    print(f"[MIDDLEWARE] ⚠️  Controlador {ctrl['id']} falhou: {e}")

        if not resultados:
            raise ErroQuorum(
                f"Nenhuma resposta recebida de {len(self._controladores)} controladores. "
                f"Erros: {erros}"
            )

        # ── Voting ────────────────────────────────────────────────────────────
        def _normalizar(valor: Any) -> str:
            if isinstance(valor, dict):
                copia = {k: v for k, v in valor.items()
                         if k not in ("ultima_atualizacao", "controlador_id", "_byzantino")}
                return json.dumps(copia, sort_keys=True)
            return str(valor)

        contagem = collections.Counter(_normalizar(r) for _, r in resultados)
        mais_comum, votos = contagem.most_common(1)[0]

        print(f"[MIDDLEWARE] Votos: {dict(contagem)} | Quorum mínimo: {config.QUORUM_MINIMO}")

        if votos < config.QUORUM_MINIMO:
            raise ErroQuorum(
                f"Quorum não atingido: {votos} voto(s) para a resposta mais comum "
                f"(mínimo: {config.QUORUM_MINIMO}). Respostas: {resultados}"
            )

        for _, resultado in resultados:
            if _normalizar(resultado) == mais_comum:
                return resultado

    # ─── Public API ─────────────────────────────────────────────────────────

    def obter_estado(self) -> dict:
        """Queries the current greenhouse state via majority voting."""
        return self._votar("obter_estado")

    def comandar_bomba(self, acao: str) -> dict:
        """
        Sends pump command to all controllers with a shared UUID for deduplication.
        The UUID is passed as 'comando_id' so all 3 controllers publish the same ID,
        allowing the actuator LRU cache to discard the 2 redundant MQTT publishes.
        """
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] 🆔 Gerando comando_id={comando_id[:8]}... para bomba {acao}")
        return self._votar("comandar_bomba", acao, comando_id)

    def comandar_exaustor(self, acao: str) -> dict:
        """
        Sends exhaust fan command to all controllers with a shared UUID for deduplication.
        """
        comando_id = str(uuid.uuid4())
        print(f"[MIDDLEWARE] 🆔 Gerando comando_id={comando_id[:8]}... para exaustor {acao}")
        return self._votar("comandar_exaustor", acao, comando_id)

    def verificar_saude(self) -> dict:
        """Checks which controllers are responding (health-check)."""
        saude = {}
        for ctrl in self._controladores:
            try:
                proxy = self._criar_proxy(ctrl)
                resp  = proxy.ping()
                saude[ctrl["id"]] = "ok" if "pong" in str(resp) else f"resposta inesperada: {resp}"
            except Exception as e:
                saude[ctrl["id"]] = f"OFFLINE: {e}"
        return saude
```

### 6.2 — Create `estufa/middleware_server.py` (NEW — Standalone XML-RPC Server)

Create `trabalho_pratico1/estufa/middleware_server.py` with **exact** content:

```python
"""
middleware_server.py — Standalone Middleware XML-RPC Server.

This is the MAIN ENTRY POINT for the Middleware layer.
It exposes a single XML-RPC interface on MIDDLEWARE_PORT (default: 9000).

Architecture:
  - Clients connect to THIS server via XML-RPC (never to controllers directly)
  - This server uses the internal Middleware voting engine to orchestrate
    parallel calls to all 3 controllers and returns the quorum result

  [Client] --XML-RPC:9000--> [MiddlewareServer] --XML-RPC:8001/8002/8003--> [Controllers]

Usage:
    python -m estufa.middleware_server
    python -m estufa.middleware_server --host localhost --port 9000
"""

import argparse
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from estufa.middleware import Middleware, ErroQuorum
from estufa import config


class MiddlewareService:
    """
    XML-RPC service class that wraps the internal Middleware voting engine.

    All methods exposed here are callable by clients via XML-RPC.
    Exceptions (ErroQuorum) are automatically serialized by the XML-RPC protocol
    as Fault objects, which the client's xmlrpc.client will raise as exceptions.
    """

    def __init__(self):
        self._mw = Middleware()

    def obter_estado(self) -> dict:
        """
        [XML-RPC] Queries the majority-approved greenhouse state.

        Returns:
            dict: Quorum-approved state with temperatura, umidade_solo,
                  bomba_ligada, exaustor_ligado fields.

        Raises:
            xmlrpc.client.Fault: If quorum cannot be reached.
        """
        try:
            return self._mw.obter_estado()
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_bomba(self, acao: str) -> dict:
        """
        [XML-RPC] Sends pump command to all controllers with deduplication ID.

        Args:
            acao: 'ligar' or 'desligar'

        Returns:
            dict: Quorum-approved response with 'sucesso' and 'mensagem'.
        """
        try:
            return self._mw.comandar_bomba(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def comandar_exaustor(self, acao: str) -> dict:
        """
        [XML-RPC] Sends exhaust fan command to all controllers with deduplication ID.

        Args:
            acao: 'ligar' or 'desligar'

        Returns:
            dict: Quorum-approved response with 'sucesso' and 'mensagem'.
        """
        try:
            return self._mw.comandar_exaustor(acao)
        except ErroQuorum as e:
            raise Exception(f"ERRO_QUORUM: {e}")

    def verificar_saude(self) -> dict:
        """
        [XML-RPC] Health-check: returns status of each controller replica.

        Returns:
            dict: Maps controller_id -> 'ok' or error message.
        """
        return self._mw.verificar_saude()

    def ping(self) -> str:
        """[XML-RPC] Health-check for the Middleware Server itself."""
        return "pong:middleware_server"


def iniciar_servidor(host: str = None, port: int = None) -> None:
    """
    Starts the Middleware XML-RPC server.

    Args:
        host: Host to bind. Defaults to config.MIDDLEWARE_HOST.
        port: Port to bind. Defaults to config.MIDDLEWARE_PORT.
    """
    host = host or config.MIDDLEWARE_HOST
    port = port or config.MIDDLEWARE_PORT

    class SilentHandler(SimpleXMLRPCRequestHandler):
        """Suppresses HTTP access logs."""
        def log_message(self, fmt, *args):
            pass

    server = SimpleXMLRPCServer(
        (host, port),
        requestHandler=SilentHandler,
        allow_none=True,
        logRequests=False,
    )

    service = MiddlewareService()
    server.register_instance(service)
    server.register_introspection_functions()

    print(f"[MIDDLEWARE SERVER] 🚀 Iniciando em {host}:{port}")
    print(f"[MIDDLEWARE SERVER] Orquestrando {len(config.CONTROLADORES)} controladores:")
    for ctrl in config.CONTROLADORES:
        print(f"  - {ctrl['id']} @ {ctrl['host']}:{ctrl['port']}")
    print(f"[MIDDLEWARE SERVER] Aguardando conexões de clientes em http://{host}:{port}")
    print(f"[MIDDLEWARE SERVER] Ctrl+C para encerrar.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MIDDLEWARE SERVER] 🛑 Encerrando servidor.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Middleware XML-RPC Server — Estufa Agrícola")
    parser.add_argument("--host", default=config.MIDDLEWARE_HOST, help="Server host")
    parser.add_argument("--port", default=config.MIDDLEWARE_PORT, type=int, help="Server port")
    args = parser.parse_args()

    iniciar_servidor(host=args.host, port=args.port)
```

### 6.3 — Git Commit

```bash
git add trabalho_pratico1/estufa/middleware.py trabalho_pratico1/estufa/middleware_server.py
git commit -m "feat(phase-6): add standalone middleware server (port 9000) with UUID-based command deduplication"
```

---

## Phase 7 — Client (Refactored as Dumb Client)

**Responsible Agent:** Phase 7  
**Prerequisite:** Phase 6 completed

### 7.1 — Architectural Change

The client is now a **dumb client** that simply connects to the Middleware Server at port 9000. It has **zero knowledge** of individual controllers, voting logic, or BFT. All intelligence lives in the Middleware Server.

### 7.2 — Create `estufa/cliente.py`

Create `trabalho_pratico1/estufa/cliente.py` with **exact** content:

```python
"""
cliente.py — User Interface for the Greenhouse Control System.

The client connects EXCLUSIVELY to the Middleware Server (port 9000) via XML-RPC.
It has no knowledge of individual controllers, voting, or fault tolerance.
All distributed system complexity is encapsulated in the Middleware Server.

Architecture:
    [Client] --XML-RPC:9000--> [Middleware Server @ :9000] --XML-RPC--> [Controllers]

Usage:
    python -m estufa.cliente
    python -m estufa.cliente --auto         # Auto mode: polls state every 3s
    python -m estufa.cliente --host HOST --port PORT  # Custom middleware address
"""

import argparse
import time
import xmlrpc.client
from estufa import config


class ErroMiddleware(Exception):
    """Raised when the Middleware Server is unreachable or returns an error."""
    pass


def _criar_proxy(host: str, port: int) -> xmlrpc.client.ServerProxy:
    """Creates an XML-RPC proxy connected to the Middleware Server."""
    return xmlrpc.client.ServerProxy(
        f"http://{host}:{port}",
        allow_none=True
    )


def exibir_estado(estado: dict) -> None:
    """Formats and displays the current greenhouse state."""
    print("\n" + "═" * 50)
    print("         🌿 ESTADO ATUAL DA ESTUFA 🌿")
    print("═" * 50)

    temp     = estado.get("temperatura")
    umidade  = estado.get("umidade_solo")
    bomba    = estado.get("bomba_ligada")
    exaustor = estado.get("exaustor_ligado")

    print(f"  🌡️  Temperatura:   {f'{temp:.2f}°C' if temp is not None else 'N/A'}")
    print(f"  💧 Umidade solo:  {f'{umidade:.2f}%' if umidade is not None else 'N/A'}")
    print(f"  🚿 Bomba:         {'🟢 LIGADA' if bomba else '🔴 DESLIGADA'}")
    print(f"  💨 Exaustor:      {'🟢 LIGADO' if exaustor else '🔴 DESLIGADO'}")
    print("═" * 50 + "\n")


def menu_interativo(proxy: xmlrpc.client.ServerProxy) -> None:
    """Main interactive menu loop."""
    while True:
        print("\n📋 MENU — Estufa Agrícola Distribuída")
        print(f"  [Middleware: {proxy._ServerProxy__host}]")
        print("  1. Consultar estado atual")
        print("  2. Ligar bomba de irrigação")
        print("  3. Desligar bomba de irrigação")
        print("  4. Ligar exaustor")
        print("  5. Desligar exaustor")
        print("  6. Verificar saúde dos controladores")
        print("  0. Sair")

        escolha = input("\n▶ Escolha: ").strip()

        try:
            if escolha == "1":
                estado = proxy.obter_estado()
                exibir_estado(estado)

            elif escolha == "2":
                resp = proxy.comandar_bomba("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "3":
                resp = proxy.comandar_bomba("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "4":
                resp = proxy.comandar_exaustor("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "5":
                resp = proxy.comandar_exaustor("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "6":
                saude = proxy.verificar_saude()
                print("\n🏥 Saúde dos Controladores:")
                for ctrl_id, status in saude.items():
                    icone = "🟢" if status == "ok" else "🔴"
                    print(f"  {icone} {ctrl_id}: {status}")

            elif escolha == "0":
                print("👋 Encerrando cliente.")
                break

            else:
                print("⚠️  Opção inválida.")

        except xmlrpc.client.Fault as e:
            print(f"\n❌ ERRO DO MIDDLEWARE: {e.faultString}")
            print("   O sistema não conseguiu atingir consenso. Verifique os controladores.")
        except ConnectionRefusedError:
            print(f"\n❌ MIDDLEWARE OFFLINE: Não foi possível conectar a porta {config.MIDDLEWARE_PORT}.")
            print("   Execute: python -m estufa.middleware_server")


def modo_automatico(proxy: xmlrpc.client.ServerProxy, intervalo: float = 3.0) -> None:
    """Displays greenhouse state in an auto-polling loop."""
    print(f"🤖 Modo automático: consultando a cada {intervalo}s. Ctrl+C para parar.")
    try:
        while True:
            try:
                estado = proxy.obter_estado()
                exibir_estado(estado)
            except xmlrpc.client.Fault as e:
                print(f"❌ ERRO DO MIDDLEWARE: {e.faultString}")
            except ConnectionRefusedError:
                print(f"❌ MIDDLEWARE OFFLINE em porta {config.MIDDLEWARE_PORT}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\n👋 Encerrando.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente — Estufa Agrícola Distribuída")
    parser.add_argument("--auto",      action="store_true",              help="Auto mode (polling)")
    parser.add_argument("--intervalo", type=float, default=3.0,          help="Auto mode interval (seconds)")
    parser.add_argument("--host",      default=config.MIDDLEWARE_HOST,   help="Middleware host")
    parser.add_argument("--port",      default=config.MIDDLEWARE_PORT,   type=int, help="Middleware port")
    args = parser.parse_args()

    proxy = _criar_proxy(args.host, args.port)

    if args.auto:
        modo_automatico(proxy, intervalo=args.intervalo)
    else:
        menu_interativo(proxy)
```

### 7.3 — Git Commit

```bash
git add trabalho_pratico1/estufa/cliente.py
git commit -m "feat(phase-7): refactor client as dumb XML-RPC client to middleware server (port 9000)"
```

---

## Phase 8 — Automated Tests

**Responsible Agent:** Phase 8  
**Prerequisite:** Phases 4–7 completed

### 8.1 — Create `tests/test_atuador.py` (NEW — LRU Deduplication Tests)

Create `trabalho_pratico1/tests/test_atuador.py` with **exact** content:

```python
"""
test_atuador.py — Unit tests for the Actuator LRU deduplication cache.

Tests:
  - New comando_id is accepted and processed
  - Duplicate comando_id is rejected (LRU cache hit)
  - LRU cache eviction when capacity is exceeded
  - Commands without comando_id are always processed (no ID = no dedup)
"""

import pytest
import collections
from estufa import config
from estufa.atuador import _is_duplicado, _dedup_cache


@pytest.fixture(autouse=True)
def limpar_cache():
    """Clears the LRU cache before each test to ensure isolation."""
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


class TestDeduplicacaoLRU:
    def test_novo_comando_id_nao_e_duplicado(self):
        """A fresh UUID should not be flagged as duplicate."""
        assert _is_duplicado("uuid-novo-123") is False

    def test_mesmo_comando_id_e_duplicado(self):
        """The same UUID seen twice should be flagged as duplicate on second call."""
        _is_duplicado("uuid-repetido-456")  # First call: add to cache
        assert _is_duplicado("uuid-repetido-456") is True  # Second call: duplicate

    def test_ids_diferentes_nao_sao_duplicados(self):
        """Different UUIDs should each be processed independently."""
        assert _is_duplicado("uuid-a") is False
        assert _is_duplicado("uuid-b") is False
        assert _is_duplicado("uuid-c") is False

    def test_sem_id_nunca_e_duplicado(self):
        """Commands without comando_id (empty string) should always be processed."""
        assert _is_duplicado("") is False
        assert _is_duplicado("") is False  # Even repeated empty strings are processed

    def test_cache_evicao_quando_cheio(self):
        """When cache reaches DEDUP_CACHE_SIZE, oldest entry is evicted."""
        # Fill cache to capacity
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        # Adding one more should evict the oldest (uuid-0000)
        _is_duplicado("uuid-novo-apos-cheio")
        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        # uuid-0000 should have been evicted — it should NOT be flagged as duplicate
        assert _is_duplicado("uuid-0000") is False

    def test_lru_atualiza_posicao_ao_ser_acessado(self):
        """Accessing an existing entry refreshes its LRU position (not evicted first)."""
        # Fill cache to capacity
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        # Access uuid-0000 to refresh its LRU position
        _is_duplicado("uuid-0000")  # This marks it as "recently used"

        # Add new entry — uuid-0001 should be evicted (oldest not recently accessed)
        _is_duplicado("uuid-novo-refresh-test")

        # uuid-0000 should still be in cache (was recently accessed)
        assert _is_duplicado("uuid-0000") is True

    def test_tres_publicacoes_simultaneas_do_mesmo_comando(self):
        """
        Simulates 3 controllers publishing the same comando_id (real-world scenario).
        Only the first should be processed; the other two should be duplicates.
        """
        shared_id = "uuid-middleware-gerado-xyz"

        result_ctrl1 = _is_duplicado(shared_id)  # First: not duplicate
        result_ctrl2 = _is_duplicado(shared_id)  # Second: duplicate
        result_ctrl3 = _is_duplicado(shared_id)  # Third: duplicate

        assert result_ctrl1 is False  # Processed
        assert result_ctrl2 is True   # Discarded
        assert result_ctrl3 is True   # Discarded
```

### 8.2 — Update `tests/test_controlador.py`

The test file needs a minor update to accommodate the new `skip_sync=True` parameter and the updated `comandar_bomba(acao, comando_id)` signature.

Key changes:
- In `servidor_xmlrpc` fixture: call `ctrl.iniciar(host, port, skip_sync=True)` to bypass state sync
- In `test_comandar_bomba_ligar`: pass `comando_id=""` as second argument
- The internal `_decidir_atuacao` test fixture needs `_mqtt_client = _MqttFake()` (already has this)

> **Note:** The existing `test_controlador.py` tests still pass because `comandar_bomba(acao, comando_id="")` has a default empty string value. Only the XML-RPC-via-proxy tests need the `skip_sync` flag.

### 8.3 — Update `tests/test_middleware.py`

The `test_middleware.py` tests continue to test the **internal** `Middleware` class directly (voting logic). No structural changes needed, but `_ControladorFake.comandar_bomba` must accept the new `comando_id` parameter:

```python
# In _ControladorFake:
def comandar_bomba(self, acao, comando_id=""):
    if self.byzantino:
        return {"sucesso": True, "mensagem": "FALSO", "byzantino": True}
    self._estado["bomba_ligada"] = (acao == "ligar")
    return {"sucesso": True, "mensagem": f"Bomba {acao}da"}

def comandar_exaustor(self, acao, comando_id=""):
    if self.byzantino:
        return {"sucesso": True, "mensagem": "FALSO", "byzantino": True}
    self._estado["exaustor_ligado"] = (acao == "ligar")
    return {"sucesso": True, "mensagem": f"Exaustor {acao}do"}
```

### 8.4 — Git Commit

```bash
git add trabalho_pratico1/tests/
git commit -m "feat(phase-8): add test_atuador for LRU dedup; update test_controlador and test_middleware for new signatures"
```

---

## Phase 9 — Launch Scripts

**Responsible Agent:** Phase 9  
**Prerequisite:** Phase 8 completed

### 9.1 — Critical Boot Sequence

```
Step 1: docker compose up -d          → Broker MQTT
Step 2: python -m estufa.middleware_server  → Middleware (port 9000) — MUST be BEFORE controllers
Step 3: python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
Step 4: python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
Step 5: python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
Step 6: python -m estufa.atuador
Step 7: python -m estufa.sensor --modo normal
Step 8: python -m estufa.cliente      → Client (connects to middleware:9000)
```

> **Important:** The Middleware Server (Step 2) must start before the Controllers (Steps 3–5), because controllers perform boot-time state synchronization by querying the Middleware.

### 9.2 — Create `scripts/start_all.sh` (Linux/macOS)

Create `trabalho_pratico1/scripts/start_all.sh`:

```bash
#!/bin/bash
# start_all.sh — Starts all components of the Distributed Greenhouse System
# Correct boot order: Broker → Middleware → Controllers → Actuator → Sensor
# Client must be started manually after this script.

set -e  # Exit on error

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODO_SENSOR="${1:-normal}"

echo "🌿 Iniciando Sistema Estufa Agrícola Distribuída..."
echo ""

# ── Verify Docker ──────────────────────────────────────────────
echo "[0/7] Verificando Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon não está rodando. Inicie o Docker e tente novamente."
    exit 1
fi
echo "✅ Docker OK"

# ── Step 1: MQTT Broker ────────────────────────────────────────
echo "[1/7] Iniciando broker MQTT (Docker)..."
cd "$ROOT" && docker compose up -d
sleep 2
echo "✅ Broker MQTT iniciado."

# ── Step 2: Middleware Server (MUST come before controllers) ───
echo "[2/7] Iniciando Middleware Server (porta 9000)..."
cd "$ROOT" && python -m estufa.middleware_server &
PIDS=($!)
sleep 1
echo "✅ Middleware Server iniciado (PID: ${PIDS[-1]})."

# ── Steps 3-5: Controllers (will sync state from Middleware) ───
echo "[3/7] Iniciando Controladores (3 réplicas — com state sync)..."
cd "$ROOT" && python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json &
PIDS+=($!)
sleep 1

# ── Step 6: Actuator ───────────────────────────────────────────
echo "[4/7] Iniciando Atuador (com deduplicação LRU)..."
cd "$ROOT" && python -m estufa.atuador &
PIDS+=($!)
sleep 0.5

# ── Step 7: Sensor ─────────────────────────────────────────────
echo "[5/7] Iniciando Sensor (modo: $MODO_SENSOR)..."
cd "$ROOT" && python -m estufa.sensor --modo "$MODO_SENSOR" &
PIDS+=($!)

echo ""
echo "✅ Sistema totalmente inicializado!"
echo ""
echo "PIDs dos processos: ${PIDS[@]}"
echo ""
echo "Para iniciar o cliente:"
echo "    python -m estufa.cliente"
echo ""
echo "Para parar todos os processos:"
echo "    kill ${PIDS[@]}"
echo "    docker compose down"
```

### 9.3 — Create `scripts/start_all.ps1` (Windows)

Create `trabalho_pratico1/scripts/start_all.ps1`:

```powershell
<#
.SYNOPSIS
    Starts all components of the Distributed Greenhouse System.
.DESCRIPTION
    Boot order: Broker → Middleware Server → Controllers → Actuator → Sensor
    Client must be started manually.
.PARAMETER modo_sensor
    Sensor profile: normal, seco, quente, frio (default: normal)
#>
param(
    [ValidateSet("normal","seco","quente","frio")]
    [string]$modo_sensor = "normal"
)

$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "🌿 Iniciando Sistema Estufa Agrícola Distribuída..." -ForegroundColor Green

# 0. Verify Docker
Write-Host "[0/7] Verificando Docker..." -ForegroundColor Cyan
try { docker info > $null 2>&1 } catch {
    Write-Host "❌ Docker não está rodando." -ForegroundColor Red
    exit 1
}

# 1. Broker MQTT
Write-Host "[1/7] Iniciando broker MQTT..." -ForegroundColor Cyan
Push-Location $ROOT; docker compose up -d; Pop-Location
Start-Sleep -Seconds 2

# 2. Middleware Server (MUST be before controllers)
Write-Host "[2/7] Iniciando Middleware Server (porta 9000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.middleware_server`"" -WindowStyle Normal
Start-Sleep -Seconds 1

# 3-5. Controllers
Write-Host "[3/7] Iniciando Controladores (3 réplicas)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json`"" -WindowStyle Normal
Start-Sleep -Seconds 1

# 6. Actuator
Write-Host "[4/7] Iniciando Atuador..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.atuador`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500

# 7. Sensor
Write-Host "[5/7] Iniciando Sensor (modo: $modo_sensor)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.sensor --modo $modo_sensor`"" -WindowStyle Normal

Write-Host ""
Write-Host "✅ Sistema inicializado!" -ForegroundColor Green
Write-Host "Para iniciar o cliente:" -ForegroundColor Yellow
Write-Host "    python -m estufa.cliente" -ForegroundColor White
```

### 9.4 — Git Commit

```bash
git add trabalho_pratico1/scripts/
git commit -m "feat(phase-9): update launch scripts with correct boot order (middleware before controllers)"
```

---

## Phase 10 — README Update

**Responsible Agent:** Phase 10  
**Prerequisite:** All previous phases completed

Update `trabalho_pratico1/README.md` with the new architecture:

Key sections to update:
- Architecture diagram showing `[Client] → [Middleware:9000] → [Controllers:8001-8003]`
- Boot sequence instructions (middleware first)
- Description of the 3 architectural fixes
- Updated component table with `middleware_server.py`

### 10.1 — Git Commit

```bash
git add trabalho_pratico1/README.md
git commit -m "docs(phase-10): update README with new middleware architecture, boot sequence, and deduplication"
```

---

## Validation Strategy

### Automated Tests

```bash
# From trabalho_pratico1/
# Run all unit tests (no Docker required):
pytest tests/test_atuador.py -v      # LRU deduplication tests
pytest tests/test_controlador.py -v  # Controller logic + XML-RPC
pytest tests/test_middleware.py -v   # Voting engine (BFT + quorum)

# Run integration tests (Docker broker required):
docker compose up -d
pytest tests/test_integracao.py -v
docker compose down
```

### Manual System Validation

#### 1. Normal Operation
```bash
# Terminal 1 (from trabalho_pratico1/):
docker compose up -d
python -m estufa.middleware_server

# Terminal 2:
python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json

# Terminal 3:
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json

# Terminal 4:
python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json

# Terminal 5:
python -m estufa.atuador

# Terminal 6:
python -m estufa.sensor --modo seco  # Triggers pump (humidity < 30%)

# Terminal 7:
python -m estufa.cliente  # Select option 1: check state
```

#### 2. Byzantine Fault Tolerance Test
```bash
# While system is running, stop ctrl_2 and restart in Byzantine mode:
# (Kill ctrl_2 terminal, then:)
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino

# From client (option 1): State should show correct values (NOT 999°C)
# Middleware log should show: ctrl_2 voted [temp=999, umid=-1], outvoted by ctrl_1 + ctrl_3
```

#### 3. Crash Recovery & State Sync Test
```bash
# 1. Let the system run until state is established (e.g., bomba_ligada=True)
# 2. Kill ctrl_1:
kill <ctrl_1_pid>

# 3. Verify system still works (ctrl_2 + ctrl_3 maintain quorum):
python -m estufa.cliente  # Option 1: state should be consistent

# 4. Restart ctrl_1 (it will sync state from Middleware):
python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
# Expected log: "[ctrl_1] ✅ Estado sincronizado com sucesso"
# Expected: ctrl_1 JSON file updated to match cluster state

# 5. Verify ctrl_1 is back in sync:
python -m estufa.cliente  # Option 6: health check — all 3 should be "ok"
```

#### 4. MQTT Deduplication Verification
```bash
# While system is running with sensor in 'seco' mode:
# Actuator terminal should show ONE processing line + TWO "duplicado ignorado" lines
# per sensor reading cycle:
#
# [ATUADOR] 💧 Bomba de Irrigação → LIGADA (origem: ctrl_1)
# [ATUADOR] 🔁 Comando duplicado ignorado: a1b2c3d4... (tópico: estufa/atuadores/bomba)
# [ATUADOR] 🔁 Comando duplicado ignorado: a1b2c3d4... (tópico: estufa/atuadores/bomba)
```

#### 5. Quorum Loss Test (2 controllers down)
```bash
# Kill ctrl_2 and ctrl_3 (only ctrl_1 remains):
# From client: should receive an error message (quorum not reached)
# [Client]: ❌ ERRO DO MIDDLEWARE: ERRO_QUORUM: Quorum não atingido...
```

---

## Summary of Changes vs. Original Plan

| Aspect | Original Plan v1 | Updated Plan v2 |
|---|---|---|
| Middleware type | Python library (`import Middleware`) | Standalone XML-RPC server (`:9000`) |
| Client connects to | Instantiates `Middleware()` directly | `http://localhost:9000` |
| Boot sequence | No order guarantee | Middleware → Controllers → Others |
| Controller boot | Loads local JSON or empty state | Syncs state from Middleware (with retries) |
| MQTT commands | All 3 publish; actuator processes 3x | Unique UUID `comando_id`; actuator LRU deduplicates |
| New files | — | `middleware_server.py`, `test_atuador.py` |
| Config additions | — | `MIDDLEWARE_PORT=9000`, `DEDUP_CACHE_SIZE=50` |
| `.gitignore` | Not present | Added (pycache, broker data, JSON state files) |
| Git commits | Not specified | Explicit commit at end of each phase |
