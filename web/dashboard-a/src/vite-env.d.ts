/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOCK_WS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
