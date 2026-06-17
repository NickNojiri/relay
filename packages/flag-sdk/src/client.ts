import { evaluate } from "./eval";
import type { Decision, EvalContext, FlagRule } from "./types";

/** Where the client loads flag rules from (DB, cache, in-memory map, ...). */
export interface FlagSource {
  getRule(key: string): FlagRule | undefined | Promise<FlagRule | undefined>;
}

/** Trivial in-memory source, handy for tests and the walking-skeleton demo. */
export class MemoryFlagSource implements FlagSource {
  constructor(private readonly rules = new Map<string, FlagRule>()) {}
  set(rule: FlagRule): void {
    this.rules.set(rule.key, rule);
  }
  getRule(key: string): FlagRule | undefined {
    return this.rules.get(key);
  }
}

/**
 * Public client surface used by studio, prompt-ops, and other consumers.
 * The API is binding-agnostic: Phase 4 swaps `evaluate` for the native engine
 * without changing this class.
 */
export class FlagClient {
  constructor(private readonly source: FlagSource) {}

  async evaluate(key: string, ctx: EvalContext): Promise<Decision> {
    const rule = await this.source.getRule(key);
    if (!rule) {
      return { enabled: false, variant: null, reason: "flag_disabled" };
    }
    return evaluate(rule, ctx);
  }
}
