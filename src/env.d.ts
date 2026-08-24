/// <reference types="astro/client" />

interface ImportMetaEnv {
  /** MapLibre style URL. Must be public — never put a secret key here. */
  readonly PUBLIC_MAP_STYLE_URL?: string;
  /** Override only if the API is not served from the same origin. */
  readonly PUBLIC_API_BASE_URL?: string;
  readonly PUBLIC_DEFAULT_LAT?: string;
  readonly PUBLIC_DEFAULT_LNG?: string;
  readonly PUBLIC_DEFAULT_ZOOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
