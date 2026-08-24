import Mountain from "lucide-solid/icons/mountain";
import type { TerrainInfo } from "../../lib/types";
import { formatElevation, titleCase } from "../../lib/format";
import ReportSection from "./ReportSection";
import {
     Earth,
     Globe,
     MountainSnow,
     Sprout,
     WavesHorizontal,
} from "lucide-solid";

export default function TerrainSection(props: {
     terrain: TerrainInfo;
     index: number;
}) {
     return (
          <ReportSection
               index={props.index}
               title="Terrain"
               lede="How high the ground sits, and what that implies for water."
               confidence={props.terrain.confidence}
          >
               <div class="flex flex-wrap items-end gap-x-10 gap-y-4">
                    <div>
                         <p class="text-[1.4rem] font-semibold leading-none tracking-tight text-ink">
                              {formatElevation(props.terrain.elevation)}
                         </p>
                         <p class="mt-2 flex gap-2 items-center text-ink-faint capitalize font-sans text-xs">
                              <WavesHorizontal class="size-4 text-olive-600/60" />
                              Above sea level
                         </p>
                    </div>

                    <div>
                         <p class="text-[1.4rem] font-semibold leading-none tracking-tight text-ink">
                              {titleCase(props.terrain.terrain)}
                         </p>
                         <p class="mt-2 flex gap-2 items-center text-ink-faint capitalize font-sans text-xs">
                              <Earth class="size-4 text-olive-600/60" />
                              Ground type
                         </p>
                    </div>
               </div>

               <p class="mt-5 max-w-prose text-sm leading-relaxed text-ink-soft">
                    {props.terrain.description}
               </p>
          </ReportSection>
     );
}
