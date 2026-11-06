import json
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class StructuredLogger:
    """Thread-safe JSON Lines (JSONL) structured logger."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.log_path.write_text("", encoding="utf-8")

    def log(self, record: Dict[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


SCENARIO_SEED_OFFSET = {
    "nominal": 1000,
    "latency_spike": 2000,
    "intermittent_error": 3000,
}


def compute_fault_behavior(fault_mode: str, req_seq: int) -> Tuple[float, int, str]:
    """
    Deterministically computes (sleep_seconds, http_status, fault_label)
    based on fault_mode and request sequence number.
    """
    seed = 42000 + SCENARIO_SEED_OFFSET.get(fault_mode, 9000) + req_seq
    rng = random.Random(seed)
    roll = rng.random()

    if fault_mode == "nominal":
        delay_s = rng.uniform(0.005, 0.020)
        return delay_s, 200, "none"

    if fault_mode == "latency_spike":
        if roll < 0.70:
            delay_s = rng.uniform(0.005, 0.020)
            return delay_s, 200, "none"
        elif roll < 0.90:
            delay_s = rng.uniform(0.090, 0.160)
            return delay_s, 200, "tail_latency_90_160ms"
        else:
            delay_s = rng.uniform(0.260, 0.340)
            return delay_s, 200, "severe_stall_over_200ms"

    if fault_mode == "intermittent_error":
        delay_s = rng.uniform(0.005, 0.025)
        if roll < 0.25:
            return delay_s, 503, "http_503_service_unavailable"
        return delay_s, 200, "none"

    return 0.010, 200, "none"


class TelemetryRequestHandler(BaseHTTPRequestHandler):
    logger: Optional[StructuredLogger] = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"}, correlation_id="healthcheck")
        else:
            self._send_json(404, {"error": "not_found"}, correlation_id="none")

    def do_POST(self) -> None:
        start_perf = time.perf_counter()
        correlation_id = self.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        fault_mode = self.headers.get("X-Fault-Mode", "nominal")
        try:
            req_seq = int(self.headers.get("X-Request-Seq", "0"))
        except ValueError:
            req_seq = 0

        if self.path != "/api/v1/telemetry":
            self._send_json(404, {"error": "not_found"}, correlation_id=correlation_id)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body_data = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body_data = {}

        device_id = body_data.get("device_id", "unknown-device")
        delay_s, status_code, fault_label = compute_fault_behavior(fault_mode, req_seq)

        time.sleep(delay_s)
        duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)

        if status_code == 200:
            resp_payload = {
                "status": "ingested",
                "device_id": device_id,
                "correlation_id": correlation_id,
                "server_duration_ms": duration_ms,
            }
            outcome = "SUCCESS"
        else:
            resp_payload = {
                "status": "error",
                "error_code": "DOWNSTREAM_STORAGE_UNAVAILABLE",
                "device_id": device_id,
                "correlation_id": correlation_id,
                "server_duration_ms": duration_ms,
            }
            outcome = "HTTP_ERROR"

        client_disconnected = False
        try:
            self._send_json(status_code, resp_payload, correlation_id=correlation_id)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            client_disconnected = True
            outcome = "CLIENT_TIMEOUT_DISCONNECT"

        if self.logger is not None:
            self.logger.log(
                {
                    "component": "server",
                    "scenario": fault_mode,
                    "correlation_id": correlation_id,
                    "request_seq": req_seq,
                    "device_id": device_id,
                    "operation": "POST /api/v1/telemetry",
                    "duration_ms": duration_ms,
                    "http_status": status_code,
                    "outcome": outcome,
                    "fault_injected": fault_label,
                    "client_disconnected": client_disconnected,
                }
            )

    def _send_json(self, status_code: int, payload: Dict[str, Any], correlation_id: str) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Correlation-ID", correlation_id)
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default stderr HTTP access logs to keep console output clean
        return


def start_background_server(
    logger: StructuredLogger, host: str = "127.0.0.1", port: int = 0
) -> Tuple[ThreadingHTTPServer, int]:
    ThreadingHTTPServer.request_queue_size = 64
    TelemetryRequestHandler.logger = logger
    server = ThreadingHTTPServer((host, port), TelemetryRequestHandler)
    server.daemon_threads = True
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, name="telemetry-http-server", daemon=True)
    thread.start()
    return server, actual_port
