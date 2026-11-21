# Tasks: Simplify TP1 for Oral Defense

> **Change ID:** `simplify-tp1-for-defense`
> **Linked Proposal:** [proposal.md](./proposal.md)
> **Status:** in-progress
>
> All tasks must be `[x]` before this change can be archived via `sdd-spec-archive`.

---

## Implementation Tasks

- [ ] Simplify `trabalho_pratico1/estufa/config.py`: set `TIMEOUT_RPC_SEGUNDOS = 0.6` and remove unused `QUORUM_MINIMO`.
- [ ] Simplify `trabalho_pratico1/estufa/sensor.py`: replace random drift + `threading.Lock` with deterministic fixed steps (`+2.0°C`/`-2.5°C` and `-3.0%`/`+6.0%`).
- [ ] Simplify `trabalho_pratico1/estufa/middleware.py`: replace `ThreadPoolExecutor` / `as_completed` with sequential loops, simplify `_normalizar_estado`, remove unused `total_ativos` and legacy `"pong"` check.
- [ ] Simplify `trabalho_pratico1/estufa/controlador.py`: replace all 5 `ThreadPoolExecutor` blocks with sequential loops, fix pre-consensus mutation in `_on_message`, simplify `_sincronizar_com_cluster` and `_salvar_estado`, deduplicate Byzantine/forwarding helpers, and remove dead/legacy code.
- [ ] Clean legacy `"umidade_solo"` fallback in `trabalho_pratico1/estufa/cliente.py`.

## Test Tasks

- [ ] Review and update `trabalho_pratico1/tests/test_sensor.py`, `test_middleware.py`, and `test_controlador.py` to match simplified deterministic behavior and signatures.
- [ ] Run `pytest trabalho_pratico1/tests -v` and confirm 100% pass rate.
- [ ] Run `PYTHONPATH=trabalho_pratico1 python3 trabalho_pratico1/scripts/validate_e2e.py` and confirm all 6 E2E stages pass.

## Documentation Tasks

- [ ] Update `trabalho_pratico1/revisao_defesa_tp1.md` with exact line numbers (`Lxx–Lyy`) and add the Defense Survival Guide (Leader vs Follower, 8 RPC methods, 6 MQTT topics, 7 critical Q&As, 3-flow study guide, practical drill checklist).
- [ ] Update `trabalho_pratico1/roteiro_apresentacao.md` with exact line numbers across Steps 1–7.
- [ ] Update `trabalho_pratico1/relatorio/relatorio.md` and `trabalho_pratico1/README.md` with updated `TIMEOUT_RPC_SEGUNDOS`, removal of `QUORUM_MINIMO`, and deterministic sensor steps.
- [ ] Regenerate `trabalho_pratico1/trabalho_pratico1_codigo_completo.txt` with exact line numbering.

## Review Gate

- [ ] All implementation tasks complete
- [ ] All tests passing
- [ ] Proposal acceptance criteria verified
- [ ] Ready for `sdd-spec-archive`
