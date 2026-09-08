import { For, Show } from "solid-js";
import Wind from "lucide-solid/icons/wind";
import ExternalLink from "lucide-solid/icons/external-link";
import type { AirQuality, PollutantReading, RiskLevel } from "../../lib/types";
import { cn } from "../../lib/cn";
import { formatDate, formatDistance, relativeHours } from "../../lib/format";
import ReportSection from "./ReportSection";
import Badge from "../ui/Badge";
import Disclosure from "./Disclosure";

/**
 * The one instrument reading in the report.
 *
 * Every other section is a model, a catalogue or press coverage. This is a
 * machine standing in the open air, which makes it the strongest number on the
 * page and the easiest to over-read, because two things about it are unlike
 * everything around it: it was measured at a station rather than at this point,
 * and it describes an hour rather than a place. So the station's distance is
 * given the same weight as the figure itself, and the section says out loud
 * that one reading is not a pattern.
 *
 * The same tones as `FloodSection` and `HazardSection`, not a new scale. Two
 * things carry the level: the badge and the bar. The EPA band name is printed
 * as published, so the six-band standard survives a three-tone palette.
 */
const TONE: Record<RiskLevel, "olive" | "khaki" | "clay" | "neutral"> = {
     low: "olive",
     medium: "khaki",
     high: "clay",
     unknown: "neutral",
};

const BAR: Record<RiskLevel, { fill: string; track: string; text: string }> = {
     low: {
          fill: "bg-olive-200",
          track: "bg-olive-50",
          text: "text-olive-500/70",
     },
     medium: {
          fill: "bg-khaki-500",
          track: "bg-khaki-50",
          text: "text-khaki-700/90",
     },
     high: { fill: "bg-clay-300", track: "bg-clay-50", text: "text-clay-700" },
     unknown: {
          fill: "bg-line-strong",
          track: "bg-paper-sunk",
          text: "text-ink-faint",
     },
};

/**
 * Where the bars stop.
 *
 * 300 is the top of "very unhealthy" and the practical ceiling of the scale;
 * above it a bar reading "full" is the correct answer. Scaling to the true
 * maximum instead would squash every ordinary Indonesian reading into the first
 * fifth of the track.
 */
const BAR_MAX = 300;

/**
 * The EPA class boundaries, as fractions of the track.
 *
 * `HazardSection` marks BNPB's 0.33 and 0.67 on every bar for the same reason:
 * a bar without them shows a magnitude, and with them shows which class the
 * magnitude falls in. Derived from the same list the bands themselves come
 * from, so the two cannot drift apart. 300 sits at the very edge and is left
 * off, as a hairline there is indistinguishable from the track's end.
 */
const BAND_MARKS = [50, 100, 150, 200].map((boundary) => boundary / BAR_MAX);

/**
 * The Status column, the counterpart of `statusLabel` in `HazardSection`.
 *
 * The dominant marker belongs here rather than beside the pollutant's name.
 * Inline it ran straight into the label ("PM2.5sets the index") and put two
 * different kinds of fact in one cell. `HazardSection` keeps the same shape:
 * the class, then a middot, then what qualifies it.
 */
function statusLabel(pollutant: PollutantReading, measured: number): string {
     // "sets the index" claims this pollutant beat the others. With one row
     // there were no others, and the claim reads as a comparison that never
     // happened. The headline figure is simply this pollutant's own number.
     return pollutant.dominant && measured > 1
          ? `${pollutant.bandLabel} · sets the index`
          : pollutant.bandLabel;
}

/**
 * Past this, the reading is about somewhere else and the section says so.
 *
 * Kept in step with `WAQI_MAX_STATION_METERS` in the API, which is what lowered
 * the confidence badge to "Estimated". This is the flag that explains the badge.
 *
 * Nothing is withheld past it. A distance cutoff was tried and removed: with 25
 * BMKG stations covering Indonesia, suppressing far readings left most of the
 * country with a blank section, and a distant reading shown with its distance
 * is worth more than nothing. So this flag has to be true at 26 km and at the
 * 4,440 km the `demo` token answers, which is why it states what the figure
 * *is* rather than how far away it came from. The distance itself is in the
 * description above and in the provenance line below.
 */
const FAR_STATION_METERS = 25_000;

/**
 * Four ways this section comes back empty, and four different things they mean.
 *
 * The distinction is the point. "We could not look" and "we looked and found
 * nothing" must never render alike, and neither may be mistaken for clean air.
 * The backend's own `note` wins where it has one, because it can name the
 * particular failure.
 */
