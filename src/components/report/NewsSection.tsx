import { createMemo, createSignal, For, Show } from "solid-js";
import Newspaper from "lucide-solid/icons/newspaper";
import ExternalLink from "lucide-solid/icons/external-link";
import type { LocalNews } from "../../lib/types";
import { cn } from "../../lib/cn";
import { formatDate, relativeDays } from "../../lib/format";
import ReportSection from "./ReportSection";

const INITIAL_ITEMS = 5;

/** Every other section is measured or modelled; this one is reported. */
const EMPTY_COPY: Record<string, { title: string; detail: string }> = {
     no_results: {
          title: "Nothing reported in this window.",
          detail: "No local coverage mentioned a hazard here. Quiet coverage is not the same as a quiet place. Small events often go unreported.",
     },
     no_area: {
          title: "We couldn't name this area.",
          detail: "News can only be searched by place name, and no administrative name resolved for this point. Try a coordinate closer to a named settlement.",
     },
     unavailable: {
          title: "The news feed didn't answer.",
          detail: "Every other section of this report is unaffected. Re-run the check to try again.",
     },
};

export default function NewsSection(props: { news: LocalNews; index: number }) {
     const [topic, setTopic] = createSignal<string | null>(null);
     const [showAll, setShowAll] = createSignal(false);

     /** Counts drive the filter chips, so a topic with nothing in it never shows. */
     const counts = createMemo(() => {
          const tally = new Map<string, { label: string; count: number }>();
          for (const item of props.news.items) {
               const seen = tally.get(item.topic);
               if (seen) seen.count += 1;
               else tally.set(item.topic, { label: item.topicLabel, count: 1 });
          }
          return [...tally.entries()].sort((a, b) => b[1].count - a[1].count);
     });

     const filtered = createMemo(() => {
          const key = topic();
          return key === null
               ? props.news.items
               : props.news.items.filter((i) => i.topic === key);
     });

     const visible = () =>
          showAll() ? filtered() : filtered().slice(0, INITIAL_ITEMS);

     return (
          <ReportSection
               index={props.index}
               title="Local news"
               lede="What's actually been reported around here lately."
               icon={<Newspaper size={15} />}
          >
               <Show
                    when={props.news.items.length}
                    fallback={
                         <div class="border-t border-line pt-4 text-sm text-ink-soft">
                              <p class="text-ink">
                                   {EMPTY_COPY[props.news.status]?.title ??
                                        "No local news to show."}
                              </p>
                              <p class="mt-1 text-xs leading-relaxed text-ink-faint">
                                   {props.news.note ??
                                        EMPTY_COPY[props.news.status]?.detail}
                              </p>
                         </div>
                    }
               >
                    <Show when={counts().length > 1}>
                         <div
                              class="mt-3 flex flex-wrap gap-1.5"
                              role="group"
                              aria-label="Filter news by topic"
                         >
                              <button
                                   type="button"
                                   onClick={() => setTopic(null)}
                                   aria-pressed={topic() === null}
                                   class={cn(
                                        "rounded-full border px-2.5 py-1 text-xs transition-colors",
                                        topic() === null
                                             ? "border-olive-700 bg-olive-700 text-paper"
                                             : "border-line bg-paper text-ink-soft hover:border-line-strong hover:text-ink"
                                   )}
                              >
                                   All {props.news.items.length}
                              </button>

                              <For each={counts()}>
                                   {([key, entry]) => (
                                        <button
                                             type="button"
                                             onClick={() =>
                                                  setTopic(
                                                       topic() === key
                                                            ? null
                                                            : key
                                                  )
                                             }
                                             aria-pressed={topic() === key}
                                             class={cn(
                                                  "rounded-full border px-2.5 py-1 text-xs transition-colors",
                                                  topic() === key
                                                       ? "border-olive-700 bg-olive-700 text-paper"
                                                       : "border-line bg-paper text-ink-soft hover:border-line-strong hover:text-ink"
                                             )}
                                        >
                                             {entry.label} {entry.count}
                                        </button>
                                   )}
                              </For>
                         </div>
                    </Show>

                    <ul class="mt-3 divide-y divide-line/50">
                         <For each={visible()}>
                              {(item) => (
                                   <li class="py-3 first:pt-2">
                                        <a
                                             href={item.url}
                                             target="_blank"
                                             rel="noreferrer noopener"
                                             class="group flex items-baseline gap-1.5 text-sm leading-snug text-ink transition-colors hover:text-olive-700"
                                        >
                                             <span class="min-w-0">
                                                  {item.title}
                                                  <ExternalLink
                                                       size={12}
                                                       class="ml-1.5 inline-block text-ink-faint transition-colors group-hover:text-olive-700"
                                                  />
                                             </span>
                                        </a>

                                        <p class="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-faint">
                                             <span class="text-ink-soft">
                                                  {item.topicLabel}
                                             </span>
                                             <Show when={item.source}>
                                                  {(source) => (
                                                       <>
                                                            <span aria-hidden="true">
                                                                 ·
                                                            </span>
                                                            <span>
                                                                 {source()}
                                                            </span>
                                                       </>
                                                  )}
                                             </Show>
                                             <span aria-hidden="true">·</span>
                                             <time
                                                  datetime={
                                                       item.publishedAt ??
                                                       undefined
                                                  }
                                             >
                                                  {relativeDays(
                                                       item.publishedAt
                                                  ) ??
                                                       formatDate(
                                                            item.publishedAt
                                                       )}
                                             </time>
                                        </p>
                                   </li>
                              )}
                         </For>
                    </ul>

                    <Show when={filtered().length > INITIAL_ITEMS}>
                         <button
                              type="button"
                              onClick={() => setShowAll(!showAll())}
                              class="mt-3 text-xs text-ink-faint underline decoration-line-strong decoration-1 underline-offset-4 transition-colors hover:text-ink hover:decoration-olive-500"
                         >
                              {showAll()
                                   ? `Show only the latest ${INITIAL_ITEMS}`
                                   : `Show all ${filtered().length} stories`}
                         </button>
                    </Show>
               </Show>
          </ReportSection>
     );
}
