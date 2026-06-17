import { createServer } from "node:http";
import { WebSocketServer, type WebSocket } from "ws";
import * as syncProtocol from "y-protocols/sync";
import * as awarenessProtocol from "y-protocols/awareness";
import * as encoding from "lib0/encoding";
import * as decoding from "lib0/decoding";
import { MESSAGE_AWARENESS, MESSAGE_SYNC, Room } from "./room";

const rooms = new Map<string, Room>();

function getRoom(name: string): Room {
  let room = rooms.get(name);
  if (!room) {
    room = new Room(name);
    rooms.set(name, room);
  }
  return room;
}

function onMessage(room: Room, conn: WebSocket, data: Uint8Array): void {
  const decoder = decoding.createDecoder(data);
  const encoder = encoding.createEncoder();
  const messageType = decoding.readVarUint(decoder);
  switch (messageType) {
    case MESSAGE_SYNC: {
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      syncProtocol.readSyncMessage(decoder, encoder, room.doc, conn);
      // Only reply if readSyncMessage produced more than the type byte.
      if (encoding.length(encoder) > 1) conn.send(encoding.toUint8Array(encoder));
      break;
    }
    case MESSAGE_AWARENESS: {
      awarenessProtocol.applyAwarenessUpdate(
        room.awareness,
        decoding.readVarUint8Array(decoder),
        conn,
      );
      break;
    }
  }
}

/** Start the Yjs CRDT sync server. Room = first path segment of the WS URL. */
export function createSyncServer(port: number) {
  const httpServer = createServer();
  const wss = new WebSocketServer({ server: httpServer });

  wss.on("connection", (conn, req) => {
    const roomName = (req.url ?? "/").slice(1).split("?")[0] || "default";
    const room = getRoom(roomName);
    room.conns.add(conn);
    conn.binaryType = "arraybuffer";

    conn.on("message", (data) => onMessage(room, conn, new Uint8Array(data as ArrayBuffer)));
    conn.on("close", () => {
      room.conns.delete(conn);
      if (room.isEmpty) rooms.delete(roomName);
    });

    // Kick off the handshake: sync step 1.
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, room.doc);
    conn.send(encoding.toUint8Array(encoder));
  });

  httpServer.listen(port);
  return { httpServer, wss, rooms };
}
