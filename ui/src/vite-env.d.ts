/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" serves the bundled recorded runs instead of calling the API. */
  readonly VITE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
