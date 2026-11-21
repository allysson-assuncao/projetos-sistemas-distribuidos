# Proposal: Simplify TP1 for Oral Defense

> **Change ID:** `simplify-tp1-for-defense`
> **Status:** draft
> **Author:** @anybo
> **Created:** 2026-11-21
> **Last Updated:** 2026-11-21

---

## Summary

Simplifies the core Python implementation of `trabalho_pratico1` (`estufa/config.py`, `estufa/sensor.py`, `estufa/middleware.py`, `estufa/controlador.py`, and `estufa/cliente.py`) by replacing unnecessary concurrency boilerplate (`ThreadPoolExecutor` / `as_completed` / `lambda` blocks), pre-consensus follower state mutations, multi-branch synchronization heuristics, thread-scoped temp-file retry loops, and dead/legacy fallback code with linear, readable, and easy-to-defend code—while preserving 100% of the distributed systems requirements (MQTT pub/sub, XML-RPC embedded middleware, Bully leader election, dynamic quorum consensus, JSON state replication, reconnection sync, and `--byzantino` fault masking) and synchronizing all defense documentation with exact line numbers and a Defense Survival Guide.

## Motivation

During the upcoming individual oral defense at the lab desk, the professor inspects source files line-by-line, asks why each architectural/code decision was made, and kills processes live to verify failure handling, leader election, reconnection sync, and Byzantine fault tolerance. Over-engineered constructs generated during rapid AI-assisted development (`ThreadPoolExecutor` instantiated on every heartbeat/sensor cycle, `.tmp` files using `threading.get_ident()` with 5-attempt `PermissionError` retries, heuristic fallback sorting tuples in `_sincronizar_com_cluster`, unused constants like `QUORUM_MINIMO`, and random sensor drift with internal locks) obscure the core distributed systems algorithms and create unnecessary risk during oral questioning.

## Scope

### In Scope
- Remove unused constant `QUORUM_MINIMO` and reduce `TIMEOUT_RPC_SEGUNDOS` from `1.5` to `0.6`s in `trabalho_pratico1/estufa/config.py` for fast sequential localhost RPC loops.
- Simplify `trabalho_pratico1/estufa/sensor.py` (`SimuladorAmbiente`) to deterministic steps (`+2.0°C`/`-2.5°C` and `-3.0%`/`+6.0%`) without `random` or internal `threading.Lock`, keeping input validation and closed-loop MQTT feedback.
- Simplify `trabalho_pratico1/estufa/middleware.py` (`ClusterMiddleware`) by replacing `ThreadPoolExecutor` / `as_completed` with clean sequential loops, simplifying `_normalizar_estado` / `_normalizar_lista_controladores`, and removing unused `total_ativos` and legacy `"pong"` check.
- Simplify `trabalho_pratico1/estufa/controlador.py` by replacing all 5 `ThreadPoolExecutor` blocks with clean sequential loops, removing pre-consensus state mutation in `_on_message`, simplifying `_sincronizar_com_cluster` to use `ClusterMiddleware.calcular_consenso()`, simplifying `_salvar_estado` to direct `json.dump()` under `self._lock`, deduplicating Byzantine payload generation and follower-to-leader RPC forwarding, and removing dead/legacy code (`lider_descoberto`, `"umidade_solo"`).
- Remove legacy `"umidade_solo"` fallback in `trabalho_pratico1/estufa/cliente.py`.
- Verify/update unit tests (`trabalho_pratico1/tests/`) and run full `pytest` + `scripts/validate_e2e.py`.
- Update line numbers across `revisao_defesa_tp1.md`, `roteiro_apresentacao.md`, `relatorio/relatorio.md`, `README.md`, and `trabalho_pratico1_codigo_completo.txt`, and enrich `revisao_defesa_tp1.md` with a Defense Survival Guide.

### Out of Scope
- Removing `estufa/broker_local.py` (needed for Docker-free Windows lab execution).
- Altering `scripts/start_all.ps1`, `scripts/start_all.sh`, `scripts/reset_demo.ps1`, or `estufa/atuador.py`.
- Changing the 7-process architecture, MQTT topics, XML-RPC ports (`8001..8003`), or Bully/Quorum semantics.

## Proposed Solution

### Approach
Refactor the core modules sequentially from configuration/sensor up to middleware/controller/client, keeping all external XML-RPC signatures (`ping`, `iniciar_eleicao`, `anunciar_lider`, `coletar_voto_estado`, `commit_estado`, `obter_estado`, `comandar_bomba`, `comandar_exaustor`), MQTT topics, and CLI flags intact.

Replacing `ThreadPoolExecutor` with straightforward `for` loops over at most 2–3 localhost peers with a `0.6s` socket timeout eliminates ~150 lines of concurrency boilerplate and makes every execution path linear and self-documenting, while still keeping worst-case failure detection bounded well under 2 seconds. Fixing `_on_message` so that only the leader builds a proposed state and `self._estado` only mutates inside `commit_estado` aligns the code strictly with the replicated state machine model taught in class.

