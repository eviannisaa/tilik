import { createSignal, createUniqueId, Show, type JSX } from "solid-js";
import { cn } from "../../lib/cn";

interface HoverNoteProps {
     /** The note itself. Kept short — this is an aside, not a paragraph. */
     note: string;
     /** What the reader points at. */
     children: JSX.Element;
     /** Anchor the panel to the trigger's right edge instead of its left. */
     align?: "left" | "right";
     class?: string;
}

/**
 * A short note attached to a phrase, shown on hover, focus or tap.
 *
 * This exists because `title` does not work. The attribute renders, but the
 * browser waits about a second before drawing anything, gives the reader no
 * sign that a 12 px icon is even hoverable, truncates long text on some
 * platforms, and on a touch screen never fires at all — so a caveat moved into
 * a `title` is a caveat effectively deleted.
 *
 * Opening on `click` as well as hover is what makes it reachable on a phone,
 * and `focus` is what makes it reachable from a keyboard. `aria-describedby`
 * ties the note to its trigger so a screen reader announces it either way.
 */
export default function HoverNote(props: HoverNoteProps) {
     const [open, setOpen] = createSignal(false);
     const id = createUniqueId();

     return (
          <span
               class="relative inline-flex"
               onMouseEnter={() => setOpen(true)}
               onMouseLeave={() => setOpen(false)}
          >
               <button
                    type="button"
                    aria-describedby={open() ? id : undefined}
                    aria-expanded={open()}
                    onFocus={() => setOpen(true)}
                    onBlur={() => setOpen(false)}
                    onClick={() => setOpen(!open())}
                    onKeyDown={(event) =>
                         event.key === "Escape" && setOpen(false)
                    }
                    class={cn(
                         "inline-flex cursor-help items-center gap-1 rounded text-left",
                         "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-olive-500",
                         props.class
                    )}
               >
                    {props.children}
               </button>

               <Show when={open()}>
                    <span
                         id={id}
                         role="tooltip"
                         class={cn(
                              "tilik-raised absolute bottom-full z-30 mb-1.5 w-64 rounded-lg border",
                              "border-line bg-paper-raised px-3 py-2 text-left text-xs font-normal",
                              "leading-relaxed text-ink-soft",
                              props.align === "right" ? "right-0" : "left-0"
                         )}
                    >
                         {props.note}
                    </span>
               </Show>
          </span>
     );
}
