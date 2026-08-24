import type { JSX } from "solid-js";
import { Show } from "solid-js";
import TriangleAlert from "lucide-solid/icons/triangle-alert";
import Info from "lucide-solid/icons/info";
import { cn } from "../../lib/cn";

interface InlineAlertProps {
  tone?: "warning" | "info";
  title?: string;
  children: JSX.Element;
  action?: JSX.Element;
  class?: string;
}

/** Non-blocking notice used for degraded data and recoverable failures. */
export default function InlineAlert(props: InlineAlertProps) {
  const tone = () => props.tone ?? "info";

  return (
    <div
      role={tone() === "warning" ? "alert" : "status"}
      class={cn(
        "flex items-start gap-3 rounded-xl border px-3.5 py-3 text-sm",
        tone() === "warning"
          ? "border-clay-200 bg-clay-50 text-clay-700"
          : "border-line bg-paper-sunk text-ink-soft",
        props.class,
      )}
    >
      <span class="mt-0.5 shrink-0">
        {tone() === "warning" ? <TriangleAlert size={16} /> : <Info size={16} />}
      </span>
      <div class="min-w-0 flex-1 leading-relaxed">
        <Show when={props.title}>
          <p class="font-medium text-ink">{props.title}</p>
        </Show>
        <div class={props.title ? "mt-0.5" : undefined}>{props.children}</div>
      </div>
      <Show when={props.action}>
        <div class="shrink-0">{props.action}</div>
      </Show>
    </div>
  );
}
