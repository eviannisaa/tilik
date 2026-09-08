import {
     For,
     Match,
     Show,
     Switch,
     createEffect,
     createSignal,
     onCleanup,
} from "solid-js";
import Clock from "lucide-solid/icons/clock";
import TriangleAlert from "lucide-solid/icons/triangle-alert";
import { cn } from "../../lib/cn";
import { locationStore } from "../../lib/store";
import AirQualitySection from "./AirQualitySection";
import AreaSection from "./AreaSection";
import DisasterSection from "./DisasterSection";
import FloodSection from "./FloodSection";
import HazardSection from "./HazardSection";
import NewsSection from "./NewsSection";
import PlacesSection from "./PlacesSection";
import ReportHighlights from "./ReportHighlights";
import { sectionId } from "./ReportSection";
import ReportSkeleton from "./ReportSkeleton";
import SectionBoundary from "./SectionBoundary";
import TerrainSection from "./TerrainSection";
import { formatDate } from "../../lib/format";
import type {
     AssessmentLevel,
     DataSource,
     LocationInfo,
     ReportMeta,
} from "../../lib/types";
import { Info } from "lucide-solid";

/**
 * What this result is about, and what it is made of.
 *
 * The place is read off the report rather than the picker, so the line describes
 * the check that produced these figures and not whatever happens to be selected
 * now. The composition is counted from `meta.sources`, so it stays true to the
 * report instead of describing an intention, and its words are the confidence
 * ladder's own — a reader meets "measured" and "estimated" again on every
 * section badge below.
 *
 * With no sources at all it keeps the promise instead of the tally: a line
 * reading "0 measured" would be the one wrong thing on screen, and the fixtures
 * and a badly degraded check both arrive that way.
 */
export function resultSummary(
     location: LocationInfo,
     meta: ReportMeta
): string {
     const place =
          location.name ?? location.locality ?? location.city ?? "this point";

     const count = (...qualities: DataSource["quality"][]) =>
          meta.sources.filter((source) => qualities.includes(source.quality))
               .length;

     const clauses = [
          [count("live", "database"), "measured directly"],
          [count("estimate"), "estimated from models"],
          [count("unavailable"), "that returned nothing"],
     ]
          .filter(([n]) => (n as number) > 0)
          .map(([n, label]) => `${n} ${label}`);

     const total = meta.sources.length;
     const sources = `${total} data source${total === 1 ? "" : "s"}`;
     const closing =
          "Every section below names its own source and how confident it is.";

     if (clauses.length === 0) {
          return `This information about ${place} is built from public data sources. ${closing}`;
     }

     return `This information about ${place} is built from ${sources}. ${joinClauses(
          clauses
     )}. ${closing}`;
}

/** "a, b and c" rather than "a and b and c", as the gaps notice reads them. */
function joinClauses(clauses: string[]): string {
     if (clauses.length === 1) return clauses[0]!;
     return `${clauses.slice(0, -1).join(", ")} and ${clauses.at(-1)}`;
}

/**
 * The index in the header, in reading order.
 *
 * These titles are also passed to the sections themselves, which is a
 * duplication a test guards rather than a comment: `report-index.test.tsx`
 * compares this list against the headings the sections actually render, so a
 * renamed section fails there instead of drifting silently.
 */
const SECTIONS = [
     { index: 1, title: "Terrain" },
     { index: 2, title: "Flood" },
     { index: 3, title: "Hazard index" },
     { index: 4, title: "Disaster history" },
     { index: 5, title: "Local news" },
     { index: 6, title: "Air quality" },
     { index: 7, title: "What's nearby" },
     { index: 8, title: "Area" },
] as const;

/**
 * The band behind the header and footer, tinted by the verdict it belongs to —
 * the same idea as the verdict block's own fill, at a depth that can carry paper
 * text. `unknown` has no status to tint by, so it stays the plain dark.
 */
const BAND: Record<AssessmentLevel, string> = {
     low: "bg-band-low",
     moderate: "bg-band-moderate",
     higher: "bg-band-higher",
     unknown: "bg-ink",
};

/**
 * How a source reads in the footer: its provider, and what kind of answer it is.
 *
 * `live` is the unmarked case — fetched now, from the provider itself. The
 * others are weaker in ways a reader should not have to infer: `database` came
 * from a local import rather than the provider, and `estimate` was derived
 * rather than measured. The old footer printed all three identically.
 */
