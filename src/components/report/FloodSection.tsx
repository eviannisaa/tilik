import { Show } from "solid-js";
import Waves from "lucide-solid/icons/waves";
import type { FloodInfo, RiskLevel } from "../../lib/types";
import { formatDistance, titleCase } from "../../lib/format";
import ReportSection from "./ReportSection";
import Badge from "../ui/Badge";
import {
     CloudAlert,
     Droplets,
     MapPin,
     MapPinned,
     TriangleAlert,
     WavesHorizontal,
} from "lucide-solid";

const RISK_TONE: Record<RiskLevel, "olive" | "khaki" | "clay" | "neutral"> = {
     low: "olive",
     medium: "khaki",
     high: "clay",
     unknown: "neutral",
};

/** BNPB's own ordering, for saying whether the model reads higher or lower. */
const SEVERITY: Record<RiskLevel, number> = {
     unknown: -1,
     low: 0,
     medium: 1,
     high: 2,
};

/**
 * How this section's verdict stands next to BNPB's national flood model.
 *
 * When the model *is* the verdict, saying so stops the same reading being read
 * twice as two agreeing sources. When something else decided it, the model is
 * either corroboration or a disagreement — and a disagreement is the most useful
 * thing here, so it gets said out loud rather than left for the reader to spot
 * by comparing two sections.
 */
function modelComparison(flood: FloodInfo): string | null {
     if (flood.hazardIndex === null || flood.hazardLevel === null) return null;

     const index = `${flood.hazardIndex.toFixed(2)} of 1.00`;

     if (flood.basis === "inarisk") {
          return "This is the Flood row of the hazard index below, the same reading rather than a second source.";
     }

     if (flood.risk === "unknown") {
          return `BNPB's national model does read this point: index ${index}, which it classes ${flood.hazardLevel}.`;
     }

     if (flood.hazardLevel === flood.risk) {
          return `BNPB's national model agrees, at index ${index}.`;
     }

     const direction =
          SEVERITY[flood.hazardLevel] > SEVERITY[flood.risk]
               ? "higher"
               : "lower";
     const authority =
          flood.basis === "postgis"
               ? "The mapped zone is the more specific source, but the gap is worth asking about locally."
               : "Neither is measured on the ground, so treat the gap as a reason to ask locally.";

     return `BNPB's national model reads this ${direction}: index ${index}, which it classes ${flood.hazardLevel}. ${authority}`;
}

const BASIS_LABEL: Record<FloodInfo["basis"], string> = {
     postgis: "From a mapped flood zone",
     inarisk: "From BNPB's national model",
     heuristic: "Estimated from elevation and water",
     none: "No source answered",
};

export default function FloodSection(props: {
     flood: FloodInfo;
     index: number;
}) {
     return (
          <ReportSection
               index={props.index}
               title="Flood"
               lede="Whether water is likely to be a problem here."
               icon={<Waves size={15} />}
               confidence={props.flood.confidence}
          >
               <Show when={modelComparison(props.flood)}>
                    {(line) => (
                         <p class="mb-5 max-w-4xl text-xs leading-relaxed text-ink-faint">
                              <span class="text-olive-600 font-semibold">
                                   1.
                              </span>{" "}
                              Flood hazard nearby
                         </p>
                    )}
               </Show>

               <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
                    <Badge tone={RISK_TONE[props.flood.risk]}>
                         {props.flood.risk === "unknown"
                              ? "Unknown risk"
                              : `${props.flood.risk} risk`}
                    </Badge>
                    <span class="text-ink-faint capitalize text-xs font-semibold">
                         {BASIS_LABEL[props.flood.basis]}
                    </span>
               </div>

               <p class="py-4 text-sm leading-relaxed text-ink-soft">
                    {props.flood.reason}
               </p>

               <Show when={modelComparison(props.flood)}>
                    {(line) => (
                         <p class="mt-2 max-w-4xl text-xs leading-relaxed text-ink-faint">
                              <span class="text-olive-600 font-semibold">
                                   2.
                              </span>{" "}
                              {line()}
                         </p>
                    )}
               </Show>

               <dl class="mt-5 grid gap-x-10 gap-y-4 sm:grid-cols-3 items-center">
                    <div>
                         <div class="flex gap-2 items-center">
                              <Droplets class="size-4 text-olive-600/60" />
                              <dt class="text-ink-faint text-xs">
                                   Nearest water
                              </dt>
                         </div>
                         <dd class="mt-1 text-sm text-ink font-semibold">
                              <Show
                                   when={props.flood.nearestRiver}
                                   fallback="No mapped waterway nearby"
                              >
                                   {(river) => (
                                        <div class="flex items-center text-sm gap-1.5">
                                             {river().name ??
                                                  titleCase(river().kind)}
                                             <span class="text-ink-soft">
                                                  (
                                                  {formatDistance(
                                                       river().distanceMeters
                                                  )}
                                                  )
                                             </span>
                                        </div>
                                   )}
                              </Show>
                         </dd>
                    </div>

                    <div>
                         <div class="flex gap-2 items-center">
                              <CloudAlert class="size-4 text-olive-600/60" />
                              <dt class="text-ink-faint text-xs">
                                   InaRISK flood index
                              </dt>
                         </div>
                         <dd class="mt-1 text-sm text-ink font-semibold">
                              <Show
                                   when={props.flood.hazardIndex !== null}
                                   fallback="No reading for this point"
                              >
                                   <span class="tilik-figure">
                                        {props.flood.hazardIndex!.toFixed(2)}
                                   </span>
                                   <span class="ml-1.5 text-sm text-ink-faint">
                                        of 1.00
                                   </span>
                              </Show>
                         </dd>
                    </div>

                    <div>
                         <div class="flex gap-2 items-center">
                              <MapPinned class="size-4 text-olive-600/60" />
                              <dt class="text-ink-faint text-xs">Flood zone</dt>
                         </div>
                         <dd class="mt-1 text-sm text-ink font-semibold">
                              {props.flood.zoneName ?? "Not mapped in our data"}
                         </dd>
                    </div>
               </dl>
          </ReportSection>
     );
}
