import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';

const connectionString = process.env.DATABASE_URL || 'postgres://postgres:password@localhost:5432/relay';
const client = postgres(connectionString);
export const db = drizzle(client, { schema });
export * from './schema';
