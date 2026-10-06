ALTER TABLE "prompt_versions" ADD COLUMN "fallbacks" jsonb DEFAULT '[]'::jsonb NOT NULL;--> statement-breakpoint
ALTER TABLE "telemetry" ADD COLUMN "fallback_reason" text;