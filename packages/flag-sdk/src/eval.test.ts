import { describe, it, expect } from "vitest";
import { evaluate, fnv1a } from "./index";
import type { FlagRule } from "./index";

const rule = (over: Partial<FlagRule> = {}): FlagRule => ({
  key: "prompt.support-bot",
  enabled: true,
  rolloutBps: 10000,
  variants: [
    { key: "A", weightBps: 5000 },
    { key: "B", weightBps: 5000 },
  ],
  ...over,
});

describe("fnv1a", () => {
  it("is deterministic", () => {
    expect(fnv1a("user-42")).toBe(fnv1a("user-42"));
  });

  // Known FNV-1a/32 vectors — the Rust core asserts these same numbers.
  it("matches canonical FNV-1a vectors", () => {
    expect(fnv1a("")).toBe(2166136261); // 0x811c9dc5, offset basis
    expect(fnv1a("a")).toBe(3826002220); // 0xe40c292c
  });
});

describe("evaluate", () => {
  it("is flag_disabled when off", () => {
    expect(evaluate(rule({ enabled: false }), { unitId: "u1" })).toEqual({
      enabled: false,
      variant: null,
      reason: "flag_disabled",
    });
  });

  it("is stable for a given unit", () => {
    const a = evaluate(rule(), { unitId: "user-42" });
    const b = evaluate(rule(), { unitId: "user-42" });
    expect(a).toEqual(b);
  });

  it("honors a 0% rollout", () => {
    const d = evaluate(rule({ rolloutBps: 0 }), { unitId: "user-42" });
    expect(d).toMatchObject({ enabled: false, reason: "out_of_rollout" });
  });

  it("splits ~50/50 across many units", () => {
    const n = 10000;
    let a = 0;
    for (let i = 0; i < n; i++) {
      if (evaluate(rule(), { unitId: `user-${i}` }).variant === "A") a++;
    }
    const ratio = a / n;
    expect(ratio).toBeGreaterThan(0.45);
    expect(ratio).toBeLessThan(0.55);
  });
});
