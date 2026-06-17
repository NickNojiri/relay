import { pgTable, uuid, text, integer, boolean, timestamp, jsonb, index } from "drizzle-orm/pg-core";

/** A variant in a flag's A/B split. Weights are basis points (sum to 10000).
 *  `promptVersionId` is which prompt version this variant serves.
 *  Mirrors @relay/flag-sdk's FlagVariant so storage and evaluation agree. */
export type FlagVariant = {
  key: string;
  weightBps: number;
  promptVersionId: string | null;
};

/** A named prompt (e.g. "prompt.support-bot"). Versions accumulate beneath it. */
export const prompts = pgTable("prompts", {
  id: uuid("id").primaryKey().defaultRandom(),
  key: text("key").notNull().unique(),
  name: text("name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

/** An immutable version of a prompt body, authored collaboratively in studio. */
export const promptVersions = pgTable(
  "prompt_versions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    promptId: uuid("prompt_id")
      .notNull()
      .references(() => prompts.id, { onDelete: "cascade" }),
    version: integer("version").notNull(),
    body: text("body").notNull(),
    provider: text("provider"),
    model: text("model"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    promptIdx: index("prompt_versions_prompt_idx").on(t.promptId),
  }),
);

/** A feature flag governing rollout + A/B split for a prompt. */
export const flags = pgTable("flags", {
  id: uuid("id").primaryKey().defaultRandom(),
  key: text("key").notNull().unique(),
  enabled: boolean("enabled").notNull().default(false),
  /** Fraction of units the flag is "on" for, in basis points (0..10000). */
  rolloutBps: integer("rollout_bps").notNull().default(10000),
  variants: jsonb("variants").$type<FlagVariant[]>().notNull().default([]),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

/** One row per LLM call the gateway proxies — the A/B observability layer. */
export const telemetry = pgTable(
  "telemetry",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    promptVersionId: uuid("prompt_version_id").references(() => promptVersions.id, {
      onDelete: "set null",
    }),
    flagKey: text("flag_key"),
    variant: text("variant"),
    provider: text("provider").notNull(),
    model: text("model").notNull(),
    promptTokens: integer("prompt_tokens").notNull().default(0),
    completionTokens: integer("completion_tokens").notNull().default(0),
    latencyMs: integer("latency_ms").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    createdIdx: index("telemetry_created_idx").on(t.createdAt),
    flagIdx: index("telemetry_flag_idx").on(t.flagKey),
  }),
);
