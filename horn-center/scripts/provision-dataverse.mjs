#!/usr/bin/env node
/**
 * Create the Horn Center tables in Dataverse from code.
 *
 * This is the "automate the Microsoft suite" part: instead of clicking through
 * make.powerapps.com, the schema is a file you can diff, review and re-run
 * against a second environment (dev -> test -> prod) and get an identical result.
 *
 * What it creates, all inside one unmanaged solution:
 *   hcr_resource     — a bookable thing (workstation, collab room, equipment)
 *   hcr_reservation  — one booking, with a lookup to hcr_resource
 *   hcr_policy       — the booking rules, editable by staff without a redeploy
 *
 * Usage:
 *   export DATAVERSE_URL="https://orgXXXXX.crm.dynamics.com"
 *   export DATAVERSE_TOKEN="$(pac auth create --environment $DATAVERSE_URL && pac org who --json | ...)"
 *   # or, for an unattended service principal:
 *   export AZURE_TENANT_ID=... AZURE_CLIENT_ID=... AZURE_CLIENT_SECRET=...
 *   node scripts/provision-dataverse.mjs [--dry-run]
 *
 * It is idempotent-ish: components that already exist come back as a duplicate
 * error, which is logged and skipped rather than aborting the run.
 *
 * NOT YET RUN AGAINST A LIVE ORG. The payload shapes follow the documented
 * Dataverse metadata API, but budget an hour for the first run — expect to fix
 * a label or a required-level here or there.
 */

const PREFIX = process.env.HCR_PREFIX ?? "hcr";
const SOLUTION = process.env.HCR_SOLUTION ?? "HornCenterReservations";
const API_VERSION = "v9.2";
const LCID = 1033;
const DRY_RUN = process.argv.includes("--dry-run");

const orgUrl = (process.env.DATAVERSE_URL ?? "").replace(/\/$/, "");
if (!orgUrl && !DRY_RUN) {
  fail("DATAVERSE_URL is required (e.g. https://orgXXXXX.crm.dynamics.com)");
}

// ---------------------------------------------------------------- helpers

function label(text) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.Label",
    LocalizedLabels: [
      {
        "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
        Label: text,
        LanguageCode: LCID,
      },
    ],
  };
}

const REQUIRED = {
  Value: "ApplicationRequired",
  CanBeChanged: true,
  ManagedPropertyLogicalName: "canmodifyrequirementlevelsettings",
};

const OPTIONAL = {
  Value: "None",
  CanBeChanged: true,
  ManagedPropertyLogicalName: "canmodifyrequirementlevelsettings",
};

function text(schemaName, display, maxLength = 100, requirement = OPTIONAL, isPrimary = false) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(display),
    RequiredLevel: requirement,
    MaxLength: maxLength,
    FormatName: { Value: "Text" },
    ...(isPrimary ? { IsPrimaryName: true } : {}),
  };
}

function memo(schemaName, display, maxLength = 4000) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(display),
    RequiredLevel: OPTIONAL,
    MaxLength: maxLength,
  };
}

function whole(schemaName, display, min = 0, max = 100000, requirement = OPTIONAL) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(display),
    RequiredLevel: requirement,
    MinValue: min,
    MaxValue: max,
    Format: "None",
  };
}

/**
 * DateTimeBehavior UserLocal stores UTC and renders in the viewer's time zone —
 * correct here, because a reservation is a real instant, not a floating wall time.
 */
function dateTime(schemaName, display, requirement = OPTIONAL) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(display),
    RequiredLevel: requirement,
    Format: "DateAndTime",
    DateTimeBehavior: { Value: "UserLocal" },
  };
}

function choice(schemaName, display, options, requirement = REQUIRED) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.PicklistAttributeMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(display),
    RequiredLevel: requirement,
    OptionSet: {
      "@odata.type": "Microsoft.Dynamics.CRM.OptionSetMetadata",
      IsGlobal: false,
      OptionSetType: "Picklist",
      Options: options.map(([value, name]) => ({ Value: value, Label: label(name) })),
    },
  };
}

function table(schemaName, singular, plural, primary, attributes) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
    SchemaName: `${PREFIX}_${schemaName}`,
    DisplayName: label(singular),
    DisplayCollectionName: label(plural),
    OwnershipType: "UserOwned",
    HasActivities: false,
    HasNotes: false,
    IsActivity: false,
    Attributes: [primary, ...attributes],
  };
}

// ---------------------------------------------------------------- schema

const RESOURCE = table(
  "Resource",
  "Resource",
  "Resources",
  text("Name", "Name", 100, REQUIRED, true),
  [
    choice("Kind", "Kind", [
      [1, "Workstation"],
      [2, "Collab room"],
      [3, "Equipment"],
    ]),
    text("Location", "Location", 150),
    whole("Capacity", "Capacity", 1, 500),
    // Semicolon-separated; a child table would be tidier but is more than this needs.
    text("Features", "Features", 400),
  ],
);

