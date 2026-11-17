# Proposal: Refactor Core Distributed Controllers, Embedded Middleware & Consensus Persistence

> **Change ID:** `refactor-core-distributed-controllers`
> **Status:** approved
> **Author:** @anybo
> **Created:** 2026-11-17
> **Last Updated:** 2026-11-17

---

## Summary

Eliminates the standalone `estufa/middleware_server.py` (`:9000`) single point of failure and refactors `estufa/config.py`, `estufa/middleware.py`, `estufa/controlador.py`, and `estufa/cliente.py` so that the Middleware operates as an embedded logical XML-RPC layer distributed across the controllers and client. Implements Bully leader election among the 3 controllers (`:8001`, `:8002`, `:8003`), leader-coordinated dynamic-quorum consensus ($2/3$ majority when 3 nodes are active to mask 1 Byzantine node, $2/2$ when 2 are active, and $1/1$ degraded mode when 1 survives), synchronous `commit_estado` replication to keep `data_ctrl_1.json`, `data_ctrl_2.json`, and `data_ctrl_3.json` identical, automatic state synchronization when a crashed replica reconnects, leader-only MQTT actuation publishing, and transparent client failover across active controllers.

## Motivation

- During the partial presentation of Trabalho Prático 1, the professor identified that having `estufa/middleware_server.py` on port `9000` as an external intermediary process violates the architecture in Figure 1 of `Trabalho Prático 1 - SD.pdf`, where `MIDDLEWARE` encloses the process controllers themselves (`Controlador de Processo 1..N`) with direct Client-to-Controller RPC and peer-to-peer Controller-to-Controller synchronization/fault tolerance.
- In the current codebase, killing `:9000` stops the entire client and replica recovery path (Single Point of Failure), controllers never communicate peer-to-peer or elect a leader, and each controller writes independently to its local `data_ctrl_X.json` without consensus—causing silent divergence across replicas (e.g., `data_ctrl_2.json` diverging from `data_ctrl_1.json` and `data_ctrl_3.json`).
- During the live re-presentation, the professor will terminate services one by one to verify autonomous leader failover, dynamic consensus, Byzantine fault isolation, consistent replicated databases, and automatic resynchronization upon process restart.

## Scope

### In Scope
- Delete `trabalho_pratico1/estufa/middleware_server.py` (removing port `9000` process).
- Refactor `trabalho_pratico1/estufa/config.py` to remove `MIDDLEWARE_HOST`/`MIDDLEWARE_PORT` and define `MAPA_CONTROLADORES` (`1..3` mapping to `id`, `host`, `port`, `data_file`), RPC timeouts, and heartbeat/election intervals.
- Refactor `trabalho_pratico1/estufa/middleware.py` into an embedded logical RPC coordination and client failover library (`ClusterMiddleware`, `ErroQuorum`, `_TimeoutTransport`) used directly by `cliente.py` and `controlador.py`.
- Refactor `trabalho_pratico1/estufa/controlador.py` to implement:
  - Simplified CLI entrypoint supporting `python -m estufa.controlador <1|2|3> [--byzantino]` (while keeping optional host/port flags if needed).
  - Bully leader election (`ping()`, `iniciar_eleicao(id_origem)`, `anunciar_lider(id_lider)`) and periodic heartbeat monitoring of the current leader.
  - Peer-to-peer dynamic-quorum consensus validation before state persistence (`coletar_voto_estado()` / `propor_atualizacao()`), rejecting corrupted `--byzantino` values when majority agrees.
  - Synchronous state commit (`commit_estado(estado_oficial)`) from leader to all active followers so all active `data_ctrl_*.json` files persist identical official data.
  - Leader-only MQTT actuation command publishing (`estufa/atuadores/bomba` and `estufa/atuadores/exaustor`).
  - Automatic boot/reconnection state synchronization directly from active peer controllers/leader without `--skip-sync` or `:9000`.
- Refactor `trabalho_pratico1/estufa/cliente.py` to communicate directly via XML-RPC with `CONTROLADORES` (`8001..8003`), automatically discovering the leader and failing over transparently on connection refused, socket timeout, or OS errors.
- Update unit and integration tests in `trabalho_pratico1/tests/test_middleware.py` and `trabalho_pratico1/tests/test_controlador.py`.

