import { z } from "zod";

/** Server-side environment, validated once at startup. */
const schema = z.object({
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),
  AUTH_SECRET: z.string().min(1),
  ANTHROPIC_API_KEY: z.string().optional(),
  OPENAI_API_KEY: z.string().optional(),
  OLLAMA_BASE_URL: z.string().url().default("http://localhost:11434"),
  RELAY_DEFAULT_PROVIDER: z.enum(["anthropic", "openai", "ollama"]).default("ollama"),
  RELAY_DEFAULT_MODEL: z.string().default("llama3.2"),
});

export type Env = z.infer<typeof schema>;

/** Parse + validate environment, throwing a readable error on misconfiguration. */
export function loadEnv(source: NodeJS.ProcessEnv = process.env): Env {
  const parsed = schema.safeParse(source);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `  - ${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("\n");
    throw new Error(`Invalid Relay environment:\n${issues}`);
  }
  return parsed.data;
}
