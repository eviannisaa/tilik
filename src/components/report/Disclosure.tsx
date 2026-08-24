import type { JSX } from "solid-js";
import ChevronDown from "lucide-solid/icons/chevron-down";
import { cn } from "../../lib/cn";

/**
 * Reference material that shouldn't cost vertical space on every read.
 *
 * A native `<details>`: it's keyboard accessible, findable by in-page search in
 * most browsers, and needs no state of its own.
 */
export default function Disclosure(props: {
     /** Takes markup as well as a string: a row of these needs its own layout. */
     summary: JSX.Element;
     children: JSX.Element;
     /** Overrides the wrapper spacing. A stack of these wants it tighter. */
     class?: string;
     /** Overrides the summary's own type styling. */
     summaryClass?: string;
}) {
     return (
          <details class={cn("group", props.class ?? "mt-4")}>
               <summary
                    class={cn(
                         "flex cursor-pointer list-none items-center gap-1.5 transition-colors [&::-webkit-details-marker]:hidden",
                         props.summaryClass ?? "text-xs text-ink-faint hover:text-ink",
                    )}
               >
                    <span class="shrink-0 transition-transform group-open:rotate-180">
                         <ChevronDown size={13} />
                    </span>
                    {props.summary}
               </summary>
               <div class="mt-3">{props.children}</div>
          </details>
     );
}
