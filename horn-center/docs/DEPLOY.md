# Deploy

Three environments, one solution, promoted by export/import. Nothing is edited
directly in test or production — if you fix something there, the next import
overwrites it.

```
dev  ──export──> git ──import──> test ──import──> prod
```

## Environments

| Environment | Purpose | Who can edit |
|---|---|---|
| `HornCenter-Dev` | Where you build. Unmanaged solution. | you |
| `HornCenter-Test` | Staff acceptance. Managed solution. | nobody |
| `HornCenter-Prod` | Students. Managed solution. | nobody |

Ask ITS for all three at once — asking for prod later, separately, restarts the
approval conversation.

## Export the solution to source control

```bash
pac solution export \
  --name HornCenterReservations \
  --path ./solution/HornCenterReservations.zip \
  --managed false

pac solution unpack \
  --zipfile ./solution/HornCenterReservations.zip \
  --folder ./solution/src \
  --packagetype Unmanaged
```

Commit `solution/src`. That folder is the reviewable form — table definitions,
choice values, forms, views and flow definitions as files you can diff. The `.zip`
is a build artifact; leave it out of git.

## Import to test or production

```bash
pac auth create --environment https://horncenter-test.crm.dynamics.com

pac solution pack \
  --zipfile ./out/HornCenterReservations_managed.zip \
  --folder ./solution/src \
  --packagetype Managed

pac solution import \
  --path ./out/HornCenterReservations_managed.zip \
  --activate-plugins \
  --force-overwrite
```

Import **managed** to test and prod. Managed solutions can be cleanly uninstalled;
unmanaged ones bleed components into the environment permanently, and there is no
undo.

## The React app

### Code App

```bash
cd horn-center/app
npm run build
pac code push          # targets whichever environment `pac auth` points at
```

Check `pac auth list` before every push. Pushing dev code to prod because the
CLI was still authenticated elsewhere is the single most common way to break a
Friday.

### Standalone SPA

```bash
npm run build          # emits app/dist
```

Deploy `dist/` to Azure Static Web Apps or campus hosting. `vite.config.ts` sets
`base: "./"` so it works from a subpath.

Environment variables at build time:

```
VITE_DATA_SOURCE=dataverse
VITE_DATAVERSE_URL=https://horncenter-prod.crm.dynamics.com
VITE_ENTRA_CLIENT_ID=<app registration id>
VITE_ENTRA_TENANT_ID=<CSULB tenant id>
```

These are compiled into the bundle and are **public**. That is fine — a client id
and a tenant id are not secrets. Never put a client *secret* in a `VITE_` variable;
the SPA flow (PKCE) does not need one.

## CI

```yaml
# .github/workflows/horn-center.yml
name: Horn Center

on:
  push:
    paths: ["horn-center/**"]
  pull_request:
    paths: ["horn-center/**"]

jobs:
  app:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: horn-center/app
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
```

To promote the solution from CI as well, add `microsoft/powerplatform-actions`:

```yaml
      - uses: microsoft/powerplatform-actions/import-solution@v1
        with:
          environment-url: ${{ secrets.PP_TEST_URL }}
          app-id: ${{ secrets.PP_CLIENT_ID }}
          client-secret: ${{ secrets.PP_CLIENT_SECRET }}
          tenant-id: ${{ secrets.PP_TENANT_ID }}
          solution-file: out/HornCenterReservations_managed.zip
```

The service principal behind `PP_CLIENT_ID` needs a System Customizer role in the
target environment. Ask ITS for it at the same time as the environments — it is a
much easier request bundled with the others than raised on its own three weeks later.

## Rollback

```bash
pac solution import --path ./out/HornCenterReservations_managed_PREVIOUS.zip --force-overwrite
```

Keep the last known-good managed zip as a release artifact. Solution import does
not roll back **data** — a schema change that dropped a column has already taken
the data with it. Never remove a column in the same release that ships a feature;
stop writing to it first, ship, then remove it in the next release.
