import { createSignal, For, Show } from "solid-js";
import ShieldAlert from "lucide-solid/icons/shield-alert";
import type { HazardIndex, HazardReading, RiskLevel } from "../../lib/types";
import { cn } from "../../lib/cn";
import { titleCase } from "../../lib/format";
import ReportSection from "./ReportSection";
import Disclosure from "./Disclosure";

/**
 * BNPB's eleven hazard layers, each a 0–1 magnitude.
 *
 * A real table, not a styled list: eleven rows of one measure is tabular data,
 * it gives the meters a table view for free, and one of the status fills sits
 * below 3:1 against the surface — for which a table view is the sanctioned
 * relief.
 *
 * The status steps were chosen with the palette validator rather than by eye.
 * `#c96f4a` against `#828062` separates by only ΔE 3.1 for a protanope and 11.9
 * for normal vision, so high and medium fills were near-indistinguishable; the
 * steps below clear 15.4 and 17.5 respectively.
 */

const LEVEL: Record<RiskLevel, { fill: string; track: string; text: string }> =
     {
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
          high: {
               fill: "bg-clay-300",
               track: "bg-clay-50",
               text: "text-clay-700",
          },
          unknown: {
               fill: "bg-line-strong",
               track: "bg-paper-sunk",
               text: "text-ink-faint",
          },
     };

/** BNPB bands the index in equal thirds, so the boundaries are worth showing. */
const BAND_MARKS = [1 / 3, 2 / 3];

/**
 * Layers that are reported but deliberately do not move the concern level, and
 * why. Kept in step with `SECONDARY_HAZARDS` in `api/services/assessment.py`.
 *
 * Without saying this, a reader who sees "Drought · 0.85 · High · here" above a
 * "Low concern" verdict concludes the app is broken — when leaving those two out
 * is the considered choice. Silence about a rule looks like a bug in it.
 */
function statusLabel(reading: HazardReading): string {
     switch (reading.status) {
          case "out_of_coverage":
               return "Outside coverage";
          case "unavailable":
               return "No answer";
          case "no_data":
               return "No hazard mapped";
          default: {
               const level = titleCase(reading.level);
               return reading.withinMeters !== null && reading.withinMeters >= 1
                    ? `${level} · ${Math.round(reading.withinMeters)} m away`
                    : `${level} · here`;
          }
     }
}

