import { db, prompts, promptVersions } from "@relay/db";
import { desc, eq, sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

async function createPrompt(formData: FormData) {
  "use server";
  const key = String(formData.get("key") ?? "").trim();
  const name = String(formData.get("name") ?? "").trim();
  if (!key || !name) return;
  await db.insert(prompts).values({ key, name }).onConflictDoNothing();
  revalidatePath("/editor");
}

async function addVersion(formData: FormData) {
  "use server";
  const promptId = String(formData.get("promptId") ?? "");
  const body = String(formData.get("body") ?? "").trim();
  const provider = String(formData.get("provider") ?? "").trim() || null;
  const model = String(formData.get("model") ?? "").trim() || null;
  if (!promptId || !body) return;
  const rows = await db
    .select({ max: sql<number>`coalesce(max(${promptVersions.version}), 0)` })
    .from(promptVersions)
    .where(eq(promptVersions.promptId, promptId));
  const nextVersion = Number(rows[0]?.max ?? 0) + 1;
  await db.insert(promptVersions).values({ promptId, version: nextVersion, body, provider, model });
  revalidatePath("/editor");
}

export default async function EditorPage() {
  const allPrompts = await db.select().from(prompts).orderBy(prompts.key);
  const versions = await db
    .select()
    .from(promptVersions)
    .orderBy(desc(promptVersions.createdAt))
    .limit(50);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <a href="/" className="text-sm text-muted-foreground hover:underline">
        ← Relay Studio
      </a>
      <h1 className="mt-2 text-2xl font-semibold">Prompt editor</h1>

      <section className="mt-6">
        <h2 className="font-medium">New prompt</h2>
        <form action={createPrompt} className="mt-2 flex flex-wrap gap-2">
          <input name="key" placeholder="prompt.support-bot" className="rounded-md border px-3 py-2 text-sm" />
          <input name="name" placeholder="Support bot" className="rounded-md border px-3 py-2 text-sm" />
          <button className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
            Create
          </button>
        </form>
      </section>

      <section className="mt-8">
        <h2 className="font-medium">Add a version</h2>
        <form action={addVersion} className="mt-2 space-y-2">
          <select name="promptId" className="w-full rounded-md border px-3 py-2 text-sm">
            {allPrompts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.key}
              </option>
            ))}
          </select>
          <textarea
            name="body"
            rows={3}
            placeholder="You are a helpful agent."
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <input name="provider" placeholder="ollama" className="rounded-md border px-3 py-2 text-sm" />
            <input name="model" placeholder="llama3.2" className="rounded-md border px-3 py-2 text-sm" />
            <button className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
              Save version
            </button>
          </div>
        </form>
      </section>

      <section className="mt-8">
        <h2 className="font-medium">Recent versions</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {versions.map((v) => (
            <li key={v.id} className="rounded-md border p-3">
              <div className="text-muted-foreground">
                v{v.version} · {v.provider ?? "—"}/{v.model ?? "—"} ·{" "}
                <code className="text-xs">{v.id}</code>
              </div>
              <div className="mt-1 whitespace-pre-wrap">{v.body}</div>
            </li>
          ))}
          {versions.length === 0 && <li className="text-muted-foreground">No versions yet.</li>}
        </ul>
      </section>
    </main>
  );
}
