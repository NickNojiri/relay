import * as Y from "yjs";
import * as syncProtocol from "y-protocols/sync";
import * as awarenessProtocol from "y-protocols/awareness";
import * as encoding from "lib0/encoding";

export const MESSAGE_SYNC = 0;
export const MESSAGE_AWARENESS = 1;

const WS_OPEN = 1;

/** Minimal connection surface — a `ws` WebSocket satisfies this structurally. */
export interface Conn {
  send(data: Uint8Array): void;
  readyState: number;
}

/** A collaborative room: one shared Y.Doc + awareness, fanned out to all conns. */
export class Room {
  readonly doc = new Y.Doc();
  readonly awareness = new awarenessProtocol.Awareness(this.doc);
  readonly conns = new Set<Conn>();

  constructor(readonly name: string) {
    this.awareness.setLocalState(null);

    // Relay every document update to all peers except the one that authored it.
    this.doc.on("update", (update: Uint8Array, origin: unknown) => {
      const encoder = encoding.createEncoder();
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      syncProtocol.writeUpdate(encoder, update);
      this.broadcast(encoding.toUint8Array(encoder), origin);
    });

    // Relay presence (cursors / selections) to everyone.
    this.awareness.on(
      "update",
      (changes: { added: number[]; updated: number[]; removed: number[] }) => {
        const changed = changes.added.concat(changes.updated, changes.removed);
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
        encoding.writeVarUint8Array(
          encoder,
          awarenessProtocol.encodeAwarenessUpdate(this.awareness, changed),
        );
        this.broadcast(encoding.toUint8Array(encoder), null);
      },
    );
  }

  /** Send to every open conn except the originator. */
  broadcast(message: Uint8Array, origin: unknown): void {
    for (const conn of this.conns) {
      if (conn !== origin && conn.readyState === WS_OPEN) conn.send(message);
    }
  }

  get isEmpty(): boolean {
    return this.conns.size === 0;
  }
}
