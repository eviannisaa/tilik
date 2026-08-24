import { For, Show } from "solid-js";
import Store from "lucide-solid/icons/store";
import type { NearbyPlaces } from "../../lib/types";
import { formatDistance } from "../../lib/format";
import Disclosure from "./Disclosure";
import ReportSection from "./ReportSection";

/**
 * What's actually around the plot, grouped by category with every place listed.
 *
 * "How far to a clinic" is the question people are really asking, and "how many
 * are there" is the follow-up: five inside 1.5 km and fourteen inside 1.5 km are
 * different places to buy land.
 */
export default function PlacesSection(props: {
     places: NearbyPlaces;
     index: number;
}) {
     /**
      * Whether the lookup actually happened.
      *
      * `none` means it did not — the provider timed out, or external APIs are off.
      * `low` means OpenStreetMap answered and had nothing here. The difference
      * matters more than anything else in this section: one is "there is nothing
      * nearby", the other is "we do not know", and the section printed the first
      * while meaning the second.
      */
     const searched = () => props.places.confidence !== "none";

     return (
          <ReportSection
               index={props.index}
               title="What's nearby"
               lede="Whether day-to-day essentials are within reach."
               icon={<Store size={15} />}
               confidence={props.places.confidence}
          >
               <p class="text-xs text-ink-faint">
                    <Show
                         when={searched()}
                         fallback={
                              <>
                                   Not checked:{" "}
                                   {formatDistance(props.places.radiusMeters)}{" "}
                                   around your coordinate
                              </>
                         }
                    >
                         {props.places.total} mapped place
                         {props.places.total === 1 ? "" : "s"} within{" "}
                         {formatDistance(props.places.radiusMeters)}
                    </Show>
               </p>

               <Show
                    when={props.places.categories.length}
                    fallback={
                         <div class="mt-4 border-t border-line pt-4 text-sm text-ink-soft">
                              <p class="text-ink">
                                   <Show
                                        when={searched()}
                                        fallback={
                                             <>
                                                  We couldn't check what's
                                                  nearby.
                                             </>
                                        }
                                   >
                                        Nothing mapped around this point.
                                   </Show>
                              </p>
                              <p class="mt-1 text-xs text-ink-faint">
                                   {props.places.note ??
                                        "That often means OpenStreetMap coverage is thin here, not that the area is empty."}
                              </p>
                         </div>
                    }
               >
                    <div class="mt-3 divide-y divide-line/50">
                         <For each={props.places.categories}>
                              {(category) => (
                                   <Disclosure
                                        class="py-2"
                                        summaryClass="text-sm text-olive-500"
                                        summary={
                                             <span class="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                                                  <span class="bg-olive-50 px-1 font-semibold">
                                                       {category.label}
                                                  </span>
                                                  <span class="shrink-0 text-sm text-ink-faint">
                                                       {category.count} nearby
                                                  </span>
                                             </span>
                                        }
                                   >
                                        <ul class="pl-[18px] flex flex-col gap-1.5">
                                             <For
                                                  each={category.places}
                                                  fallback={
                                                       <li class="text-sm text-ink-faint">
                                                            —
                                                       </li>
                                                  }
                                             >
                                                  {(place) => (
                                                       <li class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1">
                                                            <span class="min-w-0 flex-1 truncate text-xs text-ink-soft">
                                                                 {place.name}
                                                            </span>
                                                            <span class="tilik-figure shrink-0 text-xs text-ink-soft">
                                                                 {formatDistance(
                                                                      place.distanceMeters
                                                                 )}
                                                            </span>
                                                       </li>
                                                  )}
                                             </For>
                                        </ul>
                                   </Disclosure>
                              )}
                         </For>
                    </div>
               </Show>
          </ReportSection>
     );
}
