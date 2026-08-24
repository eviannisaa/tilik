import { For } from "solid-js";
import { cn } from "../../lib/cn";
import Skeleton from "../ui/Skeleton";

/**
 * Mirrors the panel's rhythm so the layout doesn't jump when data lands: the
 * highlight tiles first, then the detail sections. Full bleed, for the same
 * reason {@link ReportPanel} is — the dialog around it is already the card. The
 * verdict block has its own skeleton in {@link ReportSummary}.
 */
export default function ReportSkeleton() {
     return (
          <div aria-hidden="true">
               <div class="grid grid-cols-2 lg:grid-cols-4">
                    {[0, 1, 2, 3].map((index) => (
                         <div
                              class={cn(
                                   "px-4 py-4 sm:px-8",
                                   index % 2 === 1 && "border-l border-line",
                                   index >= 2 &&
                                        "border-t border-line lg:border-t-0",
                                   index === 2 && "lg:border-l lg:border-line"
                              )}
                         >
                              <Skeleton class="h-3 w-16" />
                              <Skeleton class="mt-2.5 h-6 w-14" />
                              <Skeleton class="mt-2.5 h-3 w-20" />
                         </div>
                    ))}
               </div>

               <For each={[0, 1, 2, 3, 4, 5, 6]}>
                    {() => (
                         <div class="border-t border-line px-4 py-6 first:border-t-0 sm:px-8">
                              <Skeleton class="h-3.5 w-28" />
                              <div class="mt-4 space-y-2.5 sm:pl-8">
                                   <Skeleton class="h-6 w-40" />
                                   <Skeleton class="h-3.5 w-full max-w-lg" />
                                   <Skeleton class="h-3.5 w-2/3 max-w-md" />
                              </div>
                         </div>
                    )}
               </For>
          </div>
     );
}
