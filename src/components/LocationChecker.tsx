import { createEffect, lazy, on, Suspense } from "solid-js";
import LocationInput from "./location/LocationInput";
import SelectedLocation from "./location/SelectedLocation";
import MapSkeleton from "./map/MapSkeleton";

/**
 * Loaded on its own, after the page is interactive.
 *
 * `maplibre-gl` is about 800 KB of the megabyte this island used to ship, and
 * importing it here put it in the same chunk as the search box. With
 * `client:only` nothing renders until that chunk has downloaded, parsed and
 * mounted — so the whole page waited on a map the reader had not asked to look
 * at yet. Split out, the form appears as soon as its own chunk lands and the map
 * fills in behind its skeleton, which already existed for exactly this gap.
 */
const LocationMap = lazy(() => import("./map/LocationMap"));
import ReportPanel from "./report/ReportPanel";
import ReportSummary from "./report/ReportSummary";
import Dialog from "./ui/Dialog";
import { displayStore, locationStore } from "./../lib/store";

export default function LocationChecker() {
     /**
      * Bring a finished report into view. Stacked, it lands below the map and is
      * off screen; side by side it is usually already visible, and scrolling
      * something the reader can already see is just a jolt — so check first.
      */
     createEffect(
          on(
               locationStore.reportStatus,
               (status, previous) => {
                    if (status !== "ready" || previous === "ready") return;
                    if (typeof window === "undefined") return;

                    const report = document.getElementById("report");
                    if (!report) return;

                    const { top } = report.getBoundingClientRect();
                    const alreadyReading =
                         top >= 0 && top < window.innerHeight * 0.6;
                    if (alreadyReading) return;

                    report.scrollIntoView({
                         behavior: "smooth",
                         block: "start",
                    });
               },
               { defer: true }
          )
     );

     return (
          <div class="space-y-4">
               <LocationInput />

               <div class="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,3fr)] lg:items-start">
                    <div class="lg:sticky lg:top-24">
                         <div
                              id="tilik-map"
                              class="h-[46vh] min-h-120 rounded-card lg:h-165"
                         >
                              <Suspense fallback={<MapSkeleton />}>
                                   <LocationMap />
                              </Suspense>
                         </div>
                    </div>

                    <div class="space-y-4">
                         <SelectedLocation />
                         <ReportSummary />
                    </div>
               </div>

               <Dialog
                    open={displayStore.reportOpen()}
                    onClose={() => displayStore.closeReport()}
                    label="The evidence behind this verdict"
               >
                    <ReportPanel />
               </Dialog>
          </div>
     );
}
