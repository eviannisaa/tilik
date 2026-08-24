/**
 * Frontend runtime config. Only `PUBLIC_*` variables are readable here — keep
 * anything secret on the FastAPI side.
 */

const env = import.meta.env;

/**
 * Free, key-less vector style. Override with PUBLIC_MAP_STYLE_URL.
 *
 * `liberty` is bright and fully coloured — green parks, blue water — on a warm
 * off-white that matches the app's paper background. Swap in `bright` for a
 * softer palette, or `positron` for near-greyscale.
 */
export const MAP_STYLE_URL: string =
  env.PUBLIC_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/liberty";

/** Used when the configured style fails to load (offline, blocked, 404). */
export const MAP_STYLE_FALLBACK_URL = "https://demotiles.maplibre.org/style.json";

/** Same-origin by default: `/api/*` is rewritten to the Python function. */
export const API_BASE_URL: string = (env.PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

export const DEFAULT_CENTER: [number, number] = [
  Number(env.PUBLIC_DEFAULT_LNG ?? 107.6191),
  Number(env.PUBLIC_DEFAULT_LAT ?? -6.9175),
];

export const DEFAULT_ZOOM = Number(env.PUBLIC_DEFAULT_ZOOM ?? 11);

/** Zoom applied once a specific point is chosen. */
export const SELECTED_ZOOM = 15;

/**
 * The map's limits, as `[[west, south], [east, north]]`.
 *
 * The same box the API treats as its coverage area, in
 * `api.services.inarisk.COVERAGE_BOUNDS`: every hazard layer, the disaster
 * archive and the boundary polygons stop at Indonesia, so a pin dropped in
 * Malaysia or Australia produces a report with nothing in it. Letting the map
 * roam there offers a check the app cannot answer.
 *
 * Padded by roughly a degree on each side so the coastlines of Aceh and Papua
 * are not pinned against the edge of the viewport, and so a point genuinely on
 * the border is still reachable.
 */
export const INDONESIA_BOUNDS: [[number, number], [number, number]] = [
  [94.0, -12.0],
  [142.0, 7.0],
];

/**
 * Zoomed out far enough to see the archipelago, and no further.
 *
 * Without a floor, `maxBounds` still allows zooming out until Indonesia is a
 * smear in the middle of an ocean of empty tiles, which looks broken rather than
 * bounded.
 */
export const MIN_ZOOM = 4;
