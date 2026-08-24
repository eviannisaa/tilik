import { cn } from "../../lib/cn";

interface SkeletonProps {
  class?: string;
  /** Rendered as a wide bar by default; pass `w-…`/`h-…` to reshape. */
  rounded?: "sm" | "full";
}

/**
 * A quiet placeholder. One sweep, no pulsing — the page should look like it is
 * settling, not flashing.
 */
export default function Skeleton(props: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      class={cn(
        "relative block h-4 w-full overflow-hidden bg-paper-sunk",
        props.rounded === "full" ? "rounded-full" : "rounded-md",
        "after:absolute after:inset-0 after:-translate-x-full after:animate-[tilik-shimmer_1.6s_infinite]",
        "after:bg-gradient-to-r after:from-transparent after:via-white/70 after:to-transparent",
        props.class,
      )}
    />
  );
}