function labelFor(source: DataSource): string {
     if (source.quality === "database")
          return `${source.provider} (local copy)`;
     if (source.quality === "estimate") return `${source.provider} (estimated)`;
     return source.provider;
}

/**
 * Sources grouped by the field they answered, in the order they arrived.
 *
 * Ungrouped, `disasters` filled three of ten slots — USGS, NOAA NCEI and the
 * local archive each repeating the same field name — while the field a reader
 * was looking for sat somewhere in the wrap.
 */
function groupByField(
     sources: DataSource[]
): { field: string; answered: DataSource[]; failed: DataSource[] }[] {
     const order: string[] = [];
     const byField = new Map<string, DataSource[]>();

     for (const source of sources) {
          if (!byField.has(source.field)) {
               byField.set(source.field, []);
               order.push(source.field);
          }
          byField.get(source.field)!.push(source);
     }

     return order.map((field) => {
          const all = byField.get(field)!;
          return {
               field,
               answered: all.filter(
                    (source) => source.quality !== "unavailable"
               ),
               failed: all.filter((source) => source.quality === "unavailable"),
          };
     });
}

const BANDTEXT: Record<AssessmentLevel, string> = {
     low: "text-band-low",
     moderate: "text-band-moderate",
     higher: "text-band-higher",
     unknown: "text-ink",
};

/**
 * The evidence behind the verdict.
 *
 * Opens with the four highlight figures — they read as the headline the numbered
 * sections then account for. The verdict, the gaps notice and the `#report`
 * anchor all live in {@link ReportSummary}; this renders nothing at all until
 * there is something to show, so a failed check reports itself once rather than
 * in two places.
 *
 * No `Panel`: it runs inside a dialog, and the dialog already is the card.
 * Wrapping it in a second one is the nesting the app's one surface treatment
 * exists to avoid, and going full bleed is also what lets the header stick —
 * `overflow-hidden` on a wrapper leaves `sticky` no scroll container to work
 * against.
 */
