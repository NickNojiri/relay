#!/usr/bin/env node
/**
 * Seed the Horn Center's resources and the active booking policy into Dataverse.
 *
 * Run after scripts/provision-dataverse.mjs. Edit RESOURCES to match the real
 * inventory before running it against anything but a dev environment.
 *
 *   export DATAVERSE_URL="https://orgXXXXX.crm.dynamics.com"
 *   export DATAVERSE_TOKEN="..."          # or AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET
 *   node scripts/seed-dataverse.mjs [--dry-run]
 */

const PREFIX = process.env.HCR_PREFIX ?? "hcr";
const API_VERSION = "v9.2";
const DRY_RUN = process.argv.includes("--dry-run");
const orgUrl = (process.env.DATAVERSE_URL ?? "").replace(/\/$/, "");

if (!orgUrl && !DRY_RUN) {
  console.error("error: DATAVERSE_URL is required");
  process.exit(1);
}

const KIND = { workstation: 1, "collab-room": 2, equipment: 3 };

const RESOURCES = [
  { name: "Workstation 1", kind: "workstation", location: "Horn Center — Main Lab", capacity: 1, features: "dual-monitor;Adobe CC" },
  { name: "Workstation 2", kind: "workstation", location: "Horn Center — Main Lab", capacity: 1, features: "dual-monitor;Adobe CC" },
  { name: "Workstation 3", kind: "workstation", location: "Horn Center — Main Lab", capacity: 1, features: "SPSS;MATLAB" },
  { name: "Workstation 4", kind: "workstation", location: "Horn Center — Quiet Row", capacity: 1, features: "standing desk" },
  { name: "Workstation 5", kind: "workstation", location: "Horn Center — Quiet Row", capacity: 1, features: "accessible desk" },
  { name: "Collab Room A", kind: "collab-room", location: "Horn Center — 2nd Floor", capacity: 6, features: "whiteboard;display" },
  { name: "Collab Room B", kind: "collab-room", location: "Horn Center — 2nd Floor", capacity: 4, features: "whiteboard" },
  { name: "Camera Kit", kind: "equipment", location: "Horn Center — Front Desk", capacity: 1, features: "DSLR;tripod" },
  { name: "VR Headset", kind: "equipment", location: "Horn Center — Front Desk", capacity: 1, features: "Quest 3;controllers" },
];

const POLICY = {
  [`${PREFIX}_name`]: "Default policy",
  [`${PREFIX}_slotminutes`]: 30,
  [`${PREFIX}_minduration`]: 30,
  [`${PREFIX}_maxduration`]: 120,
  [`${PREFIX}_maxminutesperday`]: 180,
  [`${PREFIX}_maxminutesperweek`]: 600,
  [`${PREFIX}_maxactive`]: 3,
  [`${PREFIX}_advancedays`]: 7,
  [`${PREFIX}_checkingrace`]: 15,
  [`${PREFIX}_openhoursjson`]: JSON.stringify({
    0: { open: "12:00", close: "18:00" },
    1: { open: "07:30", close: "22:00" },
    2: { open: "07:30", close: "22:00" },
    3: { open: "07:30", close: "22:00" },
    4: { open: "07:30", close: "22:00" },
    5: { open: "07:30", close: "18:00" },
    6: { open: "09:00", close: "17:00" },
  }),
  [`${PREFIX}_blackoutsjson`]: JSON.stringify([]),
};

let token;

async function getToken() {
  if (process.env.DATAVERSE_TOKEN) return process.env.DATAVERSE_TOKEN;
  const { AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET } = process.env;
  if (!AZURE_TENANT_ID || !AZURE_CLIENT_ID || !AZURE_CLIENT_SECRET) {
    console.error("error: set DATAVERSE_TOKEN or the AZURE_* client-credentials variables");
    process.exit(1);
  }
  const response = await fetch(
    `https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/token`,
    {
      method: "POST",
      body: new URLSearchParams({
        client_id: AZURE_CLIENT_ID,
        client_secret: AZURE_CLIENT_SECRET,
        grant_type: "client_credentials",
        scope: `${orgUrl}/.default`,
      }),
    },
  );
  if (!response.ok) {
    console.error(`error: token request failed ${response.status}`);
    process.exit(1);
  }
  return (await response.json()).access_token;
}

async function post(entitySet, row) {
  if (DRY_RUN) {
    console.log(`[dry-run] POST /${entitySet}`, JSON.stringify(row));
    return;
  }
  token ??= await getToken();
  const response = await fetch(`${orgUrl}/api/data/${API_VERSION}/${entitySet}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8",
      "OData-MaxVersion": "4.0",
      "OData-Version": "4.0",
    },
    body: JSON.stringify(row),
  });
  if (!response.ok) throw new Error(`POST /${entitySet} → ${response.status}\n${await response.text()}`);
}

async function main() {
  for (const resource of RESOURCES) {
    console.log(`• ${resource.name}`);
    await post(`${PREFIX}_resources`, {
      [`${PREFIX}_name`]: resource.name,
      [`${PREFIX}_kind`]: KIND[resource.kind],
      [`${PREFIX}_location`]: resource.location,
      [`${PREFIX}_capacity`]: resource.capacity,
      [`${PREFIX}_features`]: resource.features,
    });
  }

  console.log("• default booking policy");
  await post(`${PREFIX}_policies`, POLICY);

  console.log("\nSeeded. Publish customizations and reload the app.");
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exit(1);
});
