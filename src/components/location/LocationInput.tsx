import { createEffect, createSignal, on, Show } from "solid-js";
import MapPin from "lucide-solid/icons/map-pin";
import Crosshair from "lucide-solid/icons/crosshair";
import LocateFixed from "lucide-solid/icons/locate-fixed";
import { cn } from "../../lib/cn";
import { displayStore, locationStore } from "../../lib/store";
import type { InputMode } from "../../lib/store";
import CoordinateInput from "./CoordinateInput";
import SearchBar from "./SearchBar";

/**
 * Picks between searching for a place and typing coordinates directly, and owns
 * the "use my location" button so it stays available in both modes.
 */
export default function LocationInput() {
     let root!: HTMLDivElement;
     const mode = displayStore.inputMode;
     const setMode = displayStore.setInputMode;
     const [locating, setLocating] = createSignal(false);
     const [geoError, setGeoError] = createSignal<string | null>(null);

     function useMyLocation() {
          if (!("geolocation" in navigator)) {
               setGeoError("This browser can't share your location.");
               return;
          }

          setLocating(true);
          setGeoError(null);

          navigator.geolocation.getCurrentPosition(
               (position) => {
                    setLocating(false);
                    locationStore.select({
                         latitude: Number(position.coords.latitude.toFixed(6)),
                         longitude: Number(
                              position.coords.longitude.toFixed(6)
                         ),
                         name: null,
                         origin: "geolocation",
                    });
               },
               (error) => {
                    setLocating(false);
                    setGeoError(
                         error.code === error.PERMISSION_DENIED
                              ? "Location access is blocked. Search, enter coordinates, or tap the map."
                              : "Couldn't get your location. Search, enter coordinates, or tap the map."
                    );
               },
               { enableHighAccuracy: true, timeout: 12_000, maximumAge: 60_000 }
          );
     }

     createEffect(
          on(
               displayStore.focusRequest,
               () =>
                    root
                         ?.querySelector<HTMLElement>("input, textarea")
                         ?.focus(),
               { defer: true }
          )
     );

     const tab = (value: InputMode) =>
          cn(
               "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
               mode() === value
                    ? "bg-olive-500 text-paper shadow-lift"
                    : "text-ink-soft hover:bg-paper-sunk hover:text-ink"
          );

     return (
          <div ref={root} class="space-y-2.5">
               <div class="flex flex-wrap items-center justify-between gap-2">
                    <div
                         role="tablist"
                         aria-label="How to choose a location"
                         class="flex items-center gap-1 rounded-full border border-line bg-paper-raised p-1"
                    >
                         <button
                              type="button"
                              role="tab"
                              aria-selected={mode() === "place"}
                              class={tab("place")}
                              onClick={() => setMode("place")}
                         >
                              <MapPin size={13} />
                              Search a place
                         </button>
                         <button
                              type="button"
                              role="tab"
                              aria-selected={mode() === "coordinates"}
                              class={tab("coordinates")}
                              onClick={() => setMode("coordinates")}
                         >
                              <Crosshair size={13} />
                              Coordinates
                         </button>
                    </div>

                    <button
                         type="button"
                         onClick={useMyLocation}
                         disabled={locating()}
                         class="flex items-center gap-1.5 rounded-full border border-line bg-paper-raised px-3 py-1.5 text-xs text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-60"
                    >
                         <span class={locating() ? "animate-pulse" : undefined}>
                              <LocateFixed size={13} />
                         </span>
                         {locating() ? "Locating…" : "Use my location"}
                    </button>
               </div>

               <Show when={mode() === "place"} fallback={<CoordinateInput />}>
                    <SearchBar />
               </Show>

               <Show when={geoError()}>
                    <p class="pl-4 text-xs text-clay-700">{geoError()}</p>
               </Show>
          </div>
     );
}