export default function ReportPanel() {
     const status = locationStore.reportStatus;
     const report = locationStore.report;

     /** Footer provenance: grouped by field, with failures kept visible. */
     const sourcesByField = () => groupByField(report()?.meta.sources ?? []);
     const answeredSources = () =>
          (report()?.meta.sources ?? []).filter(
               (source) => source.quality !== "unavailable"
          );

     /** Which section the reader is in, for the index. */
     const [current, setCurrent] = createSignal(1);

     /** The scrolling element, so the observer below measures against it. */
     let scroller: HTMLDivElement | undefined;

     createEffect(() => {
          if (!report() || typeof IntersectionObserver === "undefined") return;

          const observer = new IntersectionObserver(
               (entries) => {
                    for (const entry of entries) {
                         if (!entry.isIntersecting) continue;
                         const index = Number(entry.target.id.split("-").pop());
                         if (index) setCurrent(index);
                    }
               },
               { root: scroller, rootMargin: "-25% 0px -65% 0px" }
          );

          for (const section of SECTIONS) {
               const node = document.getElementById(sectionId(section.index));
               if (node) observer.observe(node);
          }

          onCleanup(() => observer.disconnect());
     });

     function jumpTo(index: number) {
          document
               .getElementById(sectionId(index))
               ?.scrollIntoView({ behavior: "smooth", block: "start" });
     }

     return (
          <Switch>
               <Match when={status() === "loading" && !report()}>
                    <ReportSkeleton />
               </Match>

               <Match when={report()}>
                    {(data) => (
                         <article
                              class={cn(
                                   "flex min-h-0 flex-1 flex-col transition-opacity duration-200",
                                   status() === "loading" && "opacity-60"
                              )}
                              aria-busy={status() === "loading"}
                         >
                              <header
                                   class={cn(
                                        "shrink-0 overflow-hidden px-4 pt-1 pb-4 sm:px-8 bg-olive-200"
                                   )}
                              >
                                   <div class="relative flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pr-20 sm:pr-24">
                                        <div class="flex items-center gap-3"></div>
                                   </div>

                                   <nav
                                        aria-label="Report sections"
                                        class="relative -mx-4 mt-4 sm:-mx-8"
                                   >
                                        <ul class="tilik-rail flex gap-1.5 overflow-x-auto px-4 pb-1 sm:px-8">
                                             <For each={SECTIONS}>
                                                  {(section) => (
                                                       <li class="shrink-0">
                                                            <button
                                                                 type="button"
                                                                 onClick={() =>
                                                                      jumpTo(
                                                                           section.index
                                                                      )
                                                                 }
                                                                 aria-current={
                                                                      current() ===
                                                                      section.index
                                                                           ? "true"
                                                                           : undefined
                                                                 }
                                                                 class={cn(
                                                                      "group ease-quiet flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors duration-200",
                                                                      current() ===
                                                                           section.index
                                                                           ? "border-white bg-olive-500 text-white font-medium"
                                                                           : "border-olive-600/60 text-paper bg-olive-500/60"
                                                                 )}
                                                            >
                                                                 <span
                                                                      class={cn(
                                                                           "tilik-index text-[0.7rem] transition-colors duration-200",
                                                                           current() ===
                                                                                section.index
                                                                                ? "text-paper"
                                                                                : "group-hover:text-paper text-paper"
                                                                      )}
                                                                 >
                                                                      {String(
                                                                           section.index
                                                                      ).padStart(
                                                                           2,
                                                                           "0"
                                                                      )}
                                                                 </span>
                                                                 {section.title}
                                                            </button>
                                                       </li>
                                                  )}
                                             </For>
                                        </ul>
                                   </nav>
                              </header>
                              <div
                                   ref={scroller}
                                   class="min-h-0 flex-1 overflow-y-auto overscroll-contain"
                              >
                                   {/* <div class="flex items-start gap-2 px-8 py-4 border-b border-line">
                                        <Info
                                             class={cn(
                                                  "size-4 shrink-0 text-olive-500"
                                             )}
                                        />

                                        <p class="max-w-3xl text-xs leading-relaxed text-ink">
                                             {resultSummary(
                                                  data().location,
                                                  data().meta
                                             )}
                                        </p>
                                   </div> */}

                                   {/* <ReportHighlights report={data()} /> */}

                                   {/*
                                     * Each section is fenced off from the
                                     * others. See `SectionBoundary`: without
                                     * it, one section throwing leaves the
                                     * reader on the skeleton forever.
                                     *
                                     * The titles here must match `SECTIONS`
                                     * above, which `report-index.test.tsx`
                                     * checks, because a fallback renders the
                                     * heading itself.
                                     */}
                                   <SectionBoundary index={1} title="Terrain">
                                        <TerrainSection
                                             index={1}
                                             terrain={data().terrain}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary index={2} title="Flood">
                                        <FloodSection
                                             index={2}
                                             flood={data().flood}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary
                                        index={3}
                                        title="Hazard index"
                                   >
                                        <HazardSection
                                             index={3}
                                             hazards={data().hazards}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary
                                        index={4}
                                        title="Disaster history"
                                   >
                                        <DisasterSection
                                             index={4}
                                             disasters={data().disasters}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary
                                        index={5}
                                        title="Local news"
                                   >
                                        <NewsSection
                                             index={5}
                                             news={data().news}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary
                                        index={6}
                                        title="Air quality"
                                   >
                                        <AirQualitySection
                                             index={6}
                                             airQuality={data().airQuality}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary
                                        index={7}
                                        title="What's nearby"
                                   >
                                        <PlacesSection
                                             index={7}
                                             places={data().places}
                                        />
                                   </SectionBoundary>
                                   <SectionBoundary index={8} title="Area">
                                        <AreaSection
                                             index={8}
                                             area={data().area}
                                        />
                                   </SectionBoundary>

                                   <footer
                                        class={cn(
                                             "px-4 py-4 sm:px-8",
                                             BAND[data().assessment.level]
                                        )}
                                   >
                                        <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-khaki-200">
                                             <span class="flex items-center gap-1.5">
                                                  <Clock size={12} />
                                                  Checked{" "}
                                                  {formatDate(
                                                       data().meta.generatedAt
                                                  )}
                                             </span>

                                             <span>
                                                  {answeredSources().length} of{" "}
                                                  {data().meta.sources.length}{" "}
                                                  sources answered
                                             </span>
                                        </div>

                                        <p class="mt-3 flex gap-2.5 border-t border-paper/15 pt-3 text-xs leading-relaxed text-paper">
                                             <TriangleAlert class="shrink-0 size-4 text-yellow-600" />{" "}
                                             {data().assessment.disclaimer}
                                        </p>
                                   </footer>
                              </div>
                         </article>
                    )}
               </Match>
          </Switch>
     );
}
