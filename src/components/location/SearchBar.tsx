import { createSignal, For, onCleanup, Show } from "solid-js";
import Search from "lucide-solid/icons/search";
import X from "lucide-solid/icons/x";
import MapPin from "lucide-solid/icons/map-pin";
import Crosshair from "lucide-solid/icons/crosshair";
import { ApiError, api } from "../../lib/api";
import { locationStore } from "../../lib/store";
import { looksLikeCoordinates, parseCoordinates } from "../../lib/coordinates";
import type { SearchResult } from "../../lib/types";
import Skeleton from "../ui/Skeleton";

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 3;

export default function SearchBar() {
     let inputRef!: HTMLInputElement;
     let debounceTimer: ReturnType<typeof setTimeout> | undefined;
     let controller: AbortController | undefined;

     const [query, setQuery] = createSignal("");
     const [results, setResults] = createSignal<SearchResult[]>([]);
     const [open, setOpen] = createSignal(false);
     const [searching, setSearching] = createSignal(false);
     const [error, setError] = createSignal<string | null>(null);
     const [activeIndex, setActiveIndex] = createSignal(-1);

     function reset() {
          setResults([]);
          setOpen(false);
          setActiveIndex(-1);
          setError(null);
     }

     /** Coordinates pasted into the place field, recognised without a round trip. */
     const pastedCoordinates = () =>
          looksLikeCoordinates(query()) ? parseCoordinates(query()) : null;

     function useCoordinates() {
          const coordinates = pastedCoordinates();
          if (!coordinates) return;

          locationStore.select({
               latitude: coordinates.latitude,
               longitude: coordinates.longitude,
               name: null,
               origin: "coordinates",
          });
          reset();
          inputRef.blur();
     }

     function onInput(value: string) {
          setQuery(value);
          clearTimeout(debounceTimer);
          controller?.abort();

          if (looksLikeCoordinates(value)) {
               setSearching(false);
               setResults([]);
               setError(null);
               setOpen(true);
               return;
          }

          if (value.trim().length < MIN_QUERY_LENGTH) {
               setSearching(false);
               reset();
               return;
          }

          setSearching(true);
          setOpen(true);
          debounceTimer = setTimeout(
               () => void runSearch(value.trim()),
               DEBOUNCE_MS
          );
     }

     async function runSearch(term: string) {
          controller = new AbortController();
          try {
               const response = await api.search(term, {
                    signal: controller.signal,
               });
               setResults(response.results);
               setActiveIndex(response.results.length ? 0 : -1);
               setError(
                    response.results.length
                         ? null
                         : "No places matched that. Try a different spelling."
               );
          } catch (err) {
               if (err instanceof DOMException && err.name === "AbortError")
                    return;
               setResults([]);
               setError(
                    err instanceof ApiError
                         ? err.message
                         : "Search is unavailable right now."
               );
          } finally {
               setSearching(false);
          }
     }

     function choose(result: SearchResult) {
          locationStore.select({
               latitude: result.latitude,
               longitude: result.longitude,
               name: result.name,
               origin: "search",
               district: result.district,
               city: result.city,
               province: result.province,
          });
          setQuery(result.name);
          reset();
          inputRef.blur();
     }

     function onKeyDown(event: KeyboardEvent) {
          if (event.key === "Escape") {
               reset();
               return;
          }
          if (event.key === "Enter" && pastedCoordinates()) {
               event.preventDefault();
               useCoordinates();
               return;
          }
          if (!open() || !results().length) return;

          if (event.key === "ArrowDown") {
               event.preventDefault();
               setActiveIndex((index) => (index + 1) % results().length);
          } else if (event.key === "ArrowUp") {
               event.preventDefault();
               setActiveIndex(
                    (index) => (index - 1 + results().length) % results().length
               );
          } else if (event.key === "Enter") {
               event.preventDefault();
               const result = results()[activeIndex()];
               if (result) choose(result);
          }
     }

     onCleanup(() => {
          clearTimeout(debounceTimer);
          controller?.abort();
     });

     return (
          <div class="relative">
               <div class="flex items-center gap-2">
                    <div class="relative flex-1">
                         <span class="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-ink-faint">
                              <Search size={17} />
                         </span>

                         <input
                              ref={inputRef}
                              type="search"
                              value={query()}
                              role="combobox"
                              aria-expanded={open()}
                              aria-controls="tilik-search-results"
                              aria-autocomplete="list"
                              autocomplete="off"
                              placeholder="Search an address, village, or city…"
                              class="h-12 w-full rounded-full border border-line bg-paper-raised pl-10 pr-10 text-sm text-ink placeholder:text-ink-faint focus:border-line-strong focus:outline-none [&::-webkit-search-cancel-button]:hidden"
                              onInput={(event) =>
                                   onInput(event.currentTarget.value)
                              }
                              onKeyDown={onKeyDown}
                              onFocus={() => results().length && setOpen(true)}
                              onBlur={() =>
                                   setTimeout(() => setOpen(false), 140)
                              }
                         />

                         <Show when={query()}>
                              <button
                                   type="button"
                                   aria-label="Clear search"
                                   class="absolute inset-y-0 right-3 flex items-center text-ink-faint transition-colors hover:text-ink"
                                   onClick={() => {
                                        setQuery("");
                                        reset();
                                        inputRef.focus();
                                   }}
                              >
                                   <X size={16} />
                              </button>
                         </Show>
                    </div>
               </div>

               <Show
                    when={
                         open() &&
                         (searching() ||
                              results().length > 0 ||
                              error() ||
                              looksLikeCoordinates(query()))
                    }
               >
                    <div
                         id="tilik-search-results"
                         role="listbox"
                         class="absolute z-30 mt-2 w-full overflow-hidden rounded-2xl border border-line bg-paper-raised shadow-lift"
                    >
                         <Show when={pastedCoordinates()}>
                              {(coordinates) => (
                                   <button
                                        type="button"
                                        class="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-paper-sunk"
                                        onClick={useCoordinates}
                                   >
                                        <span class="mt-0.5 shrink-0 text-ink-faint">
                                             <Crosshair size={15} />
                                        </span>
                                        <span class="min-w-0">
                                             <span class="tilik-figure block text-sm font-medium text-ink">
                                                  {coordinates().latitude},{" "}
                                                  {coordinates().longitude}
                                             </span>
                                             <span class="block text-xs text-ink-faint">
                                                  Use these coordinates
                                                  {coordinates().swapped
                                                       ? " · reordered as latitude, longitude"
                                                       : ""}
                                             </span>
                                        </span>
                                   </button>
                              )}
                         </Show>

                         <Show
                              when={
                                   looksLikeCoordinates(query()) &&
                                   !pastedCoordinates()
                              }
                         >
                              <p class="px-4 py-3.5 text-sm text-ink-soft">
                                   That looks like coordinates but isn't a valid
                                   pair yet.
                              </p>
                         </Show>

                         <Show when={searching()}>
                              <div class="space-y-3 p-4">
                                   <Skeleton class="h-3.5 w-2/3" />
                                   <Skeleton class="h-3.5 w-1/2" />
                                   <Skeleton class="h-3.5 w-3/5" />
                              </div>
                         </Show>

                         <Show when={!searching() && error()}>
                              <p class="px-4 py-3.5 text-sm text-ink-soft">
                                   {error()}
                              </p>
                         </Show>

                         <Show when={!searching() && results().length > 0}>
                              <ul class="max-h-72 overflow-y-auto py-1">
                                   <For each={results()}>
                                        {(result, index) => (
                                             <li>
                                                  <button
                                                       type="button"
                                                       role="option"
                                                       aria-selected={
                                                            activeIndex() ===
                                                            index()
                                                       }
                                                       class="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors"
                                                       classList={{
                                                            "bg-paper-sunk":
                                                                 activeIndex() ===
                                                                 index(),
                                                       }}
                                                       onMouseEnter={() =>
                                                            setActiveIndex(
                                                                 index()
                                                            )
                                                       }
                                                       onClick={() =>
                                                            choose(result)
                                                       }
                                                  >
                                                       <span class="mt-0.5 shrink-0 text-ink-faint">
                                                            <MapPin size={15} />
                                                       </span>
                                                       <span class="min-w-0">
                                                            <span class="block truncate text-sm font-medium text-ink">
                                                                 {result.name}
                                                            </span>
                                                            <span class="block truncate text-xs text-ink-faint">
                                                                 {
                                                                      result.displayName
                                                                 }
                                                            </span>
                                                       </span>
                                                  </button>
                                             </li>
                                        )}
                                   </For>
                              </ul>
                         </Show>
                    </div>
               </Show>
          </div>
     );
}
