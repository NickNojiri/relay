// Conformance of the WebAssembly binding: the same shared fixture the TS,
// Python, Rust, and napi engines assert. Requires `pnpm run build:node` first
// (the package's `test` script does both).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

// The nodejs-target glue is CommonJS; require it so this works both via
// wasm-pack output (own package.json) and raw wasm-bindgen output. Skips
// (rather than fails) when the artifact hasn't been built on this machine;
// CI always builds it first.
let evaluateJson = null;
try {
  ({ evaluateJson } = createRequire(import.meta.url)("../pkg-node/flag_wasm.js"));
} catch {
  // not built — suites below skip
}

const cases = JSON.parse(
  readFileSync(new URL("../../flag-core/conformance/cases.json", import.meta.url), "utf8"),
);

const skip = evaluateJson ? false : "wasm artifact not built (pnpm run build:node)";

test("wasm engine matches every conformance case", { skip }, () => {
  assert.ok(cases.length > 0);
  for (const c of cases) {
    const decision = JSON.parse(evaluateJson(JSON.stringify(c.flag), c.unitId));
    assert.deepEqual(decision, c.expected, `flag=${c.flag.key} unit=${c.unitId}`);
  }
});

test("wasm engine rejects malformed rules", { skip }, () => {
  assert.throws(() => evaluateJson("{not json", "u"));
});
