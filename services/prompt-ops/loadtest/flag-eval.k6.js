// Load test for the Relay gateway's flag-eval + proxy path.
//
//   Terminal A:  RELAY_DEFAULT_PROVIDER=echo uv run uvicorn app.main:app --port 8000
//   Terminal B:  k6 run services/prompt-ops/loadtest/flag-eval.k6.js
//
// Uses the EchoProvider so the test measures the flag engine + gateway overhead
// (not a real LLM). Records p95/p99 latency and throughput.
import http from "k6/http";
import { check } from "k6";

export const options = {
  vus: 50,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<50", "p(99)<100"],
  },
};

const GATEWAY = __ENV.GATEWAY || "http://localhost:8000";

export default function () {
  const body = JSON.stringify({
    prompt_key: "prompt.support-bot",
    unit_id: `user-${Math.floor(Math.random() * 100000)}`,
    input: "hello",
  });
  const res = http.post(`${GATEWAY}/v1/chat`, body, {
    headers: { "content-type": "application/json" },
  });
  check(res, {
    "status is 200": (r) => r.status === 200,
    "has a variant": (r) => JSON.parse(r.body).variant !== undefined,
  });
}
