import { For, Show } from "solid-js";
import Minus from "lucide-solid/icons/minus";
import TrendingDown from "lucide-solid/icons/trending-down";
import TrendingUp from "lucide-solid/icons/trending-up";
import ArrowRight from "lucide-solid/icons/arrow-right";
import type { Assessment, AssessmentLevel } from "../../lib/types";
import { displayStore } from "../../lib/store";
import Button from "../ui/Button";
import { cn } from "../../lib/cn";
import { Info } from "lucide-solid";

/**
 * Level styling for the verdict block.
 *
 * `bg` is a deeper surface than the rest of the report so the block reads as the
 * answer rather than more page: the old `-50` tints separated from the card by
 * 1.20–1.30:1, effectively invisible.
 *
 * The level word is set in `ink`, not in the level colour. Khaki is too light to
 * serve as text on a khaki-tinted surface (3.55–3.90:1 at these depths), and it
 * follows the rule the hazard meters already use — text wears text tokens, and a
 * coloured mark beside it carries identity. That mark is `dot`, dark enough to
 * clear 3:1 against its own surface.
 */
const LEVEL_COPY: Record<
     AssessmentLevel,
     { label: string; dot: string; bg: string; track: string; text: string }
> = {
     low: {
          label: "Low concern",
          dot: "bg-[#35432E]",
          bg: "bg-[#7A8768]",
          track: "bg-paper/30",
          text: "text-[#5F6F50]",
     },
     moderate: {
          label: "Moderate concern",
          dot: "bg-[#5F4D25]",
          bg: "bg-[#B39A62]",
          track: "bg-paper/30",
          text: "text-[#E5D8B8]",
     },
     higher: {
          label: "Higher concern",
          dot: "bg-paper",
          bg: "bg-olive-600",
          track: "bg-[#D8BDB5]",
          text: "text-[#5A302A]",
     },
     unknown: {
          label: "Not enough data",
          dot: "bg-ink-faint",
          bg: "bg-verdict-unknown",
          track: "bg-ink/15",
          text: "text-ink",
     },
};

const ORDER: AssessmentLevel[] = ["low", "moderate", "higher"];

export default function AssessmentSummary(props: { assessment: Assessment }) {
     const level = () => LEVEL_COPY[props.assessment.level];

     return (
          <div
               class={cn(
                    "rounded-t-card border-b border-ink/15 py-6 px-1",
                    level().bg
               )}
          >
               <div class="h-62.5 overflow-y-auto px-6">
                    <p class="max-w-prose text-[0.9rem] leading-relaxed text-paper/80">
                         {props.assessment.headline}
                    </p>

                    <Show when={props.assessment.factors.length}>
                         <ul class="mt-5 space-y-2.5 border-t border-paper/15 pt-4">
                              <For each={props.assessment.factors}>
                                   {(factor) => (
                                        <li class="flex items-start gap-2.5 text-sm">
                                             <span
                                                  class={cn(
                                                       "mt-0.5 shrink-0",
                                                       factor.impact ===
                                                            "negative"
                                                            ? "text-clay-500"
                                                            : factor.impact ===
                                                                "positive"
                                                              ? "text-green-700"
                                                              : "text-yellow-500"
                                                  )}
                                             >
                                                  {factor.impact ===
                                                  "negative" ? (
                                                       <TrendingUp size={14} />
                                                  ) : factor.impact ===
                                                    "positive" ? (
                                                       <TrendingDown
                                                            size={14}
                                                       />
                                                  ) : (
                                                       <Minus size={14} />
                                                  )}
                                             </span>
                                             <span class="text-paper/80">
                                                  <span
                                                       class={cn(
                                                            "font-medium text-paper/80"
                                                       )}
                                                  >
                                                       {factor.label}.
                                                  </span>{" "}
                                                  {factor.detail}
                                             </span>
                                        </li>
                                   )}
                              </For>
                         </ul>
                    </Show>
               </div>

               <div class="mt-5 border-t border-paper/20 px-6 pt-5">
                    <Button
                         variant="secondary"
                         quiet
                         class="group w-full justify-between"
                         onClick={() => displayStore.openReport()}
                    >
                         Show the result
                         <ArrowRight
                              size={16}
                              strokeWidth={2}
                              class="ease-quiet shrink-0 text-ink-faint transition duration-300 group-hover:translate-x-0.5 group-hover:text-ink"
                         />
                    </Button>
               </div>
          </div>
     );
}
