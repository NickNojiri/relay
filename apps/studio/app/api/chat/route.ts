import { NextResponse } from "next/server";

const GATEWAY = process.env.PROMPT_OPS_URL ?? "http://localhost:8000";
// When the gateway enforces RELAY_API_KEYS, the proxy authenticates server-side
// so the key never reaches the browser.
const GATEWAY_KEY = process.env.PROMPT_OPS_API_KEY;

/** Server-side proxy to the prompt-ops gateway (keeps the browser off CORS). */
export async function POST(req: Request) {
  const body = await req.json();
  try {
    const res = await fetch(`${GATEWAY}/v1/chat`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(GATEWAY_KEY ? { authorization: `Bearer ${GATEWAY_KEY}` } : {}),
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: `prompt-ops gateway unreachable at ${GATEWAY}` },
      { status: 502 },
    );
  }
}
