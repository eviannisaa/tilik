import { For, Show } from "solid-js";
import { cn } from "../../lib/cn";
import { examplePlaceholders } from "../../lib/coordinates";
import type { AxisParts, CoordinateFormat } from "../../lib/coordinates";

type Axis = "lat" | "lng";

const HEMISPHERES: Record<Axis, [string, string]> = {
     lat: ["N", "S"],
     lng: ["E", "W"],
};

interface FieldsProps {
     axis: Axis;
     label: string;
     format: CoordinateFormat;
     parts: AxisParts;
     invalid: boolean;
     onChange: (patch: Partial<AxisParts>) => void;
}

const box =
     "tilik-figure h-10 rounded-lg border bg-paper-raised px-1.5 text-center text-sm text-ink " +
     "placeholder:text-ink-faint/60 " +
     "focus:outline-none focus:border-olive-500 [appearance:textfield] " +
     "[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";

/** One axis of a structured coordinate entry, shaped to the chosen notation. */
export default function CoordinateFields(props: FieldsProps) {
     const border = () => (props.invalid ? "border-clay-500" : "border-line");
     const hint = () => examplePlaceholders(props.axis, props.format);

     const signed = () => props.format === "dd";

     const [positive, negative] = HEMISPHERES[props.axis];

     /**
      * Which hemisphere button reads as active.
      *
      * In DD the sign is the source of truth, so the buttons reflect it rather than
      * holding separate state that could disagree with the number on screen.
      */
     const active = () => {
          if (!signed()) return props.parts.hemisphere;
          if (!Number.isFinite(props.parts.degrees))
               return props.parts.hemisphere;
          return props.parts.degrees < 0 ? negative : positive;
     };

     /** Clicking a hemisphere sets the sign in DD, or just the marker elsewhere. */
     function chooseHemisphere(letter: string) {
          if (!signed() || !Number.isFinite(props.parts.degrees)) {
               props.onChange({ hemisphere: letter });
               return;
          }

          const magnitude = Math.abs(props.parts.degrees);
          props.onChange({
               hemisphere: letter,
               degrees: letter === negative ? -magnitude : magnitude,
          });
     }

     const numeric = (value: string) =>
          value === "" ? Number.NaN : Number(value);

     return (
          <div class="flex shrink-0 items-center gap-1.5">
               <span class="text-[0.7rem] font-medium text-ink-soft">
                    {props.label}
               </span>

               <div class="flex items-center gap-1">
                    <input
                         type="number"
                         inputmode="decimal"
                         step={signed() ? "0.00001" : "1"}
                         min={
                              signed()
                                   ? props.axis === "lat"
                                        ? "-90"
                                        : "-180"
                                   : "0"
                         }
                         max={props.axis === "lat" ? "90" : "180"}
                         aria-label={`${props.label} degrees`}
                         placeholder={hint().degrees}
                         value={
                              Number.isFinite(props.parts.degrees)
                                   ? props.parts.degrees
                                   : ""
                         }
                         onInput={(event) =>
                              props.onChange({
                                   degrees: numeric(event.currentTarget.value),
                              })
                         }
                         class={cn(
                              box,
                              border(),
                              props.format === "dd" ? "w-[6.5rem]" : "w-12"
                         )}
                    />
                    <span class="text-xs text-ink-faint">°</span>

                    <Show when={props.format !== "dd"}>
                         <input
                              type="number"
                              inputmode="decimal"
                              step={props.format === "ddm" ? "0.0001" : "1"}
                              min="0"
                              max="59.9999"
                              aria-label={`${props.label} minutes`}
                              placeholder={hint().minutes}
                              value={
                                   Number.isFinite(props.parts.minutes)
                                        ? props.parts.minutes
                                        : ""
                              }
                              onInput={(event) =>
                                   props.onChange({
                                        minutes: numeric(
                                             event.currentTarget.value
                                        ),
                                   })
                              }
                              class={cn(
                                   box,
                                   border(),
                                   props.format === "ddm"
                                        ? "w-[5.25rem]"
                                        : "w-12"
                              )}
                         />
                         <span class="text-xs text-ink-faint">'</span>
                    </Show>

                    <Show when={props.format === "dms"}>
                         <input
                              type="number"
                              inputmode="decimal"
                              step="0.01"
                              min="0"
                              max="59.99"
                              aria-label={`${props.label} seconds`}
                              placeholder={hint().seconds}
                              value={
                                   Number.isFinite(props.parts.seconds)
                                        ? props.parts.seconds
                                        : ""
                              }
                              onInput={(event) =>
                                   props.onChange({
                                        seconds: numeric(
                                             event.currentTarget.value
                                        ),
                                   })
                              }
                              class={cn(box, border(), "w-16")}
                         />
                         <span class="text-xs text-ink-faint">"</span>
                    </Show>
               </div>

               <div
                    role="radiogroup"
                    aria-label={`${props.label} hemisphere`}
                    title={
                         signed() ? "Or just type a negative value" : undefined
                    }
                    class="flex shrink-0 items-center gap-0.5 rounded-lg border border-line p-0.5"
               >
                    <For each={HEMISPHERES[props.axis]}>
                         {(letter) => (
                              <button
                                   type="button"
                                   role="radio"
                                   aria-checked={active() === letter}
                                   onClick={() => chooseHemisphere(letter)}
                                   class={cn(
                                        "h-8 w-7 rounded-md text-xs font-medium transition-colors",
                                        active() === letter
                                             ? "bg-olive-500 text-paper"
                                             : "text-ink-faint hover:text-ink"
                                   )}
                              >
                                   {letter}
                              </button>
                         )}
                    </For>
               </div>
          </div>
     );
}
