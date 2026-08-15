/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_SOURCE?: "mock" | "dataverse";
  readonly VITE_DATAVERSE_URL?: string;
  readonly VITE_ENTRA_CLIENT_ID?: string;
  readonly VITE_ENTRA_TENANT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
