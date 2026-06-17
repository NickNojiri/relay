import { describe, expect, it } from "vitest";
import { Room, type Conn } from "./room";

describe("Room", () => {
  it("broadcasts a doc update to other conns, excluding the origin", () => {
    const room = new Room("r");
    const sentToB: Uint8Array[] = [];
    const a: Conn = { send: () => {}, readyState: 1 };
    const b: Conn = { send: (d) => sentToB.push(d), readyState: 1 };
    room.conns.add(a);
    room.conns.add(b);

    // Simulate `a` editing the shared doc (origin = a).
    room.doc.transact(() => {
      room.doc.getText("body").insert(0, "hello");
    }, a);

    expect(room.doc.getText("body").toString()).toBe("hello");
    expect(sentToB.length).toBe(1); // b received the update; a (origin) was excluded
  });

  it("does not send to conns that are not open", () => {
    const room = new Room("r");
    let delivered = 0;
    const closed: Conn = {
      send: () => {
        delivered += 1;
      },
      readyState: 3, // CLOSED
    };
    room.conns.add(closed);
    room.doc.transact(() => room.doc.getText("body").insert(0, "x"), null);
    expect(delivered).toBe(0);
  });
});