### Out of Scope
- Simplifying `estufa/sensor.py` (removing `PERFIS` / `--modo` for continuous closed-loop operation) and simplifying `estufa/atuador.py` / `estufa/broker_local.py` — scheduled for Change 2 (`simplify-components-and-tests`).
- Updating Windows 11 / Linux launch scripts (`scripts/start_all.ps1`, `scripts/start_all.sh`, `scripts/reset_demo.ps1`, `scripts/validate_e2e.py`), `.vscode/tasks.json`, and academic docs (`README.md`, `relatorio.md`, `roteiro_apresentacao.md`) — scheduled for Change 3 (`prepare-interactive-windows-demo-and-docs`).

## Proposed Solution

### Approach
1. **Embedded Logical Middleware (`estufa/middleware.py` & `estufa/config.py`):**
   - Replace the `:9000` centralized gateway with `MAPA_CONTROLADORES` in `config.py` (`1` -> `ctrl_1`, `localhost:8001`, `data_ctrl_1.json`; `2` -> `ctrl_2`, `localhost:8002`, `data_ctrl_2.json`; `3` -> `ctrl_3`, `localhost:8003`, `data_ctrl_3.json`), `TIMEOUT_RPC_SEGUNDOS = 1.5`, and `INTERVALO_HEARTBEAT_SEGUNDOS = 2.0`.
   - `estufa/middleware.py` retains `_TimeoutTransport` (for bounded non-blocking socket calls on Windows) and `ErroQuorum`, and provides direct multi-node XML-RPC helpers (`ClusterMiddleware`) used by `cliente.py` for leader discovery and automatic failover across `CONTROLADORES`, and by `controlador.py` for peer-to-peer RPC calls.

2. **Bully Leader Election (`estufa/controlador.py`):**
   - Each controller has a numeric rank matching its ID (`1 < 2 < 3`; highest active controller ID is elected leader).
   - A background daemon thread monitors the current leader every `INTERVALO_HEARTBEAT_SEGUNDOS` using `ping()`. If the leader fails to respond (or if no leader is known yet), the controller starts a Bully election: it sends `iniciar_eleicao(meu_rank)` to all peers with higher rank; if none respond, it declares itself leader and broadcasts `anunciar_lider(meu_id)` to lower-ranked peers.
   - If a higher-ranked controller restarts after a crash, it first synchronizes its official state from the active cluster and then runs a Bully election to assume or confirm leadership seamlessly.

3. **Dynamic Quorum Consensus & Replicated Persistence (`estufa/controlador.py`):**
   - All 3 controllers subscribe to MQTT sensor topics (`estufa/sensores/temperatura` and `estufa/sensores/umidade_solo`) and buffer/track the latest local observation and proposed actuator decision under `self._lock`.
   - When telemetry is processed or a client invokes a manual command (`comandar_atuador` / `comandar_bomba` / `comandar_exaustor`), if the request lands on a follower, the follower forwards it to the current leader (triggering election first if the leader just died).
   - The **Leader** coordinates consensus by querying active peers via XML-RPC (`coletar_voto_estado()`), receiving each peer's current sensor/command proposal (a `--byzantino` controller returns tampered readings or inverted actuator states).
   - **Dynamic Quorum Rule:**
     - **3 active nodes:** requires $\ge 2$ matching votes (majority masks 1 `--byzantino` node). If all 3 disagree (e.g., 2 distinct Byzantine faults), raises `ErroQuorum` and aborts commit.
     - **2 active nodes:** requires agreement between the 2 active nodes ($2/2$) to commit normal consensus; if they diverge during an explicit fault test, raises `ErroQuorum` or preserves last safe consistent state.
     - **1 active node (degraded mode):** when 2 peers are closed by the professor, the sole surviving controller acts as leader in $1/1$ degraded mode (as long as it is not isolated by a conflicting majority), persisting state and keeping the greenhouse operational.
   - Once consensus produces `estado_oficial`, the Leader calls `commit_estado(estado_oficial)` via XML-RPC on every reachable follower and writes `estado_oficial` to its own `data_ctrl_X.json`. Followers write the exact `estado_oficial` to their `data_ctrl_X.json`, eliminating JSON divergence.
   - **Leader-Only MQTT Actuation:** Only the Leader publishes actuation commands to `estufa/atuadores/bomba` and `estufa/atuadores/exaustor` after consensus succeeds.
   - **Boot / Reconnection Sync:** On startup (replacing `_sincronizar_estado_via_middleware` and `--skip-sync`), a controller queries active peers directly over XML-RPC (`obter_estado_cluster()`), overwrites its local `data_ctrl_X.json` with the cluster's official state before participating in elections/voting.

