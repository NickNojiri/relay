# Gateway load test

A benchmark anyone can rerun and compare. The test settings are in a committed config, each run
records the machine and the git commit it ran on, and the raw per-request data is committed with
the summary.

## Rerun it

From `services/prompt-ops`:

```bash
uv run python loadtest/bench.py --label <machine>        # e.g. --label 7800x3d
```

This takes about 100 seconds. The script:

1. Starts the gateway with the settings in `configs/echo.toml`: one Uvicorn worker, access log
   off, Echo provider, in-memory seeded repository, auth, rate limit and tracing off. Those
   settings are passed as environment variables, so a local `.env` can't change what's measured.
2. For each concurrency level, sends load for `warmup_s` and discards those results, then runs
   `repeats` measured phases of `duration_s` each.
3. Stops the gateway and writes `results/<UTC time>-<config>-<label>/`.

To measure a gateway that's already running instead (a Docker demo, a Fly deployment, a
different provider), pass `--gateway http://host:port [--api-key KEY]`. The manifest then records
that the gateway's settings were not controlled by the harness.

Commit a finished run from a clean working tree. The manifest records `git_sha` and `git_dirty`,
and a dirty run can't be tied to the code that produced it.

## What it measures

`POST /v1/chat` with the seeded `prompt.support-bot` A/B flag. Each request pays for flag
evaluation, prompt-version lookup, the Echo "completion" and a telemetry write, which is the work
the gateway adds on top of a model call. There is no model and no database in the path. The Echo
provider makes no outbound HTTP call, so this config can't show changes to provider HTTP
handling such as connection pooling. Measuring those needs a config with a real upstream.

Workers run a **closed loop**: each worker sends its next request as soon as the previous one
returns, so concurrency is the number of requests in flight. Each worker draws unit IDs from a
generator seeded by `(seed, concurrency, worker)`, so every rerun sends the same request sequence
and the same A/B mix (enforced by `tests/test_bench.py`).

## Output files

| File | Contents |
|------|----------|
| `config.toml` | Exact copy of the config used |
| `manifest.json` | Time, git SHA and dirty flag, CPU model, core count, memory, OS, Python and package versions, and whether the client and gateway shared a host |
| `requests.csv.gz` | One row per measured request: level, repeat, worker, sequence number, start offset, latency, status, variant, unit ID, error |
| `summary.csv` | One row per level and repeat: requests, ok, errors, wall time, throughput, p50/p95/p99/max |
| `summary.md` | Median across repeats per level, with the min–max range |

- **Throughput:** successful requests divided by the phase's wall time.
- **Percentiles:** nearest-rank, over successful requests only.
- **Errors:** anything that isn't a 200 with a variant, including timeouts and connection errors.
  Errors are counted in the totals, never dropped.

## Reading the numbers

- **Compare only runs on the same machine.** Compare medians, and treat differences inside the
  min–max ranges as noise.
- **Load generator on the same machine.** When the harness launches the gateway, the load
  generator runs on the same machine and competes with it for CPU. The numbers are an upper bound
  on overhead for that machine, not a capacity figure.
- **Past saturation (c=50 on a 4-vCPU box).** Throughput falls below the c=10 figure and the tail
  swings run to run. That point shows *where* one worker saturates. It is too noisy for
  before/after comparisons, so use c=1 (per-request overhead) and c=10 for those.