### Impacted Files
| File | Change Type | Notes |
|------|-------------|-------|
| `trabalho_pratico1/estufa/config.py` | Modify | Set `TIMEOUT_RPC_SEGUNDOS = 0.6`; remove unused `QUORUM_MINIMO` |
| `trabalho_pratico1/estufa/sensor.py` | Modify | Deterministic steps (`+2.0/-2.5°C`, `-3.0/+6.0%`); remove `random` and `threading.Lock` |
| `trabalho_pratico1/estufa/middleware.py` | Modify | Sequential RPC loops; clean `_normalizar_estado`; remove `total_ativos` & `"pong"` check |
| `trabalho_pratico1/estufa/controlador.py` | Modify | Sequential peer RPC loops; fix pre-consensus mutation; direct `json.dump`; clean `_sincronizar_com_cluster`; deduplicate Byzantine/forwarding |
| `trabalho_pratico1/estufa/cliente.py` | Modify | Remove legacy `"umidade_solo"` fallback |
| `trabalho_pratico1/tests/test_middleware.py` | Modify | Ensure timeout/quorum test aligns with sequential `0.6s`/mocked timeout behavior |
| `trabalho_pratico1/tests/test_sensor.py` | Modify | Verify deterministic step assertions if any test assumed random drift bounds |
| `trabalho_pratico1/tests/test_controlador.py` | Modify | Verify all controller tests pass without pre-consensus mutation or legacy fallbacks |
| `trabalho_pratico1/revisao_defesa_tp1.md` | Modify | Update exact line mappings (`Lxx–Lyy`) and add Defense Survival Guide |
| `trabalho_pratico1/roteiro_apresentacao.md` | Modify | Update exact line references across Steps 1–7 |
| `trabalho_pratico1/relatorio/relatorio.md` | Modify | Update `TIMEOUT_RPC_SEGUNDOS = 0.6`, remove `QUORUM_MINIMO`, update sensor description |
| `trabalho_pratico1/README.md` | Modify | Update config/sensor notes if referenced |
| `trabalho_pratico1/trabalho_pratico1_codigo_completo.txt` | Modify | Regenerate numbered full source listing and index table |

