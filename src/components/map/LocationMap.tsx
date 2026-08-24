import {
     createEffect,
     createSignal,
     on,
     onCleanup,
     onMount,
     Show,
} from "solid-js";
import {
     AttributionControl,
     MapLibreMap,
     Marker,
     NavigationControl,
} from "../../lib/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import Crosshair from "lucide-solid/icons/crosshair";
import {
     DEFAULT_CENTER,
     DEFAULT_ZOOM,
     INDONESIA_BOUNDS,
     MAP_STYLE_FALLBACK_URL,
     MAP_STYLE_URL,
     MIN_ZOOM,
     SELECTED_ZOOM,
} from "../../lib/config";
import { locationStore } from "../../lib/store";
import MapSkeleton from "./MapSkeleton";
import MapUnavailable from "./MapUnavailable";

/** How long to wait for MapLibre's `load` before calling it a failure. */
const INIT_TIMEOUT_MS = 15_000;

/**
 * The map is deliberately under-controlled: zoom buttons, a marker, and click
 * to select. Everything else (search, geolocation, the check button) lives in
 * normal DOM around it so it stays keyboard-reachable on mobile.
 */
export default function LocationMap() {
     let container!: HTMLDivElement;
     let map: MapLibreMap | undefined;
     let marker: Marker | undefined;

     const [ready, setReady] = createSignal(false);
     const [styleFailed, setStyleFailed] = createSignal(false);
     const [initFailed, setInitFailed] = createSignal(false);
     let selectionFromMap = false;
     let usedFallbackStyle = false;
     let readyTimer: ReturnType<typeof setTimeout> | undefined;

     function buildMarkerElement(): HTMLDivElement {
          const el = document.createElement("div");
          el.className = "tilik-marker";
          el.innerHTML = `
      <span class="tilik-marker__ping"></span>
      <span class="tilik-marker__pin"></span>
    `;
          return el;
     }

     onMount(() => {
          readyTimer = setTimeout(() => {
               if (!ready()) setInitFailed(true);
          }, INIT_TIMEOUT_MS);

          try {
               initialiseMap();
          } catch (error) {
               console.error("[tilik/map] could not start MapLibre", error);
               map = undefined;
               setInitFailed(true);
          }
     });

     function initialiseMap() {
          map = new MapLibreMap({
               container,
               style: MAP_STYLE_URL,
               center: DEFAULT_CENTER,
               zoom: DEFAULT_ZOOM,
               attributionControl: false,
               pitchWithRotate: false,
               dragRotate: false,
               maxZoom: 18,
               maxBounds: INDONESIA_BOUNDS,
               minZoom: MIN_ZOOM,
          });

          map.addControl(
               new NavigationControl({ showCompass: false }),
               "top-right"
          );
          map.addControl(
               new AttributionControl({ compact: true }),
               "bottom-right"
          );
          map.touchZoomRotate.disableRotation();

          map.on("load", () => {
               clearTimeout(readyTimer);
               setReady(true);
          });

          map.on("error", (event) => {
               const message = String(event?.error?.message ?? "");
               const isStyleFailure =
                    message.includes("style") ||
                    message.includes("Failed to fetch");
               if (
                    isStyleFailure &&
                    !usedFallbackStyle &&
                    MAP_STYLE_URL !== MAP_STYLE_FALLBACK_URL
               ) {
                    usedFallbackStyle = true;
                    setStyleFailed(true);
                    map?.setStyle(MAP_STYLE_FALLBACK_URL);
                    return;
               }
               if (import.meta.env.DEV)
                    console.warn("[tilik/map]", event?.error);
          });

          map.on("click", (event) => {
               selectionFromMap = true;
               locationStore.select({
                    latitude: Number(event.lngLat.lat.toFixed(6)),
                    longitude: Number(event.lngLat.wrap().lng.toFixed(6)),
                    name: null,
                    origin: "map",
               });
          });

          map.getCanvas().style.cursor = "crosshair";
     }

     createEffect(
          on(locationStore.selected, (selected) => {
               if (!map) return;

               if (!selected) {
                    marker?.remove();
                    marker = undefined;
                    return;
               }

               const position: [number, number] = [
                    selected.longitude,
                    selected.latitude,
               ];

               if (!marker) {
                    marker = new Marker({
                         element: buildMarkerElement(),
                         anchor: "bottom",
                    })
                         .setLngLat(position)
                         .addTo(map);
               } else {
                    marker.setLngLat(position);
               }

               if (selectionFromMap) {
                    selectionFromMap = false;
                    return;
               }

               map.flyTo({
                    center: position,
                    zoom: Math.max(map.getZoom(), SELECTED_ZOOM),
                    speed: 1.2,
                    essential: true,
               });
          })
     );

     onCleanup(() => {
          clearTimeout(readyTimer);
          try {
               marker?.remove();
               map?.remove();
          } catch (error) {
               if (import.meta.env.DEV)
                    console.warn("[tilik/map] cleanup failed", error);
          }
     });

     return (
          <div class="relative h-full w-full overflow-hidden rounded-card border border-line bg-paper-sunk">
               <div
                    ref={container}
                    class="h-full w-full"
                    aria-label="Map. Click anywhere to select a location."
               />

               <Show when={!ready() && !initFailed()}>
                    <MapSkeleton />
               </Show>

               <Show when={initFailed()}>
                    <MapUnavailable />
               </Show>

               <Show when={ready()}>
                    <div class="pointer-events-none absolute bottom-3 left-3 flex items-center gap-1.5 rounded-full border border-line bg-paper-raised/90 px-2.5 py-1.5 text-[0.7rem] text-ink-soft backdrop-blur-sm">
                         <Crosshair size={13} />
                         <span>Tap the map to drop a pin</span>
                    </div>
               </Show>

               <Show when={styleFailed()}>
                    <div class="pointer-events-none absolute top-3 left-3 rounded-full border border-khaki-200 bg-khaki-50 px-2.5 py-1.5 text-[0.7rem] text-khaki-700">
                         Using the basic basemap
                    </div>
               </Show>
          </div>
     );
}
