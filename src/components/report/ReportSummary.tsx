import { Match, Show, Switch } from "solid-js";
import { cn } from "../../lib/cn";
import { locationStore } from "../../lib/store";
import Button from "../ui/Button";
import InlineAlert from "../ui/InlineAlert";
import Panel from "../ui/Panel";
import Skeleton from "../ui/Skeleton";
import AssessmentSummary from "./AssessmentSummary";
import ReportGaps from "./ReportGaps";

/**
 * The answer, on its own.
 *
 * The verdict and what the check couldn't reach — separated from the detail
 * sections so it can sit beside the map, in view, while the evidence runs full
 * width below. The four highlight figures moved to {@link ReportPanel}, where
 * they have the width to sit in one row. Everything here is a conclusion; nothing
 * here is evidence.
 *
 * It also owns the two things there must only ever be one of: the `#report`
 * anchor, and the failure notice with its retry.
 */
export default function ReportSummary() {
     const status = locationStore.reportStatus;
     const report = locationStore.report;

     return (
          <div id="report" class="scroll-mt-6">
               <Switch>
                    <Match when={status() === "loading" && !report()}>
                         <Panel class="overflow-hidden">
                              <div aria-hidden="true">
                                   <div class="bg-paper-sunk px-4 py-8 sm:px-6">
                                        <Skeleton class="h-3 w-28" />
                                        <Skeleton class="mt-3.5 h-8 w-48" />
                                        <Skeleton class="mt-3 h-3.5 w-full max-w-xs" />
                                        <Skeleton class="mt-2 h-3.5 w-3/5" />
                                   </div>
                              </div>
                         </Panel>
                    </Match>

                    <Match when={status() === "error"}>
                         <InlineAlert
                              tone="warning"
                              title="That check didn't go through"
                              action={
                                   <Button
                                        size="sm"
                                        variant="secondary"
                                        onClick={() =>
                                             void locationStore.check()
                                        }
                                   >
                                        Retry
                                   </Button>
                              }
                         >
                              {locationStore.reportError()}
                         </InlineAlert>
                    </Match>

                    <Match when={report()}>
                         {(data) => (
                              <Panel
                                   as="article"
                                   class={cn(
                                        "overflow-hidden transition-opacity duration-200",
                                        status() === "loading" && "opacity-60"
                                   )}
                                   aria-busy={status() === "loading"}
                              >
                                   <Show when={status() === "loading"}>
                                        <p
                                             role="status"
                                             class="flex items-center gap-2 border-b border-line bg-paper-sunk px-4 py-2 text-xs text-ink-soft sm:px-6"
                                        >
                                             <span
                                                  class="size-3 shrink-0 animate-spin rounded-full border-2 border-olive-500 border-t-transparent"
                                                  aria-hidden="true"
                                             />
                                             Updating this report…
                                        </p>
                                   </Show>

                                   <AssessmentSummary
                                        assessment={data().assessment}
                                   />
                              </Panel>
                         )}
                    </Match>
               </Switch>
          </div>
     );
}
