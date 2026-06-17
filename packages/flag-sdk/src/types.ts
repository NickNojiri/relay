/** Public evaluation types. Kept standalone so the SDK has no @relay/* runtime deps. */

export interface FlagVariant {
  key: string;
  /** Basis points; weights across a flag's variants sum to 10000. */
  weightBps: number;
  promptVersionId?: string | null;
}

export interface FlagRule {
  key: string;
  enabled: boolean;
  /** Fraction of units the flag is on for, in basis points (0..10000). */
  rolloutBps: number;
  variants: FlagVariant[];
}

export interface EvalContext {
  /** Stable identifier the decision buckets on (e.g. a user id). */
  unitId: string;
}

export type DecisionReason =
  | "flag_disabled"
  | "out_of_rollout"
  | "no_variants"
  | "rollout";

export interface Decision {
  enabled: boolean;
  variant: string | null;
  reason: DecisionReason;
}
