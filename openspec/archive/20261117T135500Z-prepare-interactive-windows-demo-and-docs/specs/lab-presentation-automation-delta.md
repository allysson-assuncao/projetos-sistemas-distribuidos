# Delta Spec: `lab-presentation-automation`

> **Change ID:** `prepare-interactive-windows-demo-and-docs`
> **Target Canonical Spec:** `openspec/specs/lab-presentation-automation.md`
> **Change Type:** Modify

## Architectural Updates

- **Update `[RF-02]`:** `scripts/start_all.ps1`, `.vscode/tasks.json`, and `trabalho_pratico1/.vscode/tasks.json` MUST launch and manage the 7-process distributed architecture (`broker_local`, `ctrl_1..3` on `8001..8003`, `atuador`, `sensor`, and `cliente`) without `middleware_server` (`:9000`) or `--modo`, providing independent interactive terminals with command history for live parameter adjustments and individual service restarts on Windows 11.
- **Update `[RF-03]`:** `scripts/validate_e2e.py` MUST verify the 7-process architecture end-to-end against real subprocesses (Bully election, closed-loop MQTT actuation + identical `data_ctrl_1..3.json` persistence, sequential `ctrl_3 -> ctrl_2 -> ctrl_1` failover, reconnection DB sync, 2/3 Byzantine masking, and 2-node conflict `ErroQuorum`) and remove temporary `data_ctrl_*.json` files upon completion.
- **Update `[RNF-01]`:** E2E validation suite MUST complete in under 45 seconds on a standard Windows machine (accounting for real subprocess startup, Bully election, Windows loopback timeouts, and reconnection sync checks).
