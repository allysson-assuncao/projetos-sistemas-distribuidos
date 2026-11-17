# Delta Spec: `lab-presentation-automation`

> **Change ID:** `simplify-components-and-tests`
> **Target Canonical Spec:** `openspec/specs/lab-presentation-automation.md`
> **Change Type:** Modify

## Architectural Updates

- **Update `[RF-01]`:** `estufa.broker_local` provides a streamlined pure-Python MQTT v3.1.1 broker on `127.0.0.1:1883` without Docker, Windows Administrator privileges, or external `mosquitto.exe` wrapper fallback, supporting `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0` and `QoS 1`), `PINGREQ/PINGRESP`, and `DISCONNECT`. If the target TCP port is already in use, `estufa.broker_local` logs a diagnostic message and exits cleanly instead of hanging indefinitely.
