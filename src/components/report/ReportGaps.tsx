import { For, Show } from "solid-js";
import CloudOff from "lucide-solid/icons/cloud-off";
import RotateCw from "lucide-solid/icons/rotate-cw";
import { locationStore } from "../../lib/store";
import type { DataSource, ReportMeta } from "../../lib/types";

/**
 * What this check is missing, and what to do about it.
 *
 * Built from `meta.sources` rather than `meta.degraded`: the sources carry the
 * `field` that failed, so the notice can name the affected section instead of
 * saying "parts of this report are estimated" and leaving the reader to guess
 * which parts.
 */

const FIELD_LABEL: Record<string, string> = {
  location: "Place name",
  elevation: "Elevation",
  waterways: "Nearby water",
  flood: "Flood risk",
  hazards: "Hazard index",
  disasters: "Disaster history",
  news: "Local news",
  places: "What's nearby",
};

/** Providers arrive as slugs; nobody knows what "opentopodata" is. */
const PROVIDER_LABEL: Record<string, string> = {
  overpass: "OpenStreetMap",
  inarisk: "BNPB InaRISK",
  nominatim: "Nominatim",
  opentopodata: "OpenTopoData",
  opentopography: "OpenTopography",
  postgis: "the local database",
  heuristic: "our own estimate",
  "google-news": "Google News",
  unavailable: "The source",
};

function providerName(provider: string): string {
  return PROVIDER_LABEL[provider] ?? provider;
}

/** "a, b and c" rather than "a and b and c". */
function joinFields(fields: string[]): string {
  const lower = fields.map((field) => field.toLowerCase());
  if (lower.length === 1) return lower[0]!;
  return `${lower.slice(0, -1).join(", ")} and ${lower.at(-1)}`;
}

/** One line per provider, not per field: Overpass failing takes two sections
 *  with it, and saying so twice reads like two separate problems. */
function groupByProvider(sources: DataSource[]): Array<{ provider: string; fields: string[] }> {
  const grouped = new Map<string, string[]>();

  for (const source of sources) {
    const label = FIELD_LABEL[source.field] ?? source.field;
    const existing = grouped.get(source.provider);
    if (existing) existing.push(label);
    else grouped.set(source.provider, [label]);
  }

  return [...grouped].map(([provider, fields]) => ({ provider, fields }));
}

export default function ReportGaps(props: { meta: ReportMeta }) {
  const missing = () => props.meta.sources.filter((source) => source.quality === "unavailable");
  const busy = () => locationStore.reportStatus() === "loading";

  return (
    <Show when={missing().length}>
      <section
        aria-label="Gaps in this report"
        class="border-t border-khaki-200 bg-khaki-50 px-4 py-4 sm:px-6"
      >
        <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
          <div class="flex min-w-0 gap-3">
            <span class="mt-0.5 shrink-0 text-khaki-700" aria-hidden="true">
              <CloudOff size={16} />
            </span>

            <div class="min-w-0">
              <p class="text-sm font-medium text-khaki-700">
                {missing().length === 1
                  ? `${FIELD_LABEL[missing()[0]!.field] ?? missing()[0]!.field} is incomplete`
                  : `${missing().length} sections are incomplete`}
              </p>

              <ul class="mt-2 space-y-1.5">
                <For each={groupByProvider(missing())}>
                  {(gap) => (
                    <li class="text-xs leading-relaxed text-ink-soft">
                      <span class="font-medium text-ink">{providerName(gap.provider)}</span>{" "}
                      didn't answer, so {joinFields(gap.fields)}{" "}
                      {gap.fields.length > 1 ? "are" : "is"} missing
                    </li>
                  )}
                </For>
              </ul>

              <p class="mt-2.5 text-xs leading-relaxed text-ink-faint">
                Every other section is unaffected. These sources go down often, so a
                retry usually fills the gap.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void locationStore.check()}
            disabled={busy()}
            class="ease-quiet flex shrink-0 items-center gap-1.5 rounded-lg border border-khaki-200 bg-paper-raised px-3 py-1.5 text-xs font-medium text-ink transition duration-200 hover:border-line-strong active:scale-[0.98] disabled:opacity-60"
          >
            <span class={busy() ? "animate-spin" : undefined}>
              <RotateCw size={13} />
            </span>
            {busy() ? "Retrying…" : "Retry check"}
          </button>
        </div>
      </section>
    </Show>
  );
}
