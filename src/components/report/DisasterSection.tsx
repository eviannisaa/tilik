import { createSignal, For, Match, Show, Switch } from "solid-js";
import History from "lucide-solid/icons/history";
import ExternalLink from "lucide-solid/icons/external-link";
import type { DisasterHistory } from "../../lib/types";
import {
     formatDate,
     formatDistance,
     formatImpact,
     formatIntensity,
     formatMagnitude,
     relativeYears,
     titleCase,
} from "../../lib/format";
import Disclosure from "./Disclosure";
import ReportSection from "./ReportSection";
import { Activity, MapPin, Pin, Waves } from "lucide-solid";

const INITIAL_EVENTS = 3;

/**
 * What an area record's figure is, and what it is not.
 *
 * This lives in a hover note rather than in the panel. Pinned open it was a
 * three-line paragraph of small print above every list, read once and then
 * skipped — while the moment it is actually wanted is when a reader stops at
 * one figure and asks what it measures. Each row's own label already says
 * which of the three kinds it is; this says why that distinction exists.
 */

/**
 * The provider's estimated-impact level, when it carries information.
 *
 * `green` means "no significant impact expected". It is the answer for 96 of
 * the 99 Indonesian earthquakes PAGER runs on each year, so showing it put a
 * chip on nearly every row that said nothing. Anything above green is rare and
 * worth reading.
 */
function meaningfulAlert(severity: string | null): string | null {
     if (!severity) return null;
     const level = severity.toLowerCase();
     return level === "green" ? null : level;
}

