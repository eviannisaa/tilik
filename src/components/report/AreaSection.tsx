import { For, Show } from "solid-js";
import Compass from "lucide-solid/icons/compass";
import type { AreaInfo } from "../../lib/types";
import { formatDecimal, formatDistance, titleCase } from "../../lib/format";
import ReportSection from "./ReportSection";

export default function AreaSection(props: { area: AreaInfo; index: number }) {
     return (
          <ReportSection
               index={props.index}
               title="Area"
               lede="Which administrative area this falls in, and what surrounds it."
               icon={<Compass size={15} />}
          >
               <dl class="grid gap-x-8 gap-y-5 text-sm sm:grid-cols-2">
                    <div>
                         <dt class="text-ink-faint capitalize font-sans text-xs">
                              Administrative area
                         </dt>
                         <dd class="mt-2 text-ink">
                              {props.area.administrativeArea ??
                                   "Not identified"}
                         </dd>
                    </div>
                    <div>
                         <dt class="text-ink-faint capitalize font-sans text-xs">
                              Country
                         </dt>
                         <dd class="mt-2 text-ink">
                              {props.area.country ?? "—"}
                         </dd>
                    </div>
                    <div>
                         <dt class="text-ink-faint capitalize font-sans text-xs">
                              Coordinates
                         </dt>
                         <dd class="tilik-figure mt-2 text-ink">
                              {formatDecimal(props.area.coordinates.latitude)},{" "}
                              {formatDecimal(props.area.coordinates.longitude)}
                         </dd>
                    </div>
               </dl>

               <Show when={props.area.nearbyFeatures.length}>
                    <div class="mt-5 mb-5">
                         <p class="text-ink-faint capitalize font-sans text-xs">
                              Nearby features
                         </p>
                         <ul class="mt-2 flex flex-wrap gap-2">
                              <For each={props.area.nearbyFeatures}>
                                   {(feature) => (
                                        <li class="rounded-full border border-line bg-paper px-3 py-1.5 text-xs text-ink-soft">
                                             {feature.name}
                                             <span class="ml-1.5 text-ink-faint">
                                                  {titleCase(feature.kind)}
                                                  <Show
                                                       when={
                                                            feature.distanceMeters !==
                                                            null
                                                       }
                                                  >
                                                       {" · "}
                                                       {formatDistance(
                                                            feature.distanceMeters
                                                       )}
                                                  </Show>
                                             </span>
                                        </li>
                                   )}
                              </For>
                         </ul>
                    </div>
               </Show>
          </ReportSection>
     );
}