### Data Model Changes (if applicable)
None. JSON state files (`data_ctrl_1..3.json`) preserve the exact schema (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`, `ultima_atualizacao`, `lider_id`).

## Acceptance Criteria

- [ ] **Given** a running 3-controller cluster (`ctrl_1..3`) with `broker_local`, **When** `sensor.py` publishes readings and `atuador.py` confirms actuation, **Then** `sensor.py` advances deterministically (`+2.0°C`/`-2.5°C`, `-3.0%`/`+6.0%`) and all 3 `data_ctrl_*.json` files persist identical state exclusively via consensus + `commit_estado` without pre-consensus follower mutation.
- [ ] **Given** `ctrl_3` (leader) is terminated while `ctrl_1` and `ctrl_2` remain active, **When** heartbeat detects the failure or a client invokes `ClusterMiddleware`, **Then** `ctrl_2` wins Bully election via sequential peer RPC calls within `< 2s` and client commands succeed transparently via failover.
- [ ] **Given** `ctrl_3` restarts after state updates occurred during its downtime, **When** `_sincronizar_com_cluster()` executes before election, **Then** `ctrl_3` queries active peers sequentially, computes consensus via `ClusterMiddleware.calcular_consenso()`, and persists the synchronized state to `data_ctrl_3.json`.
- [ ] **Given** one controller runs with `--byzantino` alongside two honest controllers, **When** a consensus round runs, **Then** `calcular_consenso()` masks the corrupted vote (`2/3` majority) and prevents state corruption; when only 1 honest and 1 `--byzantino` controller remain (`1 vs 1`), `ErroQuorum` is raised and persistence/actuation is blocked.
- [ ] **Given** all code changes are complete, **When** `pytest trabalho_pratico1/tests -v` and `scripts/validate_e2e.py` are executed, **Then** 100% of unit tests and all 6 E2E stages pass, and all line numbers in `revisao_defesa_tp1.md`, `roteiro_apresentacao.md`, and `trabalho_pratico1_codigo_completo.txt` match the refactored source files.

## Defensive Security & Validation Considerations

### Input Validation
- `SimuladorAmbiente.__init__` continues rejecting `bool` values and out-of-range temperature (`-50..100`) or moisture (`0..100`) inputs with `ValueError`; `executar_sensor` rejects `intervalo <= 0.05`.
- `Controlador._validar_limites_sensor` continues rejecting non-numeric, `bool`, or physically impossible sensor readings (`temperatura` outside `-50..100`, `umidade` outside `0..100`).
- MQTT `_on_message` handlers continue catching `json.JSONDecodeError`, `UnicodeDecodeError`, and `ValueError` safely without crashing processes.

### Secret Isolation
- N/A — the system uses no passwords, API tokens, or secrets; all communication is local loopback (`127.0.0.1`) for academic lab demonstration.

### Authorization & Authentication Impact
- N/A — this change does not expose external endpoints or modify auth logic; it preserves Byzantine vote validation (`--byzantino` masking via `calcular_consenso`) and leader-only actuation authority.

### Other Security Risks
- Bindings remain strictly restricted to `127.0.0.1` (`localhost`) as required by `sdd-stack-contract.md`.
- Sequential RPC calls enforce `TIMEOUT_RPC_SEGUNDOS = 0.6` via `_TimeoutTransport` so a hung or unresponsive peer cannot cause unbounded blocking.

## Testing Strategy & Shift-Left Plan

### Happy Path Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TP-01 | Deterministic closed-loop drift in `SimuladorAmbiente` | Unit (`test_sensor.py`) | Temp `+2.0`/`-2.5`°C, humidity `-3.0`/`+6.0`%, clamped to `[0, 55]` and `[0, 100]` |
| TP-02 | Sequential `ClusterMiddleware` quorum read & command failover | Unit (`test_middleware.py`) | Returns consensus state and routes commands to active leader |
| TP-03 | Bully election, consensus voting, `commit_estado`, leader-only MQTT | Unit + Integration (`test_controlador.py`) | `ctrl_3` elected, all 3 JSONs identical, only leader publishes MQTT |
| TP-04 | Full 6-stage real multi-process verification | E2E (`scripts/validate_e2e.py`) | All 6 stages pass in `< 45s` |

### Edge Case & Failure Mode Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TE-01 | Out-of-range / boolean inputs to `SimuladorAmbiente` or `Controlador` | Unit (`test_sensor.py`, `test_controlador.py`) | `ValueError` raised / malformed reading rejected |
| TE-02 | Replica timeout or unreachable peer during `obter_estado` | Unit (`test_middleware.py`) | Timed-out peer skipped within `0.6s`, `2/2` quorum succeeds |
| TE-03 | Sequential crash failover (`ctrl_3 -> ctrl_2 -> ctrl_1` degraded `1/1`) | Integration + E2E (`test_controlador.py`, `validate_e2e.py`) | System remains operational down to 1 active controller |
| TE-04 | Byzantine fault masking (`2/3`) and tie failure (`1 vs 1` -> `ErroQuorum`) | Integration + E2E (`test_controlador.py`, `validate_e2e.py`) | Corrupted vote ignored at `2/3`; `ErroQuorum` blocks corruption at `1 vs 1` |

### Test Commands
- **Run tests:** `pytest trabalho_pratico1/tests -v`
- **Coverage / E2E check:** `pytest trabalho_pratico1/tests -v && PYTHONPATH=trabalho_pratico1 python3 trabalho_pratico1/scripts/validate_e2e.py`

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Sequential RPC loops increase latency if multiple peers hang | Low | Med | Reduce `TIMEOUT_RPC_SEGUNDOS` to `0.6s` on `127.0.0.1` (`2 * 0.6s = 1.2s` worst case, well below client timeout `2.5s+`) |
| `test_middleware.py` timeout test sleeps `1.5s` assuming parallel execution | Med | Low | Update mock sleep/timeout in `test_middleware.py` if needed and verify all tests pass |
| Line numbers in defense docs drift after refactoring | High | High | Inspect exact lines after final code edit and regenerate `trabalho_pratico1_codigo_completo.txt` + update docs in Step 3 |

## Specification Changes & Delta Stubs

### `specs/distributed-controllers-consensus-delta.md`
- **Target Canonical Spec:** `openspec/specs/distributed-controllers-consensus.md`
- **Summary of Updates:** Sequential peer RPC loops with `TIMEOUT_RPC_SEGUNDOS = 0.6`, removal of `ThreadPoolExecutor` boilerplate, state updates applied only via `commit_estado` after consensus, simplified `_sincronizar_com_cluster`, direct `json.dump` under `self._lock`, and removal of unused `QUORUM_MINIMO` / `total_ativos`.

### `specs/iot-sensor-actuator-loop-delta.md`
- **Target Canonical Spec:** `openspec/specs/iot-sensor-actuator-loop.md`
- **Summary of Updates:** Deterministic fixed-step drift (`+2.0°C`/`-2.5°C` and `-3.0%`/`+6.0%`) in `SimuladorAmbiente` without `random` or internal `threading.Lock`.

### `specs/lab-presentation-automation-delta.md`
- **Target Canonical Spec:** `openspec/specs/lab-presentation-automation.md`
- **Summary of Updates:** Updated defense documentation (`revisao_defesa_tp1.md` with Defense Survival Guide, `roteiro_apresentacao.md`, `relatorio/relatorio.md`, `trabalho_pratico1_codigo_completo.txt`) synchronized with simplified source code.

## References

- Official assignment: `trabalho_pratico1/Trabalho Prático 1 - SD.pdf`
- Living specs: `openspec/specs/distributed-controllers-consensus.md`, `openspec/specs/iot-sensor-actuator-loop.md`, `openspec/specs/lab-presentation-automation.md`, `openspec/specs/sdd-stack-contract.md`