export default function HazardSection(props: {
     hazards: HazardIndex;
     index: number;
}) {
     const [showAll, setShowAll] = createSignal(false);

     const answered = () =>
          props.hazards.readings.filter((reading) => reading.status === "ok");
     const silent = () =>
          props.hazards.readings.filter((reading) => reading.status !== "ok");

     /** Layers with nothing to report are counted, not listed, until asked for. */
     const rows = () =>
          showAll() || answered().length === 0
               ? props.hazards.readings
               : answered();

     const ingestedResolution = () => {
          const found = answered();
          if (
               !found.length ||
               found.some((reading) => reading.source !== "postgis")
          )
               return null;
          return found[0]!.resolutionMeters;
     };

     return (
          <ReportSection
               index={props.index}
               title="Hazard index"
               emphasis
               lede="BNPB's national models, scored 0 to 1 at or near this point."
               icon={<ShieldAlert size={15} />}
               confidence={props.hazards.confidence}
          >
               <Show
                    when={props.hazards.readings.length}
                    fallback={
                         <p class="text-sm leading-relaxed text-ink-soft">
                              {props.hazards.note ??
                                   "No hazard index available for this point."}
                         </p>
                    }
               >
                    <p class="text-xs text-ink-soft">
                         <span class="font-medium text-ink">
                              <span class="font-semibold">
                                   {answered().length}
                              </span>{" "}
                              of{" "}
                              <span class="font-semibold">
                                   {props.hazards.readings.length}
                              </span>
                         </span>{" "}
                         layers map a hazard here · {props.hazards.source}
                         <Show when={ingestedResolution()}>
                              {(resolution) => (
                                   <> · read locally at {resolution()} m</>
                              )}
                         </Show>
                    </p>

                    <table class="mt-4 w-full border-collapse table-fixed text-sm">
                         <caption class="sr-only">
                              BNPB InaRISK hazard index by hazard type, scored 0
                              to 1
                         </caption>
                         <thead>
                              <tr class="text-left">
                                   <th
                                        scope="col"
                                        class="pb-2 text-ink capitalize font-semibold"
                                   >
                                        Hazard
                                   </th>
                                   <th
                                        scope="col"
                                        aria-hidden="true"
                                        class="pb-2"
                                   ></th>
                                   <th
                                        scope="col"
                                        class="w-14 pb-2 text-ink capitalize font-semibold"
                                   >
                                        Index
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
                              <For each={rows()}>
                                   {(reading) => {
                                        const tone = LEVEL[reading.level];
                                        const filled = reading.index !== null;

                                        return (
                                             <tr
                                                  class={cn(
                                                       "border-t border-line/50 align-middle",
                                                       !filled &&
                                                            "text-ink-faint"
                                                  )}
                                             >
                                                  <th
                                                       scope="row"
                                                       class="py-2 pr-3 text-left font-medium text-ink text-xs"
                                                  >
                                                       {reading.label}
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
                                                                 reading.description
                                                            }
                                                       >
                                                            <For
                                                                 each={
                                                                      BAND_MARKS
                                                                 }
                                                            >
                                                                 {(mark) => (
                                                                      <span
                                                                           aria-hidden="true"
                                                                           class="absolute inset-y-0 w-px bg-paper-raised/70"
                                                                           style={{
                                                                                left: `${mark * 100}%`,
                                                                           }}
                                                                      />
                                                                 )}
                                                            </For>
                                                            <Show when={filled}>
                                                                 <span
                                                                      class={cn(
                                                                           "relative h-full rounded-r-[4px]",
                                                                           tone.fill
                                                                      )}
                                                                      style={{
                                                                           width: `${Math.max(2, (reading.index ?? 0) * 100)}%`,
                                                                      }}
                                                                 />
                                                            </Show>
                                                       </span>
                                                  </td>

                                                  <td
                                                       class={cn(
                                                            "tilik-figure w-14 py-2 pr-6 text-right font-semibold text-xs whitespace-nowrap",
                                                            tone.text
                                                       )}
                                                  >
                                                       {filled
                                                            ? reading.index!.toFixed(
                                                                   2
                                                              )
                                                            : "—"}
                                                  </td>

                                                  <td class="py-2 text-right text-xs whitespace-nowrap text-ink-soft">
                                                       {statusLabel(reading)}
                                                  </td>
                                             </tr>
                                        );
                                   }}
                              </For>
                         </tbody>
                    </table>

                    <Show when={silent().length > 0 && answered().length > 0}>
                         <button
                              type="button"
                              onClick={() => setShowAll(!showAll())}
                              class="mt-3 text-xs text-ink-faint underline decoration-line-strong decoration-1 underline-offset-4 transition-colors hover:text-ink hover:decoration-olive-500"
                         >
                              {showAll()
                                   ? "Hide layers with no reading"
                                   : `Show ${silent().length} more layers with no reading`}
                         </button>
                    </Show>

                    <Disclosure summary="What these readings mean">
                         <dl class="space-y-2 text-xs text-ink-faint">
                              <div class="flex gap-3">
                                   <dt class="w-36 shrink-0 text-ink-soft">
                                        0.00–1.00
                                   </dt>
                                   <dd>
                                        BNPB's hazard index. Hairlines on each
                                        bar mark their class boundaries at 0.33
                                        and 0.67. A reading of 0.00 means
                                        modelled, with no hazard.
                                   </dd>
                              </div>
                              <div class="flex gap-3">
                                   <dt class="w-36 shrink-0 text-ink-soft">
                                        No hazard mapped
                                   </dt>
                                   <dd>
                                        The model covers Indonesia but maps
                                        nothing of this kind nearby, which is
                                        normal for tsunami well inland. Not a
                                        guarantee of safety.
                                   </dd>
                              </div>
                              <Show
                                   when={props.hazards.readings.some(
                                        (r) => r.status === "unavailable"
                                   )}
                              >
                                   <div class="flex gap-3">
                                        <dt class="w-36 shrink-0 text-ink-soft">
                                             No answer
                                        </dt>
                                        <dd>
                                             BNPB's server didn't respond for
                                             this layer. Re-run to retry.
                                        </dd>
                                   </div>
                              </Show>
                              <Show
                                   when={props.hazards.readings.some(
                                        (r) => r.status === "out_of_coverage"
                                   )}
                              >
                                   <div class="flex gap-3">
                                        <dt class="w-36 shrink-0 text-ink-soft">
                                             Outside coverage
                                        </dt>
                                        <dd>
                                             Beyond InaRISK's modelled area.
                                             BNPB maps Indonesia only. No index
                                             applies, which is not the same as
                                             no hazard.
                                        </dd>
                                   </div>
                              </Show>
                         </dl>
                    </Disclosure>

                    <Show when={props.hazards.note}>
                         <p class="mt-3 text-xs leading-relaxed text-ink-faint">
                              {props.hazards.note}
                         </p>
                    </Show>
               </Show>
          </ReportSection>
     );
}
