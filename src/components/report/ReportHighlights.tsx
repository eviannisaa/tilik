import { For, Show } from "solid-js";
import { cn } from "../../lib/cn";
import { formatDistance, formatElevation, titleCase } from "../../lib/format";
import type { LocationReport, RiskLevel } from "../../lib/types";

/**
 * The four figures worth reading before anything else.
 *
 * Stat tiles rather than a chart: each is a single value with no comparison to
 * plot. They open {@link ReportPanel}, full width below the map, so the headline
 * numbers are read before the evidence that produced them. Values are set in the
 * sans with proportional figures — tabular digits give every numeral a `0`'s
 * width, which reads loose at display size and is only wanted in a column.
 *
 * Each tile carrying a status wears it as a fill, the way the verdict block
 * does, so the row can be read at a glance before any of it is read closely.
 */

/**
 * The status fill. These are the `verdict-*` tints, not the deeper ones the
 * verdict block itself uses: those are mid-tones that hold neither ink nor paper
 * at small sizes — ink measures 3.59:1 on the low fill and 2.16:1 on the higher
 * one. The `verdict-*` steps were tuned so `ink` and `ink-soft` both clear
 * 4.5:1 on every level, which is what a tile full of 0.65rem labels needs.
 *
 * The two tiles that are facts rather than judgements — elevation, distance to a
 * clinic — get `paper` instead. Tinting them would claim a status they don't
 * have, and leaving them on the panel's own surface made the row look half
 * finished.
 */
const FILL: Record<RiskLevel, string> = {
     low: "bg-verdict-low",
     medium: "bg-verdict-moderate",
     high: "bg-verdict-higher",
     unknown: "bg-verdict-unknown",
};

const DOT: Record<RiskLevel, string> = {
     low: "bg-olive-700",
     medium: "bg-khaki-500",
     high: "bg-clay-600",
     unknown: "bg-line-strong",
};

interface Tile {
     label: string;
     value: string;
     note: string;
     level?: RiskLevel;
}

function buildTiles(report: LocationReport): Tile[] {
     const strongest = report.hazards.readings
          .filter(
               (reading) => reading.status === "ok" && reading.index !== null
          )
          .sort((a, b) => (b.index ?? 0) - (a.index ?? 0))[0];

     const health = report.places.categories.find(
          (category) => category.key === "health"
     );

     return [
          {
               label: "Elevation",
               value: formatElevation(report.terrain.elevation),
               note: titleCase(report.terrain.terrain),
          },
          {
               label: "Flood risk",
               value:
                    report.flood.risk === "unknown"
                         ? "Unknown"
                         : titleCase(report.flood.risk),
               note:
                    report.flood.hazardIndex !== null
                         ? `InaRISK ${report.flood.hazardIndex.toFixed(2)}`
                         : report.flood.basis === "heuristic"
                           ? "Estimated"
                           : "No source",
               level: report.flood.risk,
          },
          {
               label: "Strongest hazard",
               value: strongest ? strongest.index!.toFixed(2) : "—",
               note: strongest ? strongest.label : "None mapped here",
               level: strongest?.level,
          },
          {
               label: "Nearest clinic",
               value: health?.nearest
                    ? formatDistance(health.nearest.distanceMeters)
                    : "—",
               note: health?.nearest
                    ? health.nearest.name
                    : "None mapped nearby",
          },
     ];
}

export default function ReportHighlights(props: { report: LocationReport }) {
     return (
          <dl class="grid grid-cols-2 lg:grid-cols-4">
               <For each={buildTiles(props.report)}>
                    {(tile, index) => (
                         <div
                              class={cn(
                                   "flex flex-col px-4 py-4 sm:px-8",
                                   index() % 2 === 1 && "border-l border-line",
                                   index() >= 2 &&
                                        "border-t border-line lg:border-t-0",
                                   index() === 2 &&
                                        "lg:border-l lg:border-line",
                                   tile.level ? FILL[tile.level] : "bg-paper"
                              )}
                         >
                              <dt class="tilik-label text-ink/80 capitalize font-sans text-xs">
                                   {tile.label}
                              </dt>

                              <dd class="mt-3 flex items-center gap-2">
                                   <Show when={tile.level}>
                                        {(level) => (
                                             <>
                                                  <span
                                                       class={cn(
                                                            "mb-1 size-2 shrink-0 rounded-full",
                                                            DOT[level()]
                                                       )}
                                                       aria-hidden="true"
                                                  />

                                                  <span class="sr-only">
                                                       {level()} concern:{" "}
                                                  </span>
                                             </>
                                        )}
                                   </Show>
                                   <span class="text-2xl font-semibold leading-none text-ink">
                                        {tile.value}
                                   </span>
                              </dd>

                              <p
                                   class="mt-auto line-clamp-2 pt-2 text-xs leading-snug text-ink font-sans"
                                   title={tile.note}
                              >
                                   {tile.note}
                              </p>
                         </div>
                    )}
               </For>
          </dl>
     );
}
