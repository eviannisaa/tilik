import type { JSX } from "solid-js";
import { Dynamic } from "solid-js/web";
import { cn } from "../../lib/cn";

interface PanelProps {
  class?: string;
  children: JSX.Element;
  as?: "div" | "section" | "article";
  /** Set while the contents are being replaced by a refetch. */
  "aria-busy"?: boolean;
}

/**
 * The only surface treatment in the app. Everything that needs separation from
 * the paper background uses this — no nested cards, no drop shadows on shadows.
 *
 * The tag is rendered through `Dynamic` because Solid compiles a capitalised
 * JSX identifier into a component call, so `<Tag>` with a string tag name would
 * blow up at runtime rather than producing an element.
 */
export default function Panel(props: PanelProps) {
  return (
    <Dynamic
      component={props.as ?? "div"}
      aria-busy={props["aria-busy"]}
      class={cn("tilik-raised rounded-card border border-line bg-paper-raised", props.class)}
    >
      {props.children}
    </Dynamic>
  );
}
