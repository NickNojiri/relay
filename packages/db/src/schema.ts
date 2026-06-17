import { pgTable, text, timestamp, json, uuid } from 'drizzle-orm/pg-core';

export const prompts = pgTable('prompts', {
  id: uuid('id').primaryKey().defaultRandom(),
  name: text('name').notNull().unique(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const promptVersions = pgTable('prompt_versions', {
  id: uuid('id').primaryKey().defaultRandom(),
  promptId: uuid('prompt_id').references(() => prompts.id).notNull(),
  content: text('content').notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const flags = pgTable('flags', {
  id: uuid('id').primaryKey().defaultRandom(),
  key: text('key').notNull().unique(),
  rolloutPercentage: json('rollout_percentage').notNull(), // e.g., { "versionA": 50, "versionB": 50 }
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const telemetry = pgTable('telemetry', {
  id: uuid('id').primaryKey().defaultRandom(),
  flagKey: text('flag_key').notNull(),
  resolvedVariant: text('resolved_variant').notNull(),
  promptVersionId: uuid('prompt_version_id').notNull(),
  latencyMs: json('latency_ms').notNull(), // Array of latencies or aggregated percentiles
  tokenCost: json('token_cost').notNull(),
  recordedAt: timestamp('recorded_at').defaultNow().notNull(),
});
