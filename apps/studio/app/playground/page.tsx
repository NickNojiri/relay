"use client";

import { useState } from "react";

interface Done {
  variant: string | null;
  latencyMs: number;
}

export default function PlaygroundPage() {
  const [promptKey, setPromptKey] = useState("prompt.support-bot");
  const [unitId, setUnitId] = useState("user-42");
  const [input, setInput] = useState("My order hasn't arrived yet.");
  const [output, setOutput] = useState("");
  const [meta, setMeta] = useState<Done | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setOutput("");
    setMeta(null);
    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt_key: promptKey, unit_id: unitId, input }),
      });
      if (!res.ok || !res.body) {
        const d = (await res.json().catch(() => ({}))) as { error?: string };
        setError(d.error ?? "request failed");
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const evt of events) {
          const match = evt.match(/^data: (.*)$/m);
          const data = match?.[1];
          if (!data) continue;
          const payload = JSON.parse(data) as {
            delta?: string;
            done?: boolean;
            variant?: string | null;
            latencyMs?: number;
          };
          if (payload.delta) {
            acc += payload.delta;
            setOutput(acc);
          }
          if (payload.done) {
            setMeta({ variant: payload.variant ?? null, latencyMs: payload.latencyMs ?? 0 });
          }
        }
      }
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
        Streams from the <code>prompt-ops</code> gateway: the flag engine picks a variant from{" "}
        <code>unit_id</code>, then tokens stream back live as the model responds.
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
          {loading ? "Streaming…" : "Run"}
        </button>
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          {error}
        </p>
      )}

      {(output || meta) && (
        <div className="mt-6 rounded-lg border p-4 text-sm">
          {meta && (
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
              <span>
                variant: <b className="text-foreground">{meta.variant ?? "—"}</b>
              </span>
              <span>{meta.latencyMs} ms</span>
            </div>
          )}
          <pre className="mt-3 whitespace-pre-wrap break-words">{output}</pre>
        </div>
      )}
    </main>
  );
}
