import {
     createEffect,
     createMemo,
     createSignal,
     For,
     on,
     Show,
} from "solid-js";
import ArrowRight from "lucide-solid/icons/arrow-right";
import ClipboardPaste from "lucide-solid/icons/clipboard-paste";
import Keyboard from "lucide-solid/icons/keyboard";
import { cn } from "../../lib/cn";
import { displayStore, locationStore } from "../../lib/store";
import {
     COORDINATE_FORMATS,
     COORDINATE_FORMAT_LABELS,
     COORDINATE_FORMAT_NAMES,
     EXAMPLE_POINT,
     examplePair,
     formatPair,
     formatSignedPair,
     fromParts,
     parseCoordinates,
     splitAxis,
     type AxisParts,
} from "../../lib/coordinates";
import CopyButton from "../ui/CopyButton";
import CoordinateFields from "./CoordinateFields";

const EMPTY: AxisParts = {
     degrees: Number.NaN,
     minutes: 0,
     seconds: 0,
     hemisphere: "",
};

/**
 * Direct coordinate entry, for when you already know the exact spot.
 *
 * The notation is chosen *before* typing, and the fields reshape to match — one
 * box for decimal degrees, three for DMS. Typing `6° 55' 3" S` into a single
 * free-text box is possible but fiddly, so that path stays available for pasting
 * a value from somewhere else.
 */
