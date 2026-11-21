# Delta Spec: `distributed-controllers-consensus`

> **Change ID:** `simplify-tp1-for-defense`
> **Target Canonical Spec:** `openspec/specs/distributed-controllers-consensus.md`
> **Change Type:** Modify

## Architectural Updates

- **Sequential Peer & Client RPC Calls (`TIMEOUT_RPC_SEGUNDOS = 0.6`):**
  - Replace `ThreadPoolExecutor` / `as_completed` blocks in `estufa/middleware.py` (`obter_estado`, `verificar_saude`) and `estufa/controlador.py` (`realizar_eleicao`, `_sincronizar_com_cluster`, `_coordenar_consenso_e_persistir`) with straightforward sequential `for` loops over active candidates/peers using `TIMEOUT_RPC_SEGUNDOS = 0.6`s (and client default `TIMEOUT_RPC_SEGUNDOS * 2.5` = `1.5`s or explicit override).
- **Strict Post-Consensus State Mutation:**
  - `Controlador._on_message` MUST NOT mutate `self._estado` prior to consensus. Only the elected leader builds a proposed state dictionary with the incoming sensor reading and updates `self._estado` across the cluster exclusively via `commit_estado` after `ClusterMiddleware.calcular_consenso()` succeeds.
- **Simplified Reconnection Sync & Persistence:**
  - `_sincronizar_com_cluster()` queries peers sequentially, filters initialized responses passing `_validar_limites_sensor`, and resolves official state strictly via `ClusterMiddleware.calcular_consenso()`.
  - `_salvar_estado()` writes `self._estado` directly with `json.dump()` protected by `self._lock` (removing thread-scoped `.tmp` retry loops).
- **Dead/Legacy Code Removal:**
  - Remove unused `QUORUM_MINIMO` from `estufa/config.py`, unused `total_ativos` parameter from `ClusterMiddleware.calcular_consenso()`, legacy `"pong"` check in `verificar_saude()`, and legacy `"umidade_solo"` fallbacks in `controlador.py` and `cliente.py`.
