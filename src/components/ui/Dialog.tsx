import { createEffect, onCleanup, type JSX } from "solid-js";
import X from "lucide-solid/icons/x";
import { cn } from "../../lib/cn";
import Button from "./Button";

interface DialogProps {
     open: boolean;
     /**
      * Called for every way out — the close button, a click on the backdrop, and
      * Escape. The last one is why this is a callback rather than a setter the
      * caller drives one way: the browser can close a dialog without asking.
      */
     onClose: () => void;
     /** Names the dialog for assistive tech. Not rendered. */
     label: string;
     children: JSX.Element;
}

/**
 * A modal built on the native element.
 *
 * `showModal()` rather than the `open` attribute: only the method puts the
 * dialog in the top layer, which is what lets it escape the sticky column's
 * stacking context and overflow, and it brings the focus trap, Escape and
 * `::backdrop` with it rather than reimplementing all three.
 *
 * The surface is the raised one `Panel` uses, and children are laid out edge to
 * edge with no padding of their own: the dialog IS the card, so content brings
 * its own gutters rather than a second card inside the first. Its own chrome is
 * one floating close button, leaving the top of the content free to be the title
 * bar.
 */
export default function Dialog(props: DialogProps) {
     let el: HTMLDialogElement | undefined;

     createEffect(() => {
          const node = el;
          if (!node) return;

          if (typeof node.showModal !== "function") {
               node.open = props.open;
               return;
          }

          if (props.open && !node.open) node.showModal();
          if (!props.open && node.open) node.close();
     });

     createEffect(() => {
          if (!props.open) return;

          const root = document.documentElement;
          const previous = root.style.overflow;
          root.style.overflow = "hidden";
          onCleanup(() => {
               root.style.overflow = previous;
          });
     });

     return (
          <dialog
               ref={el}
               aria-label={props.label}
               onClose={() => props.onClose()}
               onClick={(event) => {
                    if (event.target === el) props.onClose();
               }}
               class={cn(
                    "m-auto max-h-[90vh] w-[min(100%-2rem,69rem)] max-w-none flex-col overflow-hidden p-0 open:flex",
                    "tilik-raised rounded-card border border-line bg-paper-raised text-ink backdrop:bg-ink/50",
                    props.open && "tilik-rise"
               )}
          >
               <div class="relative z-20 flex h-0 shrink-0 justify-end">
                    <Button
                         variant="ghost"
                         quiet
                         aria-label="Close"
                         class="mt-3 mr-3 sm:mt-4 sm:mr-4 size-8! rounded-full! text-ink hover:text-olive-800 hover:bg-olive-500/10!"
                         onClick={() => props.onClose()}
                    >
                         <X
                              class="size-4! shrink-0"
                              strokeWidth={2}
                              aria-hidden="true"
                         />
                    </Button>
               </div>

               <div class="flex min-h-0 flex-1 flex-col">{props.children}</div>
          </dialog>
     );
}
