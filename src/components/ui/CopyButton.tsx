import { createSignal, Show } from "solid-js";
import Check from "lucide-solid/icons/check";
import Copy from "lucide-solid/icons/copy";
import { cn } from "../../lib/cn";

/** Copies a string, confirming briefly so the click doesn't feel inert. */
export default function CopyButton(props: {
     value: string;
     label: string;
     class?: string;
}) {
     const [copied, setCopied] = createSignal(false);

     async function copy() {
          try {
               await navigator.clipboard.writeText(props.value);
               setCopied(true);
               setTimeout(() => setCopied(false), 1600);
          } catch {
               // Clipboard access can be refused; the text is on screen to select.
          }
     }

     return (
          <button
               type="button"
               onClick={copy}
               aria-label={props.label}
               class={cn(
                    "inline-flex items-center gap-1 rounded-full px-1 py-1 text-[0.7rem] transition-colors",
                    copied()
                         ? "text-olive-600"
                         : "text-ink-faint hover:text-ink",
                    props.class
               )}
          >
               <Show when={copied()} fallback={<Copy size={12} />}>
                    <Check size={12} />
               </Show>
               {copied() ? "Copied" : "Copy"}
          </button>
     );
}
