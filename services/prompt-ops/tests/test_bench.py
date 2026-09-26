import csv
import gzip
import json
import tomllib
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.providers import EchoProvider, get_provider
from app.repository import get_repository, seed_demo
from loadtest import bench

CONFIG_PATH = Path(__file__).resolve().parents[1] / "loadtest/configs/echo.toml"
LOAD = tomllib.loads(CONFIG_PATH.read_text())["load"]


@pytest.fixture
def client():
    app.dependency_overrides[get_repository] = seed_demo
    app.dependency_overrides[get_provider] = EchoProvider
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")
    app.dependency_overrides.clear()


def test_percentile_is_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert bench.percentile(values, 50) == 50
    assert bench.percentile(values, 95) == 95
    assert bench.percentile(values, 99) == 99
    assert bench.percentile([7.0], 99) == 7
    assert bench.percentile([], 50) == 0


async def test_phase_hits_the_gateway_and_records_every_request(client):
    rows, wall = await bench.run_phase(client, LOAD, concurrency=4, repeat=0, duration_s=0.3)
    assert rows and wall >= 0.3
    assert {r.worker for r in rows} == {0, 1, 2, 3}
    assert all(r.status == 200 and r.variant in {"A", "B"} for r in rows)

    summary = bench.summarize(rows, 4, 0, wall)
    assert summary["ok"] == summary["requests"] == len(rows)
    assert summary["errors"] == 0
    assert summary["p50_ms"] <= summary["p95_ms"] <= summary["p99_ms"] <= summary["max_ms"]


async def test_reruns_send_the_same_request_mix(client):
    first, _ = await bench.run_phase(client, LOAD, concurrency=2, repeat=0, duration_s=0.2)
    second, _ = await bench.run_phase(client, LOAD, concurrency=2, repeat=1, duration_s=0.2)

    def sequence(rows, worker):
        return [(r.unit_id, r.variant) for r in rows if r.worker == worker]

    for worker in (0, 1):
        n = min(len(sequence(first, worker)), len(sequence(second, worker)))
        assert n > 5
        assert sequence(first, worker)[:n] == sequence(second, worker)[:n]


async def test_errors_are_counted_not_dropped(client):
    load = {**LOAD, "prompt_key": "prompt.does-not-exist"}
    rows, wall = await bench.run_phase(client, load, concurrency=1, repeat=0, duration_s=0.1)
    summary = bench.summarize(rows, 1, 0, wall)
    assert rows and all(r.status == 404 for r in rows)
    assert summary["ok"] == 0 and summary["errors"] == len(rows)


async def test_write_results_produces_a_complete_run_directory(client, tmp_path):
    rows, wall = await bench.run_phase(client, LOAD, concurrency=2, repeat=0, duration_s=0.1)
    summaries = [bench.summarize(rows, 2, 0, wall)]
    config = tomllib.loads(CONFIG_PATH.read_text())
    out = tmp_path / "run"

    bench.write_results(out, CONFIG_PATH, bench.manifest(config, "http://gateway", False), rows, summaries)

    assert (out / "config.toml").read_text() == CONFIG_PATH.read_text()
    man = json.loads((out / "manifest.json").read_text())
    assert man["machine"]["logical_cpus"] and man["config"]["name"] == "echo"
    with gzip.open(out / "requests.csv.gz", "rt") as f:
        raw = list(csv.DictReader(f))
    assert len(raw) == len(rows) and set(raw[0]) == set(bench.RAW_FIELDS)
    with open(out / "summary.csv") as f:
        assert next(csv.DictReader(f))["ok"] == str(summaries[0]["ok"])
    assert "| 2 |" in (out / "summary.md").read_text()
