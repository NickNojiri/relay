const GATEWAY = process.env.PROMPT_OPS_URL ?? "http://localhost:8000";

/** Server-side proxy that pipes the gateway's SSE stream through to the browser. */
export async function POST(req: Request) {
  const body = await req.json();
  try {
    const upstream = await fetch(`${GATEWAY}/v1/chat/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!upstream.ok || !upstream.body) {
      return new Response(JSON.stringify({ error: `gateway error ${upstream.status}` }), {
        status: upstream.status,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(upstream.body, {
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
    });
  } catch {
    return new Response(
      JSON.stringify({ error: `prompt-ops gateway unreachable at ${GATEWAY}` }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
}