export default function DisasterSection(props: {
     disasters: DisasterHistory;
     index: number;
}) {
     const [showAll, setShowAll] = createSignal(false);

     /** A dozen rows buries the sections below it; five is enough to get the shape. */
     const events = () =>
          showAll()
               ? props.disasters.events
               : props.disasters.events.slice(0, INITIAL_EVENTS);

     /**
      * Whether any row is held for an area rather than a measured spot.
      *
      * One flat list keeps every distance visible and comparable. The marker is
      * what stops an area's distance being read as the event's own: the figure is
      * how far that area is, and the event sat somewhere inside it.
      */
     const hasApproximate = () =>
          props.disasters.events.some((event) => event.scope !== "point");

     const onlyQuakes = () => {
          const types = props.disasters.coveredTypes;
          return (
               types.length > 0 && types.every((type) => type === "earthquake")
          );
     };

     return (
          <ReportSection
               index={props.index}
               title="Disaster history"
               lede="What has actually been recorded around this point."
               icon={<History size={15} />}
               confidence={props.disasters.confidence}
          >
               <div class="flex flex-col gap-4 items-start">
                    <p class="text-xs text-ink-faint flex items-center gap-1.5 shrink-0 ">
                         <MapPin class="size-3 text-clay-700 shrink-0" />
                         Searched within{" "}
                         {formatDistance(props.disasters.radiusMeters)} of your
                         coordinate, last {props.disasters.searchedYears} years
                    </p>

                    <Show when={props.disasters.earthquakeRadiusMeters}>
                         {(quakeRadius) => (
                              <p class="text-xs text-ink-faint flex items-center gap-1.5 shrink-0">
                                   <Activity class="size-3 text-clay-700 shrink-0" />
                                   Earthquakes to{" "}
                                   {formatDistance(quakeRadius())}, where the
                                   shaking reached here
                              </p>
                         )}
                    </Show>

                    <Show when={props.disasters.tsunamiYears}>
                         {(tsunamiYears) => (
                              <p class="text-xs text-ink-faint flex items-center gap-1.5 shrink-0">
                                   <Waves class="size-3 text-clay-700 shrink-0" />
                                   Last {props.disasters.searchedYears} years,
                                   tsunamis back {tsunamiYears()}
                              </p>
                         )}
                    </Show>
               </div>

               {/* <Show when={props.disasters.note}>
                    {(note) => (
                         <p class="mt-2 rounded-lg border border-khaki-200 bg-khaki-50 px-3 py-2 text-xs leading-relaxed text-khaki-700">
                              {note()}
                         </p>
                    )}
               </Show>

               <Show when={onlyQuakes() && !props.disasters.note}>
                    <p class="mt-2 rounded-lg border border-khaki-200 bg-khaki-50 px-3 py-2 text-xs leading-relaxed text-khaki-700">
                         Earthquakes only, and a seismic catalogue records
                         tremors rather than damage. Indonesia's flood,
                         landslide and windstorm history, with the death and
                         displacement counts, is BNPB's DIBI; import it to
                         cover the hazards that actually affect a plot of land.
                    </p>
               </Show> */}

               <Show
                    when={props.disasters.events.length}
                    fallback={
                         <div class="mt-4 border-t border-line pt-4 text-sm text-ink-soft">
                              <p class="text-ink">
                                   Nothing found in the catalogues searched.
                              </p>

                              <Show when={!props.disasters.note}>
                                   <p class="mt-1 text-xs text-ink-faint">
                                        That means nothing was found in the
                                        sources we check, not that nothing ever
                                        happened here.
                                   </p>
                              </Show>
                         </div>
                    }
               >
                    <ul class="mt-3 divide-y divide-line/50">
                         <For each={events()}>
                              {(event) => (
                                   <li class="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 first:pt-2">
                                        <span class="min-w-0 flex-1 text-sm text-ink">
                                             {event.title}
                                             <Show when={event.url}>
                                                  {(url) => (
                                                       <a
                                                            href={url()}
                                                            target="_blank"
                                                            rel="noreferrer noopener"
                                                            class="ml-1.5 inline-flex translate-y-0.5 text-ink-faint transition-colors hover:text-ink"
                                                            aria-label={`Open source record for ${event.title}`}
                                                       >
                                                            <ExternalLink
                                                                 size={12}
                                                            />
                                                       </a>
                                                  )}
                                             </Show>
                                             <span class="mt-0.5 block text-xs text-ink-faint">
                                                  {titleCase(event.type)}
                                                  <Show
                                                       when={
                                                            event.waterHeightM !==
                                                            null
                                                       }
                                                  >
                                                       <span title="Highest water level recorded within the search radius, from NOAA/NCEI tsunami runup observations">
                                                            {" · water to "}
                                                            {event.waterHeightM!.toFixed(
                                                                 1
                                                            )}
                                                            {" m"}
                                                       </span>
                                                  </Show>

                                                  <Show
                                                       when={formatIntensity(
                                                            event.intensityMmi
                                                       )}
                                                  >
                                                       {(intensity) => (
                                                            <span
                                                                 title={
                                                                      event.intensityBasis ===
                                                                      "reported"
                                                                           ? "Modified Mercalli intensity. The event's highest from felt reports, not necessarily what was felt here"
                                                                           : "Modified Mercalli intensity. The event's highest as modelled by ShakeMap, not necessarily what was felt here"
                                                                 }
                                                            >
                                                                 {" · shaking "}
                                                                 {intensity()}
                                                            </span>
                                                       )}
                                                  </Show>
                                                  <Show
                                                       when={formatMagnitude(
                                                            event.magnitude,
                                                            event.magnitudeScale
                                                       )}
                                                  >
                                                       {(magnitude) => (
                                                            <span
                                                                 title={
                                                                      event.magnitudeScaleSource
                                                                           ? `Scale as reported: ${event.magnitudeScaleSource}`
                                                                           : undefined
                                                                 }
                                                            >
                                                                 {" · "}
                                                                 {magnitude()}
                                                            </span>
                                                       )}
                                                  </Show>
                                                  <Show
                                                       when={
                                                            event.depthKm !==
                                                            null
                                                       }
                                                  >
                                                       {" · "}
                                                       {Math.round(
                                                            event.depthKm!
                                                       )}{" "}
                                                       km deep
                                                  </Show>

                                                  <Show
                                                       when={meaningfulAlert(
                                                            event.severity
                                                       )}
                                                  >
                                                       {(alert) => (
                                                            <span
                                                                 class="font-medium text-clay-700"
                                                                 title="Estimated impact level from the provider. USGS PAGER for earthquakes"
                                                            >
                                                                 {" · "}
                                                                 {titleCase(
                                                                      alert()
                                                                 )}{" "}
                                                                 alert
                                                            </span>
                                                       )}
                                                  </Show>
                                                  {" · "}
                                                  {event.source}

                                                  <Show
                                                       when={formatImpact(
                                                            event.impact
                                                       )}
                                                  >
                                                       {(impact) => (
                                                            <span class="text-xs font-medium text-clay-700">
                                                                 {" · "}
                                                                 {impact()}
                                                            </span>
                                                       )}
                                                  </Show>
                                             </span>
                                        </span>

                                        <span class="tilik-figure shrink-0 text-right text-sm text-ink-soft">
                                             <Switch
                                                  fallback={
                                                       <>
                                                            {formatDistance(
                                                                 event.distanceMeters
                                                            )}
                                                       </>
                                                  }
                                             >
                                                  <Match
                                                       when={
                                                            event.distanceBasis ===
                                                            "measured"
                                                       }
                                                  >
                                                       {formatDistance(
                                                            event.distanceMeters
                                                       )}
                                                  </Match>
                                                  <Match
                                                       when={
                                                            event.distanceBasis ===
                                                                 "area_edge" &&
                                                            event.distanceMeters ===
                                                                 0
                                                       }
                                                  >
                                                       <span
                                                            class="font-sans"
                                                            title="Recorded for the same district your coordinate falls in. The archive stores no position within a district, so there is no distance to give."
                                                       >
                                                            Same district
                                                       </span>
                                                  </Match>
                                                  <Match
                                                       when={
                                                            event.distanceBasis ===
                                                            "area_edge"
                                                       }
                                                  >
                                                       <span
                                                            class="font-sans"
                                                            title="The nearest this event could have been: it is recorded for the area named, whose closest edge is this far away."
                                                       >
                                                            <span aria-hidden="true">
                                                                 ≥
                                                            </span>
                                                            <span class="sr-only">
                                                                 at least
                                                            </span>{" "}
                                                            {formatDistance(
                                                                 event.distanceMeters
                                                            )}
                                                            <span class="ml-1 font-sans text-ink-faint">
                                                                 away
                                                            </span>
                                                       </span>
                                                  </Match>
                                                  <Match
                                                       when={
                                                            event.distanceBasis ===
                                                            "area_centre"
                                                       }
                                                  >
                                                       <span
                                                            class="mr-0.5 text-ink-faint"
                                                            title="Measured to the area's centre, because this area has no boundary in the source. The event may be nearer or further"
                                                       >
                                                            ~
                                                       </span>
                                                       {formatDistance(
                                                            event.distanceMeters
                                                       )}
                                                       <span class="ml-1 font-sans text-ink-faint">
                                                            to area centre
                                                       </span>
                                                  </Match>
                                             </Switch>
                                             <span class="mt-0.5 block text-ink-faint text-xs">
                                                  {formatDate(event.occurredAt)}
                                                  <Show
                                                       when={relativeYears(
                                                            event.occurredAt
                                                       )}
                                                  >
                                                       {(rel) => (
                                                            <span class="ml-1 hidden sm:inline">
                                                                 ({rel()})
                                                            </span>
                                                       )}
                                                  </Show>
                                             </span>
                                        </span>
                                   </li>
                              )}
                         </For>
                    </ul>

                    <Show when={props.disasters.events.length > INITIAL_EVENTS}>
                         <button
                              type="button"
                              onClick={() => setShowAll(!showAll())}
                              class="mt-3 text-xs text-ink-faint underline decoration-line-strong decoration-1 underline-offset-4 transition-colors hover:text-ink hover:decoration-olive-500"
                         >
                              {showAll()
                                   ? `Show only the first ${INITIAL_EVENTS}`
                                   : `Show all ${props.disasters.events.length} events`}
                         </button>
                    </Show>

                    <Show when={hasApproximate()}>
                         <Disclosure summary="What these distances mean">
                              <p class="text-xs leading-relaxed text-ink-soft">
                                   Records reported at the district level do not
                                   include a specific location within the
                                   district. Therefore, their coordinates
                                   represent the nearest available reference
                                   point, not the actual location of the event.
                              </p>
                         </Disclosure>
                    </Show>
               </Show>
          </ReportSection>
     );
}
