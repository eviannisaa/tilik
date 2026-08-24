import { Show } from "solid-js";
import ArrowRight from "lucide-solid/icons/arrow-right";
import Crosshair from "lucide-solid/icons/crosshair";
import Hand from "lucide-solid/icons/hand";
import Keyboard from "lucide-solid/icons/keyboard";
import LocateFixed from "lucide-solid/icons/locate-fixed";
import MapPin from "lucide-solid/icons/map-pin";
import Search from "lucide-solid/icons/search";
import X from "lucide-solid/icons/x";
import { displayStore, locationStore } from "../../lib/store";
import { formatAxis, formatPair } from "../../lib/coordinates";
import { adminChain } from "../../lib/format";
import Button from "../ui/Button";
import CopyButton from "../ui/CopyButton";
import Panel from "../ui/Panel";
import Skeleton from "../ui/Skeleton";
import CoordinateFormatPicker from "./CoordinateFormatPicker";
import { LandPlot, Locate, MapPinSearch, Trash } from "lucide-solid";

/** How the point got picked. An icon reads faster than a line of small caps. */
const ORIGIN = {
     search: { label: "From search", icon: Search },
     map: { label: "From the map", icon: Hand },
     geolocation: { label: "Your location", icon: LocateFixed },
     coordinates: { label: "Typed in", icon: Keyboard },
} as const;

/** Uppercase metadata label. Colour is spent on the pin, not on chrome. */
const META_PILL =
     "inline-flex font-sans items-center gap-1.5 rounded-full bg-paper-sunk px-2.5 py-1 text-xs font-medium tracking-[0.02em] text-ink-soft";

export default function SelectedLocation() {
     const selected = locationStore.selected;
     const busy = () => locationStore.reportStatus() === "loading";

     const origin = () => ORIGIN[selected()?.origin ?? "search"];

     return (
          <Show
               when={selected()}
               fallback={
                    <Panel class="overflow-hidden">
                         <div class="p-6">
                              <span class={META_PILL}>
                                   <Locate
                                        size={12}
                                        strokeWidth={2.25}
                                        class="shrink-0 text-clay-600"
                                   />
                                   Awaiting a point
                              </span>

                              <p class="font-display flex items-center justify-center h-46 text-sm leading-[1.1] tracking-[-0.02em] text-ink text-center">
                                   Nothing picked yet.
                              </p>
                         </div>
                    </Panel>
               }
          >
               {(location) => (
                    <Panel class="overflow-hidden">
                         <div class="px-6 pt-6 pb-4">
                              <div class="flex items-start justify-between gap-3 mb-4.5">
                                   <span class={META_PILL}>
                                        {(() => {
                                             const Icon = origin().icon;
                                             return (
                                                  <Icon
                                                       size={12}
                                                       strokeWidth={2.25}
                                                       class="shrink-0 text-clay-600"
                                                  />
                                             );
                                        })()}
                                        {origin().label}
                                   </span>

                                   <button
                                        type="button"
                                        onClick={() => locationStore.clear()}
                                        aria-label="Clear this location"
                                        class="-mr-1.5 flex shrink-0 items-center gap-1 p-1.5 text-xs rounded-full text-clay-600 transition-colors duration-200 hover:text-clay-500 ease-in-out"
                                   >
                                        <Trash size={13} strokeWidth={2} />
                                        Clear
                                   </button>
                              </div>

                              <Show
                                   when={location().name}
                                   fallback={
                                        <Show
                                             when={locationStore.resolvingName()}
                                             fallback={
                                                  <p class="font-display text-[1.6rem] leading-[1.1] tracking-[-0.02em] text-ink-faint sm:text-[1.9rem]">
                                                       Unnamed spot
                                                  </p>
                                             }
                                        >
                                             <div class="mt-2 flex items-center gap-2">
                                                  <Skeleton class="h-6 w-56" />
                                             </div>
                                             <p class="mt-2 text-xs text-ink-faint">
                                                  Looking up the name…
                                             </p>
                                        </Show>
                                   }
                              >
                                   <div class="min-w-0">
                                        <h2
                                             title={
                                                  location().name ?? undefined
                                             }
                                             class="font-display font-medium truncate text-lg leading-[1.2] text-ink"
                                        >
                                             {location().name}
                                        </h2>

                                        <Show
                                             when={
                                                  adminChain(location()).length
                                             }
                                        >
                                             <p
                                                  class="mt-1 truncate text-xs text-ink-faint"
                                                  title={adminChain(
                                                       location()
                                                  ).join(", ")}
                                             >
                                                  {adminChain(location()).join(
                                                       ", "
                                                  )}
                                             </p>
                                        </Show>
                                   </div>
                              </Show>
                         </div>

                         <div class="flex items-center justify-between gap-x-3 gap-y-4 px-6">
                              <p class="flex items-center min-w-0 truncate text-sm text-olive-700">
                                   <MapPin
                                        size={13}
                                        strokeWidth={2.5}
                                        class="mr-1.5 inline-block shrink-0 text-clay-600"
                                   />
                                   {formatAxis(
                                        location().latitude,
                                        "lat",
                                        displayStore.coordinateFormat()
                                   )}
                                   <span class="mx-1.5 text-clay-600">·</span>
                                   {formatAxis(
                                        location().longitude,
                                        "lng",
                                        displayStore.coordinateFormat()
                                   )}
                              </p>
                              {/* <CopyButton
                                   label="Copy coordinates"
                                   value={formatPair(
                                        location().latitude,
                                        location().longitude,
                                        displayStore.coordinateFormat()
                                   )}
                              /> */}
                         </div>

                         <div class=" px-5 py-5 sm:px-7">
                              <Button
                                   size="lg"
                                   quiet
                                   class="w-full justify-between"
                                   loading={busy()}
                                   onClick={() => void locationStore.check()}
                              >
                                   {busy()
                                        ? "Reading the ground…"
                                        : "Check the ground"}
                                   <Show when={!busy()}>
                                        <ArrowRight size={17} strokeWidth={2} />
                                   </Show>
                              </Button>

                              <p class="mt-2.5 text-center text-[0.7rem] leading-relaxed text-ink-faint">
                                   Terrain, flood, hazards, past disasters and
                                   what's nearby
                              </p>
                         </div>
                    </Panel>
               )}
          </Show>
     );
}
