import { nativeEvaluate } from "./native";
import type { Decision, EvalContext, FlagRule } from "./types";

const encoder = new TextEncoder();

/**
 * FNV-1a, 32-bit. Operates on UTF-8 bytes so this matches the Rust `flag-core`
 * implementation exactly — that parity is what the cross-binding conformance
 * suite (Phase 4) verifies. Returns an unsigned 32-bit integer.
 */
export function fnv1a(input: string): number {
  let hash = 0x811c9dc5; // 2166136261 (offset basis)
  for (const byte of encoder.encode(input)) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0; // * 16777619 (FNV prime), keep unsigned
  }
  return hash >>> 0;
}

/** Deterministic 0..9999 bucket for (flag, unit) under a salt namespace. */
function bucket(flagKey: string, unitId: string, salt: string): number {
  return fnv1a(`${flagKey}:${salt}:${unitId}`) % 10000;
}

/**
 * Evaluate a flag. Routes through the native Rust engine when
 * `enableNativeEngine()` has been called (Phase 4b), otherwise — and always in
 * browsers/edge — uses the pure-TS reference implementation below. Both are
 * pinned to identical decisions by the shared conformance suite.
 */
export function evaluate(rule: FlagRule, ctx: EvalContext): Decision {
  return nativeEvaluate(rule, ctx) ?? evaluateTs(rule, ctx);
}

/** Pure-TS reference evaluation (the fallback engine). */
export function evaluateTs(rule: FlagRule, ctx: EvalContext): Decision {
  if (!rule.enabled) {
    return { enabled: false, variant: null, reason: "flag_disabled" };
  }

  if (bucket(rule.key, ctx.unitId, "gate") >= rule.rolloutBps) {
    return { enabled: false, variant: null, reason: "out_of_rollout" };
  }

  if (rule.variants.length === 0) {
    return { enabled: true, variant: null, reason: "no_variants" };
  }

  const vb = bucket(rule.key, ctx.unitId, "variant");
  let cumulative = 0;
  for (const variant of rule.variants) {
    cumulative += variant.weightBps;
    if (vb < cumulative) {
      return { enabled: true, variant: variant.key, reason: "rollout" };
    }
  }
  // Weights summed to < 10000: assign the last variant.
  const last = rule.variants[rule.variants.length - 1]!;
  return { enabled: true, variant: last.key, reason: "rollout" };
}
