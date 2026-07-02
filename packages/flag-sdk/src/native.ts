import type { Decision, EvalContext, FlagRule } from "./types";

/**
 * Optional native engine (@relay/flag-node, napi-rs over the Rust flag-core).
 *
 * Loading is explicit and async — call `enableNativeEngine()` once at server
 * startup — so browser/edge bundles never touch Node builtins and the pure-TS
 * path stays the default. Once enabled, `evaluate()` routes through the native
 * engine transparently; if the addon is missing or misbehaves we stay on TS.
 */

interface NativeEngine {
  evaluateJson(ruleJson: string, unitId: string): string;
}

let engine: NativeEngine | null = null;

/** A rule whose decision is knowable without hashing — used to sanity-check the addon. */
const PROBE_RULE = { key: "probe", enabled: false, rolloutBps: 0, variants: [] };

/**
 * Try to load the native addon. Returns true if the engine is active.
 * Safe to call anywhere: it no-ops (false) outside Node or when the
 * platform-specific `.node` artifact isn't built/installed.
 */
export async function enableNativeEngine(): Promise<boolean> {
  if (engine) return true;
  if (typeof process === "undefined" || !process.versions?.node) return false;
  try {
    const { createRequire } = await import(/* webpackIgnore: true */ "node:module");
    const requireNative = createRequire(import.meta.url);
    const mod = requireNative("@relay/flag-node") as NativeEngine;
    const probe = JSON.parse(mod.evaluateJson(JSON.stringify(PROBE_RULE), "u")) as Decision;
    if (probe.reason !== "flag_disabled") return false;
    engine = mod;
    return true;
  } catch {
    return false;
  }
}

/** Drop back to the pure-TS engine (mainly for tests). */
export function disableNativeEngine(): void {
  engine = null;
}

export function nativeEngineActive(): boolean {
  return engine !== null;
}

/** Native-path evaluation; null when the native engine isn't enabled. */
export function nativeEvaluate(rule: FlagRule, ctx: EvalContext): Decision | null {
  if (!engine) return null;
  return JSON.parse(engine.evaluateJson(JSON.stringify(rule), ctx.unitId)) as Decision;
}