4. **Direct Client RPC & Failover (`estufa/cliente.py`):**
   - `cliente.py` uses `ClusterMiddleware` to discover the current leader (or query any reachable controller in `8001..8003`).
   - If the active controller/leader crashes mid-session or refuses connection (`ConnectionRefusedError`, `TimeoutError`, `socket.timeout`, `OSError`), `ClusterMiddleware` transparently fails over to the remaining controllers, triggers/awaits election resolution if needed, and retries the operation without exposing `:9000` or topology details to the user.

### Impacted Files
| File | Change Type | Notes |
|------|-------------|-------|
| `trabalho_pratico1/estufa/middleware_server.py` | Delete | Remove standalone `:9000` intermediary SPOF process |
| `trabalho_pratico1/estufa/config.py` | Modify | Remove `MIDDLEWARE_HOST`/`MIDDLEWARE_PORT`; add `MAPA_CONTROLADORES` and heartbeat/election constants |
| `trabalho_pratico1/estufa/middleware.py` | Modify | Refactor into embedded logical RPC/failover/voting helpers used by client and controllers |
| `trabalho_pratico1/estufa/controlador.py` | Modify | Add Bully leader election, peer consensus voting, `commit_estado` DB replication, leader-only MQTT publishing, boot sync from peers, and simplified `1|2|3` CLI |
| `trabalho_pratico1/estufa/cliente.py` | Modify | Connect directly to controllers (`8001..8003`) with transparent leader discovery and failover |
| `trabalho_pratico1/tests/test_middleware.py` | Modify | Rewrite/update unit tests for direct controller failover, dynamic quorum (3/3, 2/3 Byzantine, 2/2, 1/1), and `ErroQuorum` |
| `trabalho_pratico1/tests/test_controlador.py` | Modify | Add unit/integration tests for Bully election, leader failover, consensus commit across `data_ctrl_*.json`, and reconnection state sync |

### Data Model Changes (if applicable)
- Replicated JSON state (`data_ctrl_1.json`, `data_ctrl_2.json`, `data_ctrl_3.json`) stores canonical fields:
  - `temperatura`: `float | None`
  - `umidade`: `float | None`
  - `bomba_ligada`: `bool`
  - `exaustor_ligado`: `bool`
  - `ultima_atualizacao`: `str | None` (ISO-8601 timestamp)
  - `lider_id`: `str | None` (e.g., `"ctrl_3"`, replacing legacy `"controlador_id"`)

## Acceptance Criteria

- [ ] **Given** `middleware_server.py` has been removed and no process listens on port `9000`, **When** the 3 controllers (`ctrl_1`..`ctrl_3` on `8001..8003`) and `cliente.py` are started, **Then** `cliente.py` queries state and triggers manual commands directly via XML-RPC to the active controllers without referencing `:9000`.
- [ ] **Given** 3 active controllers (`ctrl_1`, `ctrl_2`, `ctrl_3`) with `ctrl_3` elected as leader via Bully algorithm, **When** `ctrl_3` crashes or is terminated, **Then** `ctrl_1` and `ctrl_2` detect the failure via heartbeat/RPC error, elect `ctrl_2` as the new leader, and continue processing MQTT telemetry and client RPC requests seamlessly.
- [ ] **Given** 3 active controllers receiving sensor telemetry or a client command, **When** the leader runs consensus validation, **Then** the leader persists the agreed official state via `commit_estado` so `data_ctrl_1.json`, `data_ctrl_2.json`, and `data_ctrl_3.json` contain identical `temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`, and `lider_id` values, and only the leader publishes the actuation command to MQTT.
- [ ] **Given** 3 active controllers where 1 controller is started with `--byzantino` (returning tampered readings/decisions), **When** consensus voting runs across the 3 nodes, **Then** the 2 honest controllers form a $2/3$ majority, reject the Byzantine payload, and persist only the valid official state in honest replicated JSON databases.
- [ ] **Given** controllers are terminated sequentially one by one during presentation, **When** 2 controllers remain active ($2/2$) and then 1 controller remains active ($1/1$ degraded mode), **Then** the surviving controller(s) elect a leader, preserve availability for client RPC and MQTT control, and persist state locally.
- [ ] **Given** a controller was stopped while the remaining cluster processed state updates, **When** the stopped controller is restarted, **Then** it synchronizes its local `data_ctrl_X.json` directly from the active leader/peers on startup so its database matches the cluster before resuming participation.

## Defensive Security & Validation Considerations

### Input Validation
- Validate controller IDs on CLI and RPC inputs (`1`, `2`, `3` or `ctrl_1`..`ctrl_3`), rejecting unknown controller identifiers or out-of-range ranks (`ValueError`).
- Validate manual actuator targets (`"bomba"`, `"exaustor"`) and boolean command values (`isinstance(ligar, bool)`), as well as sensor payload bounds (numeric `float` values for temperature/humidity, ignoring malformed JSON MQTT payloads).
- Validate `commit_estado` and `obter_estado` payloads contain expected schema keys and types before writing to `data_ctrl_*.json`.

