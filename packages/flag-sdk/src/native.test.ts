import { afterAll, describe, expect, it } from "vitest";
import cases from "../../flag-core/conformance/cases.json";
import {
  disableNativeEngine,
  enableNativeEngine,
  evaluate,
  evaluateTs,
  nativeEngineActive,
} from "./index";
import type { FlagRule } from "./index";

interface ConformanceCase {
  flag: FlagRule;
  unitId: string;
  expected: { enabled: boolean; variant: string | null; reason: string };
}

// Runs only where the @relay/flag-node addon has been built for this platform
// (`pnpm --filter @relay/flag-node build`); CI builds it and exercises this.
// Locally without the artifact the suite skips rather than fails.
const nativeAvailable = await enableNativeEngine();

describe.skipIf(!nativeAvailable)("native engine (@relay/flag-node)", () => {
  afterAll(() => disableNativeEngine());

  it("is active after enableNativeEngine()", () => {
    expect(nativeEngineActive()).toBe(true);
  });

  it("matches every conformance case through evaluate()", () => {
    const all = cases as unknown as ConformanceCase[];
    expect(all.length).toBeGreaterThan(0);
    for (const c of all) {
      const d = evaluate(c.flag, { unitId: c.unitId });
      expect({ enabled: d.enabled, variant: d.variant, reason: d.reason }).toEqual(c.expected);
    }
  });

  it("agrees with the pure-TS engine on random-ish unit ids", () => {
    const rule: FlagRule = {
      key: "prompt.native-parity",
      enabled: true,
      rolloutBps: 7500,
      variants: [
        { key: "A", weightBps: 2500 },
        { key: "B", weightBps: 7500 },
      ],
    };
    for (let i = 0; i < 500; i++) {
      const ctx = { unitId: `unit-${i}-${i * 2654435761}` };
      expect(evaluate(rule, ctx)).toEqual(evaluateTs(rule, ctx));
    }
  });
});

describe.skipIf(nativeAvailable)("native engine unavailable", () => {
  it("evaluate() falls back to the pure-TS engine", () => {
    expect(nativeEngineActive()).toBe(false);
    const rule: FlagRule = { key: "prompt.fallback", enabled: false, rolloutBps: 0, variants: [] };
    expect(evaluate(rule, { unitId: "u" }).reason).toBe("flag_disabled");
  });
});
