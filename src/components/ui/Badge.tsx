import type { JSX } from "solid-js";
import { cn } from "../../lib/cn";

type Tone = "neutral" | "olive" | "khaki" | "clay" | "amber" | "red" | "green";

const TONES: Record<Tone, string> = {
     neutral: "bg-paper-sunk text-ink-soft border-line",
     olive: "bg-olive-50 text-olive-700 border-olive-200",
     khaki: "bg-khaki-50 text-khaki-700 border-khaki-200",
     clay: "bg-clay-50 text-clay-700 border-clay-200",
     amber: "bg-amber-100 text-amber-600 border-amber-600",
     green: "bg-green-100 text-green-700 border-green-700",
     red: "bg-red-200 text-red-700 border-red-800",
};

interface BadgeProps {
     tone?: Tone;
     class?: string;
     children: JSX.Element;
}

export default function Badge(props: BadgeProps) {
     return (
          <span
               class={cn(
                    // Same size as the confidence chips it sits beside in a report section.
                    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 capitalize font-semibold text-xs",
                    TONES[props.tone ?? "neutral"],
                    props.class
               )}
          >
               {props.children}
          </span>
     );
}