const EMPTY_COPY: Record<string, { title: string; detail: string }> = {
     not_configured: {
          title: "Air quality isn't set up for this deployment.",
          detail: "This check needs a WAQI token, and none is configured. Every other section of this report is unaffected.",
     },
     disabled: {
          title: "Air quality is turned off for this deployment.",
          detail: "Someone chose to leave this section out. It says nothing about the air here.",
     },
     no_station: {
          title: "No station is reporting for this point.",
          detail: "WAQI has no monitor it can answer with here, or the nearest one is offline. That is a gap in coverage, not clean air. Distance alone never produces this state: a far station's reading is shown, with its distance.",
     },
     unavailable: {
          title: "The air-quality service didn't answer.",
          detail: "Every other section of this report is unaffected. Re-run the check to try again.",
     },
};

export default function AirQualitySection(props: {
     airQuality: AirQuality;
     index: number;
}) {
     const air = () => props.airQuality;
     const reading = () => (air().status === "ok" ? air() : null);

     /** True once the figure has stopped describing this address. */
     const far = () => {
          const distance = air().stationDistanceMeters;
          return distance !== null && distance > FAR_STATION_METERS;
     };

     /**
      * Hours, not days. The heading promises what the air is doing right now,
      * and "today" covers a reading taken at 3am.
      */
     const measured = () =>
          relativeHours(air().measuredAt) ?? formatDate(air().measuredAt);

     return (
          <ReportSection
               index={props.index}
               title="Air quality"
               lede="What the nearest monitoring station is measuring right now."
               icon={<Wind size={15} />}
               confidence={air().confidence}
          >
               <Show
                    when={reading()}
                    fallback={
                         <div class="border-t border-line pt-4 text-sm text-ink-soft">
                              <p class="text-ink">
                                   {EMPTY_COPY[air().status]?.title ??
                                        "No air-quality reading to show."}
                              </p>
                              <p class="mt-1 text-xs leading-relaxed text-ink-faint">
                                   {air().note ??
                                        EMPTY_COPY[air().status]?.detail}
                              </p>
                         </div>
                    }
               >
                    {(current) => (
                         <>
                              <div class="flex flex-wrap items-baseline gap-x-3 gap-y-2">
                                   <span
                                        class={cn(
                                             "tilik-figure font-display text-4xl leading-none font-medium",
                                             BAR[current().level].text
                                        )}
                                   >
                                        {current().aqi}
                                   </span>
                                   <span class="tilik-label text-ink-faint">
                                        AQI
                                   </span>
                                   <Show when={current().bandLabel}>
                                        {(band) => (
                                             <Badge
                                                  tone={TONE[current().level]}
                                             >
                                                  {band()}
                                             </Badge>
                                        )}
                                   </Show>
                              </div>

                              <p class="mt-3 max-w-2xl text-sm leading-relaxed text-ink-soft">
                                   {current().description}
                              </p>

                              <Show when={current().pollutants.length}>
                                   {/*
                                     * The counterpart of "N of M layers map a
                                     * hazard here" in `HazardSection`, and it
                                     * carries more weight here: BMKG's stations
                                     * mostly report PM2.5 alone, so without
                                     * this line a single row reads as the whole
                                     * picture.
                                     */}
                                   <p class="mt-4 text-xs text-ink-soft">
                                        <span class="font-medium text-ink">
                                             <span class="font-semibold">
                                                  {
                                                       current().pollutants
                                                            .length
                                                  }
                                             </span>{" "}
                                             of{" "}
                                             <span class="font-semibold">
                                                  {
                                                       current()
                                                            .pollutantsPossible
                                                  }
                                             </span>
                                        </span>{" "}
                                        pollutants measured at this station
                                   </p>

                                   <table class="mt-4 w-full border-collapse table-fixed text-sm">
                                        <caption class="sr-only">
                                             Air-quality sub-index by pollutant,
                                             on the US EPA scale
                                        </caption>
                                        <thead>
                                             <tr class="text-left">
                                                  <th
                                                       scope="col"
                                                       class="pb-2 text-ink capitalize font-semibold"
                                                  >
                                                       Pollutant
                                                  </th>
                                                  <th
                                                       scope="col"
                                                       aria-hidden="true"
                                                       class="pb-2"
                                                  ></th>
                                                  <th
                                                       scope="col"
                                                       class="w-14 pl-2 pb-2 text-ink capitalize font-semibold"
                                                  >
                                                       AQI
                                                  </th>
                                                  <th
                                                       scope="col"
                                                       class="pb-2 text-ink capitalize font-semibold text-right"
                                                  >
                                                       Status
                                                  </th>
                                             </tr>
                                        </thead>
                                        <tbody>
                                             <For each={current().pollutants}>
                                                  {(pollutant) => {
                                                       const tone =
                                                            BAR[
                                                                 pollutant.level
                                                            ];

                                                       return (
                                                            <tr class="border-t border-line/50 align-middle">
                                                                 <th
                                                                      scope="row"
                                                                      class="py-2 pr-3 text-left font-medium text-ink text-xs"
                                                                 >
                                                                      {
                                                                           pollutant.label
                                                                      }
                                                                 </th>

                                                                 <td
                                                                      class="w-[38%] py-2 pr-3"
                                                                      aria-hidden="true"
                                                                 >
                                                                      <span
                                                                           class={cn(
                                                                                "relative flex h-1.5 w-full overflow-hidden rounded-[2px]",
                                                                                tone.track
                                                                           )}
                                                                           title={
                                                                                pollutant.bandLabel
                                                                           }
                                                                      >
                                                                           <For
                                                                                each={
                                                                                     BAND_MARKS
                                                                                }
                                                                           >
                                                                                {(
                                                                                     mark
                                                                                ) => (
                                                                                     <span
                                                                                          aria-hidden="true"
                                                                                          class="absolute inset-y-0 w-px bg-paper-raised/70"
                                                                                          style={{
                                                                                               left: `${mark * 100}%`,
                                                                                          }}
                                                                                     />
                                                                                )}
                                                                           </For>
                                                                           <span
                                                                                class={cn(
                                                                                     "relative h-full rounded-r-[4px]",
                                                                                     tone.fill
                                                                                )}
                                                                                style={{
                                                                                     width: `${Math.min(100, Math.max(2, (pollutant.aqi / BAR_MAX) * 100))}%`,
                                                                                }}
                                                                           />
                                                                      </span>
                                                                 </td>

                                                                 <td
                                                                      class={cn(
                                                                           "tilik-figure w-14 py-2 pr-6 text-right font-semibold text-xs whitespace-nowrap",
                                                                           tone.text
                                                                      )}
                                                                 >
                                                                      {Math.round(
                                                                           pollutant.aqi
                                                                      )}
                                                                 </td>

                                                                 {/*
                                                                  * No `whitespace-nowrap` here, unlike the
                                                                  * hazard table. Its status labels are two
                                                                  * words; "Unhealthy for sensitive groups"
                                                                  * is five, and held on one line it pushes
                                                                  * the table wider than the panel.
                                                                  */}
                                                                 <td class="py-2 text-right text-xs text-ink-soft">
                                                                      {statusLabel(
                                                                           pollutant,
                                                                           current()
                                                                                .pollutants
                                                                                .length
                                                                      )}
                                                                 </td>
                                                            </tr>
                                                       );
                                                  }}
                                             </For>
                                        </tbody>
                                   </table>
                              </Show>

                              <Show when={far()}>
                                   <p class="mt-4 border-l-2 border-khaki-200 pl-3 text-xs leading-relaxed text-ink-soft">
                                        This is the nearest station's reading,
                                        not a measurement of the air at this
                                        point.
                                   </p>
                              </Show>

                              <p class="mt-4 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-faint">
                                   <Show
                                        when={current().stationName}
                                        fallback={<span>Station unnamed</span>}
                                   >
                                        {(name) => (
                                             <Show
                                                  when={current().stationUrl}
                                                  fallback={
                                                       <span class="text-ink-soft">
                                                            {name()}
                                                       </span>
                                                  }
                                             >
                                                  {(url) => (
                                                       <a
                                                            href={url()}
                                                            target="_blank"
                                                            rel="noreferrer noopener"
                                                            class="text-ink-soft underline decoration-line-strong decoration-1 underline-offset-4 transition-colors hover:text-olive-700 hover:decoration-olive-500"
                                                       >
                                                            {name()}
                                                            <ExternalLink
                                                                 size={12}
                                                                 class="ml-1.5 inline-block"
                                                            />
                                                       </a>
                                                  )}
                                             </Show>
                                        )}
                                   </Show>
                                   <Show
                                        when={
                                             current().stationDistanceMeters !==
                                             null
                                        }
                                   >
                                        <span aria-hidden="true">·</span>
                                        <span>
                                             {formatDistance(
                                                  current()
                                                       .stationDistanceMeters
                                             )}{" "}
                                             away
                                        </span>
                                   </Show>
                                   <Show when={current().measuredAt}>
                                        <span aria-hidden="true">·</span>
                                        <time
                                             datetime={
                                                  current().measuredAt ??
                                                  undefined
                                             }
                                        >
                                             read {measured()}
                                        </time>
                                   </Show>
                              </p>

                              <Disclosure summary="What this reading means">
                                   <dl class="space-y-2 text-xs text-ink-faint">
                                        <div class="flex gap-3">
                                             <dt class="w-36 shrink-0 text-ink-soft">
                                                  0 to 500
                                             </dt>
                                             <dd>
                                                  The US EPA air-quality index.
                                                  Its bands are good to 50,
                                                  moderate to 100, unhealthy for
                                                  sensitive groups to 150,
                                                  unhealthy to 200, very
                                                  unhealthy to 300, then
                                                  hazardous. Every pollutant is
                                                  scored on that one scale, and
                                                  where a station measures
                                                  several the worst of them sets
                                                  the figure above.
                                             </dd>
                                        </div>
                                        <div class="flex gap-3">
                                             <dt class="w-36 shrink-0 text-ink-soft">
                                                  What was measured
                                             </dt>
                                             <dd>
                                                  A station measures only what
                                                  its instruments cover, and
                                                  BMKG's mostly report PM2.5
                                                  alone. A pollutant missing
                                                  from the table was not
                                                  measured here, which is not
                                                  the same as measured at zero.
                                                  Ozone and NO2 in particular go
                                                  unrecorded at most Indonesian
                                                  stations.
                                             </dd>
                                        </div>
                                        <div class="flex gap-3">
                                             <dt class="w-36 shrink-0 text-ink-soft">
                                                  One hour
                                             </dt>
                                             <dd>
                                                  This is the latest reading,
                                                  not an average. Air quality
                                                  swings with traffic, wind and
                                                  rain, so a clear afternoon
                                                  says little about the dry
                                                  season. Check it more than
                                                  once, at different times.
                                             </dd>
                                        </div>
                                        <div class="flex gap-3">
                                             <dt class="w-36 shrink-0 text-ink-soft">
                                                  A station, not a plot
                                             </dt>
                                             <dd>
                                                  The figure was measured
                                                  wherever the station stands,
                                                  and its distance is printed
                                                  above. The confidence badge on
                                                  this section follows that
                                                  distance rather than the
                                                  reading.
                                             </dd>
                                        </div>
                                   </dl>
                              </Disclosure>

                              <Show when={current().attributions.length}>
                                   <p class="mt-4 border-t border-line/50 pt-3 text-xs leading-relaxed text-ink-faint">
                                        Measured and published by{" "}
                                        <For each={current().attributions}>
                                             {(credit, position) => (
                                                  <>
                                                       <Show
                                                            when={credit.url}
                                                            fallback={
                                                                 <span>
                                                                      {
                                                                           credit.name
                                                                      }
                                                                 </span>
                                                            }
                                                       >
                                                            {(url) => (
                                                                 <a
                                                                      href={url()}
                                                                      target="_blank"
                                                                      rel="noreferrer noopener"
                                                                      class="underline decoration-line-strong decoration-1 underline-offset-2 transition-colors hover:text-ink"
                                                                 >
                                                                      {
                                                                           credit.name
                                                                      }
                                                                 </a>
                                                            )}
                                                       </Show>
                                                       {/*
                                                         * A middot, not a
                                                         * comma. "BMKG | Badan
                                                         * Meteorologi,
                                                         * Klimatologi dan
                                                         * Geofisika" carries two
                                                         * commas of its own, so
                                                         * comma-separating the
                                                         * names showed a reader
                                                         * four candidates where
                                                         * there were two. The
                                                         * names themselves are
                                                         * printed exactly as the
                                                         * provider gives them:
                                                         * an attribution is not
                                                         * ours to tidy.
                                                         */}
                                                       <Show
                                                            when={
                                                                 position() <
                                                                 current()
                                                                      .attributions
                                                                      .length -
                                                                      1
                                                            }
                                                       >
                                                            <span aria-hidden="true">
                                                                 {" · "}
                                                            </span>
                                                       </Show>
                                                  </>
                                             )}
                                        </For>
                                        .
                                   </p>
                              </Show>
                         </>
                    )}
               </Show>
          </ReportSection>
     );
}
