"use client";

import { useState } from "react";

interface ChatResponse {
  variant: string | null;
  provider: string;
  model: string;
  output: string;
  usage: { prompt_tokens: number; completion_tokens: number };
  latency_ms: number;
}

export default function PlaygroundPage() {
  const [promptKey, setPromptKey] = useState("prompt.support-bot");
  const [unitId, setUnitId] = useState("user-42");
  const [input, setInput] = useState("My order hasn't arrived yet.");
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt_key: promptKey, unit_id: unitId, input }),
      });
      const data = await res.json();
      if (!res.ok) setError(data.error ?? "request failed");
      else setResult(data as ChatResponse);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <a href="/" className="text-sm text-muted-foreground hover:underline">
        ← Relay Studio
      </a>
      <h1 className="mt-2 text-2xl font-semibold">Playground</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Routes through the <code>prompt-ops</code> gateway: the flag engine picks a variant
        deterministically from <code>unit_id</code>, then the gateway proxies the LLM call and
        logs telemetry.
      </p>

      <div className="mt-6 space-y-3">
        <label className="block text-sm font-medium">
          Prompt key
          <input
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            value={promptKey}
            onChange={(e) => setPromptKey(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium">
          Unit id (buckets the variant)
          <input
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            value={unitId}
            onChange={(e) => setUnitId(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium">
          Input
          <textarea
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <button
          onClick={run}
          disabled={loading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Running…" : "Run"}
        </button>
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-6 rounded-lg border p-4 text-sm">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
            <span>
              variant: <b className="text-foreground">{result.variant ?? "—"}</b>
            </span>
            <span>
              {result.provider}/{result.model}
            </span>
            <span>
              {result.usage.prompt_tokens}+{result.usage.completion_tokens} tok
            </span>
            <span>{result.latency_ms} ms</span>
          </div>
          <pre className="mt-3 whitespace-pre-wrap break-words">{result.output}</pre>
        </div>
      )}
    </main>
  );
}
