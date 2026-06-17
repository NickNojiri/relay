import { createSyncServer } from "./server";

const port = Number(process.env.SYNC_SERVER_PORT ?? 1234);
createSyncServer(port);
// eslint-disable-next-line no-console
console.log(`relay sync-server listening on ws://localhost:${port}`);
