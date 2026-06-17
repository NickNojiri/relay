import { describe, expect, it } from "vitest";
import { loadEnv } from "./env";

const base = {
  DATABASE_URL: "postgres://relay:relay@localhost:5432/relay",
  REDIS_URL: "redis://localhost:6379",
  AUTH_SECRET: "x",
} as NodeJS.ProcessEnv;

describe("loadEnv", () => {
  it("parses a valid environment and applies defaults", () => {
    const env = loadEnv(base);
    expect(env.OLLAMA_BASE_URL).toBe("http://localhost:11434");
    expect(env.RELAY_DEFAULT_PROVIDER).toBe("ollama");
  });

  it("throws a readable error on missing required vars", () => {
    expect(() => loadEnv({} as NodeJS.ProcessEnv)).toThrow(/Invalid Relay environment/);
  });
});
