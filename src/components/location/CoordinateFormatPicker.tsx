import { For } from "solid-js";
import { cn } from "../../lib/cn";
import {
  COORDINATE_FORMATS,
  COORDINATE_FORMAT_LABELS,
  COORDINATE_FORMAT_NAMES,
} from "../../lib/coordinates";
import { displayStore } from "../../lib/store";

/** Switches the notation every coordinate readout uses. */
export default function CoordinateFormatPicker(props: { class?: string }) {
  return (
    <div
      role="radiogroup"
      aria-label="Coordinate format"
      class={cn("flex items-center gap-0.5 rounded-full border border-line p-0.5", props.class)}
    >
      <For each={COORDINATE_FORMATS}>
        {(format) => (
          <button
            type="button"
            role="radio"
            aria-checked={displayStore.coordinateFormat() === format}
            title={COORDINATE_FORMAT_NAMES[format]}
            onClick={() => displayStore.setCoordinateFormat(format)}
            class={cn(
              "rounded-full px-2 py-0.5 text-[0.65rem] font-medium tracking-wide transition-colors",
              displayStore.coordinateFormat() === format
                ? "bg-olive-500 text-paper"
                : "text-ink-faint hover:text-ink",
            )}
          >
            {COORDINATE_FORMAT_LABELS[format]}
          </button>
        )}
      </For>
    </div>
  );
}
