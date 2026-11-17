# Tasks: Refactor Core Distributed Controllers, Embedded Middleware & Consensus Persistence

> **Change ID:** `refactor-core-distributed-controllers`
> **Linked Proposal:** [proposal.md](./proposal.md)
> **Status:** complete
>
> All tasks must be `[x]` before this change can be archived via `sdd-spec-archive`.

---

## Implementation Tasks

- [x] Delete `trabalho_pratico1/estufa/middleware_server.py` (eliminate standalone `:9000` intermediary process)
- [x] Update `trabalho_pratico1/estufa/config.py` removing `MIDDLEWARE_HOST`/`MIDDLEWARE_PORT` and adding `MAPA_CONTROLADORES` (`1..3`), `INTERVALO_HEARTBEAT_SEGUNDOS`, and controller rank helpers
- [x] Refactor `trabalho_pratico1/estufa/middleware.py` into an embedded logical RPC layer (`ClusterMiddleware`, `ErroQuorum`, `_TimeoutTransport`) supporting direct controller communication, leader discovery, and automatic client failover across `CONTROLADORES`
- [x] Implement Bully leader election (`ping`, `iniciar_eleicao`, `anunciar_lider`, periodic leader heartbeat thread) and automatic failover in `trabalho_pratico1/estufa/controlador.py`
- [x] Implement leader-coordinated dynamic-quorum consensus (`coletar_voto_estado`, majority voting masking `--byzantino` faults in $3$-node mode, $2/2$ mode, and $1/1$ degraded mode) in `trabalho_pratico1/estufa/controlador.py`
- [x] Implement synchronous `commit_estado` replication so `data_ctrl_1.json`, `data_ctrl_2.json`, and `data_ctrl_3.json` store identical validated state and ensure only the leader publishes MQTT actuation commands
- [x] Implement automatic peer state synchronization on controller startup/reconnection (`_sincronizar_com_cluster`, removing `--skip-sync` and `:9000` dependency) and support simplified CLI (`python -m estufa.controlador <1|2|3> [--byzantino]`)
- [x] Refactor `trabalho_pratico1/estufa/cliente.py` to use `ClusterMiddleware` for direct XML-RPC calls to controllers with transparent leader routing and failover

## Security Validation Tasks

- [x] Validate controller IDs (`1..3`), actuator names (`"bomba"`, `"exaustor"`), boolean flags, and incoming JSON state schemas before committing to `data_ctrl_*.json`
- [x] Confirm all XML-RPC listeners bind strictly to `localhost` (`127.0.0.1`) and no secrets or credentials are hardcoded
- [x] Verify `_TimeoutTransport` bounds all outbound XML-RPC calls (`TIMEOUT_RPC_SEGUNDOS`) and locks are never held across network RPC calls (preventing deadlocks/hangs)

## Shift-Left Test Suite Tasks

### Happy Path
- [x] Implement `TP-01` & `TP-02` in `trabalho_pratico1/tests/test_controlador.py`: verify Bully election selects highest active ID and leader commits identical state across `data_ctrl_1.json`..`data_ctrl_3.json`
- [x] Implement `TP-03` & `TP-04` in `trabalho_pratico1/tests/test_middleware.py` and `test_controlador.py`: verify direct client RPC via `ClusterMiddleware` without `:9000` and leader-only MQTT actuation emission

### Edge Cases & Failure Modes
- [x] Implement `TE-01` & `TE-02` in `trabalho_pratico1/tests/test_controlador.py` and `test_middleware.py`: verify automatic leader failover on crash (`ctrl_3` -> `ctrl_2`) with client retry, and $2/3$ Byzantine masking rejecting `--byzantino` values before persistence
- [x] Implement `TE-03`, `TE-04`, and `TE-05` in `trabalho_pratico1/tests/test_controlador.py` and `test_middleware.py`: verify graceful degradation ($2/2$ and $1/1$), `ErroQuorum` on conflicting 2-node tie / 0 active nodes, and automatic DB catch-up synchronization when a crashed replica restarts

## Documentation Tasks

- [x] Ensure `openspec/changes/refactor-core-distributed-controllers/specs/distributed-controllers-consensus.md` accurately captures all final RPC contracts and quorum behaviors

## Review Gate

- [x] All implementation tasks complete
- [x] All security validation tasks complete
- [x] All tests passing (`.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests\test_middleware.py .\trabalho_pratico1\tests\test_controlador.py -v`)
- [x] Proposal acceptance criteria verified
- [x] Ready for `sdd-spec-archive`