### Secret Isolation
- N/A — no passwords, API keys, tokens, or external credentials are used or hardcoded; configuration holds only localhost ports and filenames.

### Authorization & Authentication Impact
- N/A — local academic distributed systems simulation bound strictly to `127.0.0.1` (`localhost`). Integrity against compromised/faulty nodes (`--byzantino`) is enforced through majority consensus voting prior to persistence and actuation.

### Other Security Risks
- **Socket Hang / DoS Prevention:** All peer-to-peer and client XML-RPC calls use `_TimeoutTransport` (`TIMEOUT_RPC_SEGUNDOS = 1.5`) so dead or hung sockets never freeze the controller or client threads.
- **Race Conditions & State Corruption:** Shared controller state (`self._estado`, `self._lider_id`) is guarded by `threading.RLock`/`threading.Lock`, and JSON persistence uses atomic write or locked file serialization so concurrent RPC and MQTT threads cannot corrupt `data_ctrl_*.json`.
- **Loopback Isolation:** XML-RPC servers bind exclusively to `localhost` (`127.0.0.1`), preventing exposure on external lab networks.

## Testing Strategy & Shift-Left Plan

### Happy Path Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TP-01 | Bully election on 3-controller cluster startup | Unit / Integration | Highest-rank active controller (`ctrl_3`) is elected leader and announced to peers |
| TP-02 | Leader-coordinated consensus & `commit_estado` persistence | Integration | Leader collects votes, commits official state, and `data_ctrl_1.json`..`data_ctrl_3.json` are identical |
| TP-03 | Client direct RPC read and command routing without `:9000` | Unit / Integration | `ClusterMiddleware` / `cliente.py` discovers active leader and executes `obter_estado` / `comandar_*` |
| TP-04 | Leader-only MQTT actuation emission | Unit | Only the leader publishes to `estufa/atuadores/*`; followers update state via `commit_estado` without duplicate MQTT publishes |

### Edge Case & Failure Mode Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TE-01 | Leader (`ctrl_3`) crashes -> failover election & client retry | Integration | `ctrl_2` becomes leader, client seamlessly fails over to `ctrl_2`, and operations succeed |
| TE-02 | 1 Byzantine controller (`--byzantino`) among 3 active nodes | Unit / Integration | 2/3 honest majority discards tampered data and persists official state |
| TE-03 | Sequential degradation down to 2 active ($2/2$) and 1 active ($1/1$) | Integration | Last surviving controller assumes degraded leadership ($1/1$) and continues serving |
| TE-04 | Divergent 2-node tie or total cluster unavailability (0 active / quorum impossible) | Unit | Raises `ErroQuorum` cleanly without corrupting persisted JSON files |
| TE-05 | Crashed replica reconnects after cluster state evolved | Integration | Reconnecting controller pulls official state from leader/peers and syncs `data_ctrl_X.json` |

### Test Commands
- **Run tests:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v`
- **Coverage check:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests\test_middleware.py .\trabalho_pratico1\tests\test_controlador.py -v`

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Deadlock when two controllers call XML-RPC peer methods while holding `self._lock` | Med | High | Never hold `self._lock` during outbound XML-RPC calls; snapshot state under lock, perform network RPC outside lock, then re-acquire lock to apply result |
| Split-brain or concurrent elections during rapid node restarts | Med | Med | Deterministic Bully rank order (`ctrl_3 > ctrl_2 > ctrl_1`), bounded RPC timeouts (`1.5s`), and serialization lock around election transitions |
| Windows firewall or slow TCP RST delaying failover | Low | Med | Bind strictly to `127.0.0.1` (`localhost`) and use explicit `_TimeoutTransport` on every `ServerProxy` |

## Specification Changes & Delta Stubs

### `specs/distributed-controllers-consensus.md`
- **Target Canonical Spec:** `New Specification` (`openspec/specs/distributed-controllers-consensus.md`)
- **Summary of Updates:** Defines functional and non-functional requirements for embedded XML-RPC middleware, Bully leader election, dynamic-quorum consensus validation before JSON persistence, replica recovery sync, and direct client failover.

## References

- `trabalho_pratico1/Trabalho Prático 1 - SD.pdf` (Figure 1 architectural diagram and problem statements)
- `trabalho_pratico1/prompt.md` (Professor feedback and refactoring goals)
- `openspec/specs/sdd-stack-contract.md`
