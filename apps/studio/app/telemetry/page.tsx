import { db, telemetry } from "@relay/db";
import { avg, count, sum } from "drizzle-orm";

export const dynamic = "force-dynamic";

export default async function TelemetryPage() {
  const rows = await db
    .select({
      flagKey: telemetry.flagKey,
      variant: telemetry.variant,
      n: count(),
      avgLatency: avg(telemetry.latencyMs),
      promptTokens: sum(telemetry.promptTokens),
      completionTokens: sum(telemetry.completionTokens),
    })
    .from(telemetry)
    .groupBy(telemetry.flagKey, telemetry.variant);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <a href="/" className="text-sm text-muted-foreground hover:underline">
        ← Relay Studio
      </a>
      <h1 className="mt-2 text-2xl font-semibold">Telemetry</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Per-variant request volume, average latency, and token totals — which prompt wins.
      </p>

      <table className="mt-6 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">flag</th>
            <th className="py-2 pr-4">variant</th>
            <th className="py-2 pr-4">requests</th>
            <th className="py-2 pr-4">avg ms</th>
            <th className="py-2 pr-4">prompt tok</th>
            <th className="py-2">completion tok</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b">
              <td className="py-2 pr-4">
                <code className="text-xs">{r.flagKey ?? "—"}</code>
              </td>
              <td className="py-2 pr-4">{r.variant ?? "—"}</td>
              <td className="py-2 pr-4">{r.n}</td>
              <td className="py-2 pr-4">{r.avgLatency ? Math.round(Number(r.avgLatency)) : "—"}</td>
              <td className="py-2 pr-4">{r.promptTokens ?? 0}</td>
              <td className="py-2">{r.completionTokens ?? 0}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="py-3 text-muted-foreground">
                No telemetry yet — run a request from the playground.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
