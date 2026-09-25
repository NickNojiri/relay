"""Graceful shutdown: SIGTERM lets an in-flight stream finish and refuses new work.

Runs the real uvicorn with the same --timeout-graceful-shutdown the Dockerfile
uses, so this is the behaviour a deploy gets, not a mock of it.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent.parent
GRACE_S = "30"  # keep in step with the Dockerfile's --timeout-graceful-shutdown

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_up(url: str, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        assert proc.poll() is None, proc.stderr.read().decode()
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.TransportError:
            time.sleep(0.1)
    raise AssertionError("gateway did not start")


def test_sigterm_drains_an_in_flight_stream_then_exits():
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests._drain_app:app", "--port", str(port),
         "--timeout-graceful-shutdown", GRACE_S],
        cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "RELAY_API_KEYS": "", "RELAY_RATE_LIMIT_PER_MINUTE": "0"},
    )
    try:
        _wait_up(f"{base}/health", proc)
        events: list[dict] = []

        def consume():
            with httpx.stream("POST", f"{base}/v1/chat/stream", timeout=10,
                              json={"prompt_key": "slow", "unit_id": "u", "input": "x"}) as r:
                for line in r.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

        reader = threading.Thread(target=consume)
        reader.start()
        while not events:                      # the stream is flowing
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.3)

        with pytest.raises(httpx.TransportError):   # no new work once draining
            httpx.get(f"{base}/health", timeout=1)

        reader.join(timeout=10)
        assert [e["delta"] for e in events if "delta" in e] == [f"t{i} " for i in range(10)]
        assert events[-1]["done"] is True
        # uvicorn re-raises SIGTERM once it has drained, so the exit is by that
        # signal. It must not be SIGKILL, and the drain log must be there.
        assert proc.wait(timeout=10) in (0, -signal.SIGTERM)
        log = proc.stderr.read().decode()
        assert "Waiting for connections to close" in log
        assert "Finished server process" in log
    finally:
        if proc.poll() is None:
            proc.kill()
