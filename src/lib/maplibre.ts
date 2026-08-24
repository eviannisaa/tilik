/**
 * MapLibre GL v6 stopped inlining its web worker. It now resolves a sibling
 * `maplibre-gl-worker.mjs` against `import.meta.url` — which, once the library
 * is bundled, points at a file the bundler never emitted. The worker 404s, the
 * map never fires `load`, and the UI sits on its loading state forever.
 *
 * `?worker&url` makes Vite bundle that worker (together with the shared chunk
 * it imports) and hand back a real, hashed URL. Registering it here, in the
 * single module every map import goes through, guarantees it happens before
 * any `Map` is constructed.
 */
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

setWorkerUrl(workerUrl);

export {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
} from "maplibre-gl";
