import { db, flags, promptVersions } from "@relay/db";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

async function upsertFlag(formData: FormData) {
  "use server";
  const key = String(formData.get("key") ?? "").trim();
  if (!key) return;
  const enabled = formData.get("enabled") === "on";
  const rolloutBps = Math.max(0, Math.min(10000, Number(formData.get("rolloutBps") ?? 10000)));
  const variants = [
    {
      key: "A",
      weightBps: Number(formData.get("weightA") ?? 5000),
      promptVersionId: String(formData.get("versionA") ?? "") || null,
    },
    {
      key: "B",
      weightBps: Number(formData.get("weightB") ?? 5000),
      promptVersionId: String(formData.get("versionB") ?? "") || null,
    },
  ];
  await db
    .insert(flags)
    .values({ key, enabled, rolloutBps, variants })
    .onConflictDoUpdate({
      target: flags.key,
      set: { enabled, rolloutBps, variants, updatedAt: new Date() },
    });
  revalidatePath("/flags");
}

export default async function FlagsPage() {
  const [allFlags, versions] = await Promise.all([
    db.select().from(flags).orderBy(flags.key),
    db.select().from(promptVersions),
  ]);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <a href="/" className="text-sm text-muted-foreground hover:underline">
        ← Relay Studio
      </a>
      <h1 className="mt-2 text-2xl font-semibold">Flag admin</h1>

      <section className="mt-6">
        <h2 className="font-medium">Create / update a flag</h2>
        <form action={upsertFlag} className="mt-2 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <input name="key" placeholder="prompt.support-bot" className="rounded-md border px-3 py-2 text-sm" />
            <label className="flex items-center gap-1 text-sm">
              <input type="checkbox" name="enabled" defaultChecked /> enabled
            </label>
            <label className="flex items-center gap-1 text-sm">
              rollout bps
              <input
                name="rolloutBps"
                type="number"
                defaultValue={10000}
                min={0}
                max={10000}
                className="w-24 rounded-md border px-2 py-1 text-sm"
              />
            </label>
          </div>
          {(["A", "B"] as const).map((label) => (
            <div key={label} className="flex flex-wrap items-center gap-2">
              <span className="w-4 text-sm font-medium">{label}</span>
              <select name={`version${label}`} className="rounded-md border px-3 py-2 text-sm">
                <option value="">— version —</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version} · {v.id.slice(0, 8)}
                  </option>
                ))}
              </select>
              <input
                name={`weight${label}`}
                type="number"
                defaultValue={5000}
                className="w-24 rounded-md border px-2 py-1 text-sm"
              />
              <span className="text-xs text-muted-foreground">bps</span>
            </div>
          ))}
          <button className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
            Save flag
          </button>
        </form>
      </section>

      <section className="mt-8">
        <h2 className="font-medium">Flags</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {allFlags.map((f) => (
            <li key={f.id} className="rounded-md border p-3">
              <div className="flex items-center justify-between">
                <code className="font-medium">{f.key}</code>
                <span className="text-xs text-muted-foreground">
                  {f.enabled ? "on" : "off"} · {f.rolloutBps / 100}% rollout
                </span>
              </div>
              <div className="mt-1 text-muted-foreground">
                {f.variants.map((v) => `${v.key}:${v.weightBps / 100}%`).join("  ·  ")}
              </div>
            </li>
          ))}
          {allFlags.length === 0 && <li className="text-muted-foreground">No flags yet.</li>}
        </ul>
      </section>
    </main>
  );
}
