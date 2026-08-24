import type { JSX } from "solid-js";
import { Show } from "solid-js";
import type { ConfidenceLevel } from "../../lib/types";
import { cn } from "../../lib/cn";
import { locationStore } from "../../lib/store";

const CONFIDENCE_COPY: Record<
     ConfidenceLevel,
     { label: string; tone: string }
> = {
     high: {
          label: "Measured",
          tone: "text-olive-700 bg-olive-50 border-olive-200",
     },
     medium: {
          label: "Modelled",
          tone: "text-khaki-700 bg-khaki-50 border-khaki-200",
     },
     low: {
          label: "Estimated",
          tone: "text-clay-700 bg-clay-50 border-clay-200",
     },
     none: {
          label: "No data",
          tone: "text-ink-faint bg-paper-sunk border-line",
     },
};

/** The id a section anchors on, and the header index jumps to. */
export function sectionId(index: number) {
     return `tilik-section-${index}`;
}

interface ReportSectionProps {
     /** Position in the report, rendered as the section numeral. */
     index: number;
     title: string;
     icon?: JSX.Element;
     /**
      * Sets the title at display size rather than the standard section size.
      * A typographic distinction only, no colour change: olive and terracotta
      * already mean hazard levels, so a coloured heading would read as one.
      */
     emphasis?: boolean;
     /** One plain-language line about what this section answers. */
     lede?: string;
     confidence?: ConfidenceLevel;
     children: JSX.Element;
}

/**
 * One section of the report.
 *
 * Content is full-width rather than indented under the heading: the old inset
 * left tables and lists starting at a different edge from everything around
 * them, which read as misalignment rather than hierarchy.
 */
export default function ReportSection(props: ReportSectionProps) {
     /**
      * The report is fetched as one call, so every section goes stale together.
      * Each one says so in its own header: a single line at the top of the report is
      * invisible to someone already scrolled down to the section they care about.
      */
     const updating = () => locationStore.reportStatus() === "loading";

     return (
          <section
               id={sectionId(props.index)}
               class="relative border-t border-line px-4 py-8 first:border-t-0 sm:px-8"
               aria-busy={updating()}
          >
               <Show when={updating()}>
                    <div
                         role="progressbar"
                         aria-label={`Updating ${props.title}`}
                         class="absolute inset-x-0 top-0 h-0.5 overflow-hidden bg-olive-50"
                    >
                         <div class="tilik-progress-fill h-full w-1/4 rounded-full bg-olive-500 animate-[tilik-progress_1.1s_ease-in-out_infinite]" />
                    </div>
               </Show>

               <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                    <div class="flex min-w-0 items-center gap-2.5">
                         <h3
                              class={cn(
                                   "font-display min-w-0 leading-none tracking-[-0.02em] text-paper p-1 font-medium text-[1rem] bg-[#505B2B]"
                              )}
                         >
                              {props.title}
                         </h3>
                    </div>

                    <Show
                         when={!updating()}
                         fallback={
                              <span class="flex shrink-0 items-center gap-1.5 rounded-full border border-olive-200 bg-olive-50 tilik-label px-2 py-0.5 text-olive-700">
                                   <span
                                        class="size-2.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
                                        aria-hidden="true"
                                   />
                                   Updating
                              </span>
                         }
                    >
                         <Show when={props.confidence}>
                              {(level) => (
                                   <span
                                        class={cn(
                                             "shrink-0 rounded-full px-2 py-0.5 border border-olive-500! font-semibold bg-olive-500/15 text-olive-500! capitalize font-sans text-xs",
                                             CONFIDENCE_COPY[level()].tone
                                        )}
                                        title={`How this figure was obtained: ${CONFIDENCE_COPY[level()].label.toLowerCase()}`}
                                   >
                                        {CONFIDENCE_COPY[level()].label}
                                   </span>
                              )}
                         </Show>
                    </Show>
               </div>

               <Show when={props.lede}>
                    <p class="mt-2 text-xs leading-relaxed text-ink-faint">
                         {props.lede}
                    </p>
               </Show>

               <div class="mt-5">{props.children}</div>
          </section>
     );
}
