"use client";

import { useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

const WS_URL = process.env.NEXT_PUBLIC_SYNC_URL ?? "ws://localhost:1234";

/** A live, multiplayer draft area backed by the Yjs CRDT sync-server. */
export function CollabEditor({ room = "draft" }: { room?: string }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState("connecting");
  const ytextRef = useRef<Y.Text | null>(null);

  useEffect(() => {
    const doc = new Y.Doc();
    const provider = new WebsocketProvider(WS_URL, room, doc);
    const ytext = doc.getText("body");
    ytextRef.current = ytext;

    const render = () => setText(ytext.toString());
    ytext.observe(render);
    provider.on("status", (event: { status: string }) => setStatus(event.status));
    render();

    return () => {
      ytext.unobserve(render);
      provider.destroy();
      doc.destroy();
      ytextRef.current = null;
    };
  }, [room]);

  function onChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    const ytext = ytextRef.current;
    if (!ytext) return;
    const next = event.target.value;
    // Simplified binding: replace the shared text. Enough to demo live sync; a
    // production editor would apply character-level deltas to preserve concurrent edits.
    ytext.doc?.transact(() => {
      ytext.delete(0, ytext.length);
      ytext.insert(0, next);
    });
  }

  return (
    <div>
      <div className="text-xs text-muted-foreground">
        multiplayer · <span className="font-medium text-foreground">{status}</span>
      </div>
      <textarea
        value={text}
        onChange={onChange}
        rows={4}
        placeholder="Draft a prompt together…"
        className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
      />
    </div>
  );
}
