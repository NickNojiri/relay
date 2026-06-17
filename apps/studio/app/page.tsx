const sections = [
  {
    href: "/playground",
    title: "Playground",
    desc: "Send a request through the gateway; see which variant a user gets, plus tokens & latency.",
    ready: true,
  },
  {
    href: "/editor",
    title: "Prompt editor",
    desc: "Author a system prompt and save a version. Real-time co-editing arrives in Phase 3.",
    ready: false,
  },
  {
    href: "/flags",
    title: "Flag admin",
    desc: "Create a rollout flag and split traffic across prompt versions.",
    ready: false,
  },
  {
    href: "/telemetry",
    title: "Telemetry",
    desc: "Per-variant cost and latency, to see which prompt wins.",
    ready: false,
  },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold">Relay Studio</h1>
      <p className="mt-2 text-muted-foreground">
        Author a system prompt, deploy it through an LLM gateway, A/B-test it with feature
        flags, and track cost &amp; latency per variant.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {sections.map((s) => (
          <a
            key={s.href}
            href={s.ready ? s.href : undefined}
            className={`rounded-lg border p-4 transition-colors ${
              s.ready ? "hover:border-primary" : "cursor-default opacity-60"
            }`}
          >
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{s.title}</h2>
              {!s.ready && <span className="text-xs text-muted-foreground">next</span>}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{s.desc}</p>
          </a>
        ))}
      </div>
    </main>
  );
}