const RESERVATION = table(
  "Reservation",
  "Reservation",
  "Reservations",
  text("Name", "Reference", 200, REQUIRED, true),
  [
    // The Entra ID object id — the stable identifier. Never key off email:
    // students change names and addresses, the oid never moves.
    text("StudentAadId", "Student (Entra object id)", 64, REQUIRED),
    text("StudentName", "Student name", 150),
    dateTime("StartsAt", "Starts at", REQUIRED),
    dateTime("EndsAt", "Ends at", REQUIRED),
    choice("Status", "Status", [
      [1, "Booked"],
      [2, "Checked in"],
      [3, "Completed"],
      [4, "Cancelled"],
      [5, "No-show"],
    ]),
    dateTime("CheckedInAt", "Checked in at"),
    text("Purpose", "Purpose", 100),
  ],
);

const POLICY = table(
  "Policy",
  "Booking policy",
  "Booking policies",
  text("Name", "Name", 100, REQUIRED, true),
  [
    whole("SlotMinutes", "Slot length (minutes)", 5, 240),
    whole("MinDuration", "Minimum booking (minutes)", 5, 480),
    whole("MaxDuration", "Maximum booking (minutes)", 5, 1440),
    whole("MaxMinutesPerDay", "Daily cap (minutes)", 0, 1440),
    whole("MaxMinutesPerWeek", "Weekly cap (minutes)", 0, 10080),
    whole("MaxActive", "Concurrent bookings", 1, 50),
    whole("AdvanceDays", "Booking horizon (days)", 1, 180),
    whole("CheckinGrace", "Check-in grace (minutes)", 0, 120),
    memo("OpenHoursJson", "Open hours (JSON)", 2000),
    memo("BlackoutsJson", "Blackouts (JSON)", 8000),
  ],
);

/** One resource has many reservations. */
const RESOURCE_LOOKUP = {
  "@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata",
  SchemaName: `${PREFIX}_resource_${PREFIX}_reservation`,
  ReferencedEntity: `${PREFIX}_resource`,
  ReferencingEntity: `${PREFIX}_reservation`,
  Lookup: {
    "@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata",
    SchemaName: `${PREFIX}_Resource`,
    DisplayName: label("Resource"),
    RequiredLevel: REQUIRED,
  },
  AssociatedMenuConfiguration: {
    Behavior: "UseCollectionName",
    Group: "Details",
    Order: 10000,
  },
  CascadeConfiguration: {
    Assign: "NoCascade",
    Delete: "Restrict",
    Merge: "NoCascade",
    Reparent: "NoCascade",
    Share: "NoCascade",
    Unshare: "NoCascade",
  },
};

// ---------------------------------------------------------------- transport

async function getToken() {
  if (process.env.DATAVERSE_TOKEN) return process.env.DATAVERSE_TOKEN;

  const { AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET } = process.env;
  if (!AZURE_TENANT_ID || !AZURE_CLIENT_ID || !AZURE_CLIENT_SECRET) {
    fail(
      "Provide DATAVERSE_TOKEN, or AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET for client-credentials auth.",
    );
  }

  const body = new URLSearchParams({
    client_id: AZURE_CLIENT_ID,
    client_secret: AZURE_CLIENT_SECRET,
    grant_type: "client_credentials",
    scope: `${orgUrl}/.default`,
  });

  const response = await fetch(
    `https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/token`,
    { method: "POST", body },
  );
  if (!response.ok) fail(`Token request failed: ${response.status} ${await response.text()}`);
  return (await response.json()).access_token;
}

let token;

async function send(path, payload, { method = "POST" } = {}) {
  if (DRY_RUN) {
    console.log(`[dry-run] ${method} ${path}`);
    console.log(JSON.stringify(payload, null, 2).slice(0, 400) + "\n");
    return { dryRun: true };
  }

  token ??= await getToken();
  const response = await fetch(`${orgUrl}/api/data/${API_VERSION}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json; charset=utf-8",
      "OData-MaxVersion": "4.0",
      "OData-Version": "4.0",
      // Files every created component into the solution instead of Common Data
      // Services Default — this is what makes the result exportable.
      "MSCRM.SolutionUniqueName": SOLUTION,
    },
    body: JSON.stringify(payload),
  });

  if (response.ok) return response.status === 204 ? {} : safeJson(response);

  const detail = await response.text();
  if (/duplicate|already exists|existing/i.test(detail)) {
    console.log(`  ↷ already exists, skipping`);
    return { skipped: true };
  }
  throw new Error(`${method} ${path} → ${response.status}\n${detail}`);
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

// ---------------------------------------------------------------- run

async function main() {
  console.log(
    DRY_RUN
      ? `Dry run — printing payloads for prefix "${PREFIX}", solution "${SOLUTION}".`
      : `Provisioning "${SOLUTION}" in ${orgUrl} with prefix "${PREFIX}".`,
  );

  for (const definition of [RESOURCE, RESERVATION, POLICY]) {
    console.log(`\n• table ${definition.SchemaName}`);
    await send("/EntityDefinitions", definition);
  }

  console.log(`\n• relationship ${RESOURCE_LOOKUP.SchemaName}`);
  await send("/RelationshipDefinitions", RESOURCE_LOOKUP);

  console.log(`
Done. Next:
  1. Publish customizations:   pac solution publish
  2. Seed rows:                node scripts/seed-dataverse.mjs
  3. Point the app at the org: VITE_DATA_SOURCE=dataverse VITE_DATAVERSE_URL=${orgUrl || "<org url>"}
  4. Export the solution:      pac solution export --name ${SOLUTION} --path ./solution
`);
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exit(1);
});