export default function CoordinateInput() {
     const [mode, setMode] = createSignal<"fields" | "paste">("paste");
     const [pasted, setPasted] = createSignal("");
     const [submitted, setSubmitted] = createSignal(false);

     const [lat, setLat] = createSignal<AxisParts>({
          ...EMPTY,
          hemisphere: "S",
     });
     const [lng, setLng] = createSignal<AxisParts>({
          ...EMPTY,
          hemisphere: "E",
     });

     const format = displayStore.coordinateFormat;

     /** DD arrives as a signed decimal pair; the others as spelled-out notation. */
     const example = () =>
          format() === "dd"
               ? formatSignedPair(
                      EXAMPLE_POINT.latitude,
                      EXAMPLE_POINT.longitude
                 )
               : examplePair(format());

     const latValue = createMemo(() => fromParts(lat(), "lat"));
     const lngValue = createMemo(() => fromParts(lng(), "lng"));

     const parsed = createMemo(() => {
          if (mode() === "paste") return parseCoordinates(pasted());

          const latitude = latValue();
          const longitude = lngValue();
          if (latitude === null || longitude === null) return null;
          return { latitude, longitude, swapped: false };
     });

     /**
      * Re-express whatever is entered whenever the notation changes.
      *
      * This reacts to the format signal rather than to a click, because the format
      * can also be changed from the selected-location card. Handling it only in this
      * form's own button left a decimal degree sitting in a whole-degrees box.
      *
      * `fromParts` is notation-agnostic — unused fields are zero — so reading the
      * old parts after the switch still yields the right decimal value.
      */
     createEffect(
          on(
               format,
               (next, previous) => {
                    if (next === previous) return;
                    setSubmitted(false);

                    if (mode() === "paste") {
                         const parsedText = parseCoordinates(pasted());
                         if (parsedText) {
                              setPasted(
                                   next === "dd"
                                        ? formatSignedPair(
                                               parsedText.latitude,
                                               parsedText.longitude
                                          )
                                        : formatPair(
                                               parsedText.latitude,
                                               parsedText.longitude,
                                               next
                                          )
                              );
                         }
                         return;
                    }

                    const latitude = fromParts(lat(), "lat");
                    const longitude = fromParts(lng(), "lng");
                    if (latitude !== null)
                         setLat(splitAxis(latitude, "lat", next));
                    if (longitude !== null)
                         setLng(splitAxis(longitude, "lng", next));
               },
               { defer: true }
          )
     );

     function submit(event?: Event) {
          event?.preventDefault();
          setSubmitted(true);

          const coordinates = parsed();
          if (!coordinates) return;

          locationStore.select({
               latitude: coordinates.latitude,
               longitude: coordinates.longitude,
               name: null,
               origin: "coordinates",
          });
     }

     const showError = () => submitted() && !parsed();
     const touched = () =>
          mode() === "paste"
               ? pasted().trim().length > 0
               : Number.isFinite(lat().degrees) ||
                 Number.isFinite(lng().degrees);

     return (
          <form
               onSubmit={submit}
               class="rounded-card border border-line bg-paper-raised p-3 sm:p-4"
          >
               <div class="flex flex-wrap items-center justify-between gap-2">
                    <div
                         role="radiogroup"
                         aria-label="Coordinate format"
                         class="flex items-center gap-0.5 rounded-full border border-line p-0.5"
                    >
                         <For each={COORDINATE_FORMATS}>
                              {(option) => (
                                   <button
                                        type="button"
                                        role="radio"
                                        aria-checked={format() === option}
                                        title={COORDINATE_FORMAT_NAMES[option]}
                                        onClick={() =>
                                             displayStore.setCoordinateFormat(
                                                  option
                                             )
                                        }
                                        class={cn(
                                             "rounded-full px-2.5 py-1 text-[0.7rem] font-medium tracking-wide transition-colors",
                                             format() === option
                                                  ? "bg-olive-500 text-paper"
                                                  : "text-ink-faint hover:text-ink"
                                        )}
                                   >
                                        {COORDINATE_FORMAT_LABELS[option]}
                                   </button>
                              )}
                         </For>
                    </div>

                    <button
                         type="button"
                         onClick={() => {
                              setMode(mode() === "fields" ? "paste" : "fields");
                              setSubmitted(false);
                         }}
                         class="flex items-center gap-1.5 text-[0.7rem] text-ink-faint transition-colors hover:text-ink"
                    >
                         <Show
                              when={mode() === "fields"}
                              fallback={<Keyboard size={12} />}
                         >
                              <ClipboardPaste size={12} />
                         </Show>
                         {mode() === "fields"
                              ? "Paste instead"
                              : "Type in fields"}
                    </button>
               </div>

               <p class="mt-2 text-[0.7rem] text-ink-faint">
                    {COORDINATE_FORMAT_NAMES[format()]}
                    <Show when={!parsed()}>
                         <span class="tilik-figure ml-2 text-ink-soft">
                              e.g. {example()}
                         </span>
                    </Show>
               </p>

               <Show when={mode() === "paste"}>
                    <p class="mt-1 text-[0.7rem] text-ink-faint">
                         Any notation is read, including signed decimals and
                         Indonesian LS/BT.
                    </p>
               </Show>

               <Show when={mode() === "fields" && format() === "dd"}>
                    <p class="mt-1 text-[0.7rem] text-ink-faint">
                         A negative value is enough. South and west don't need
                         the toggle.
                    </p>
               </Show>

               <Show
                    when={mode() === "fields"}
                    fallback={
                         <div class="mt-2 flex items-center gap-2">
                              <input
                                   type="text"
                                   value={pasted()}
                                   autocomplete="off"
                                   spellcheck={false}
                                   aria-label="Latitude and longitude"
                                   placeholder={example()}
                                   class="tilik-figure h-10 min-w-0 flex-1 font-sans rounded-lg border border-line bg-paper px-3 text-sm text-ink placeholder:truncate placeholder:font-sans placeholder:text-ink-faint focus:border-olive-500 focus:outline-none"
                                   onInput={(event) => {
                                        setPasted(event.currentTarget.value);
                                        setSubmitted(false);
                                   }}
                              />
                              <button
                                   type="submit"
                                   disabled={!parsed()}
                                   aria-label="Use these coordinates"
                                   class="flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-olive-500 px-4 text-sm font-medium text-paper transition-colors hover:bg-olive-600 disabled:bg-ink-faint disabled:opacity-70"
                              >
                                   Go
                                   <ArrowRight size={15} />
                              </button>
                         </div>
                    }
               >
                    <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
                         <CoordinateFields
                              axis="lat"
                              label="Latitude"
                              format={format()}
                              parts={lat()}
                              invalid={submitted() && latValue() === null}
                              onChange={(patch) => {
                                   setLat({ ...lat(), ...patch });
                                   setSubmitted(false);
                              }}
                         />
                         <CoordinateFields
                              axis="lng"
                              label="Longitude"
                              format={format()}
                              parts={lng()}
                              invalid={submitted() && lngValue() === null}
                              onChange={(patch) => {
                                   setLng({ ...lng(), ...patch });
                                   setSubmitted(false);
                              }}
                         />

                         <button
                              type="submit"
                              disabled={!parsed()}
                              aria-label="Use these coordinates"
                              class="flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-olive-500 px-4 text-sm font-medium text-paper transition-colors hover:bg-olive-600 disabled:bg-ink-faint disabled:opacity-70"
                         >
                              Go
                              <ArrowRight size={15} />
                         </button>
                    </div>
               </Show>

               <div class="mt-3 border-t border-line pt-3">
                    <Show
                         when={parsed()}
                         fallback={
                              <p class="text-xs text-ink-faint">
                                   {showError() || touched()
                                        ? "Not a usable coordinate yet."
                                        : "Enter a latitude and longitude."}
                              </p>
                         }
                    >
                         {(coordinates) => (
                              <div class="min-w-0">
                                   <Show when={coordinates().swapped}>
                                        <p class="text-[0.7rem] text-khaki-700">
                                             Read as longitude first, so it's
                                             been reordered.
                                        </p>
                                   </Show>
                                   <For each={COORDINATE_FORMATS}>
                                        {(option) => (
                                             <div class="flex items-center gap-2 text-xs">
                                                  <span class="w-9 shrink-0 text-[0.65rem] font-medium text-ink-faint">
                                                       {
                                                            COORDINATE_FORMAT_LABELS[
                                                                 option
                                                            ]
                                                       }
                                                  </span>
                                                  <span class="tilik-figure min-w-0 flex-1 truncate text-ink">
                                                       {formatPair(
                                                            coordinates()
                                                                 .latitude,
                                                            coordinates()
                                                                 .longitude,
                                                            option
                                                       )}
                                                  </span>
                                                  <CopyButton
                                                       label={`Copy as ${COORDINATE_FORMAT_NAMES[option]}`}
                                                       value={formatPair(
                                                            coordinates()
                                                                 .latitude,
                                                            coordinates()
                                                                 .longitude,
                                                            option
                                                       )}
                                                  />
                                             </div>
                                        )}
                                   </For>
                              </div>
                         )}
                    </Show>
               </div>
          </form>
     );
}
