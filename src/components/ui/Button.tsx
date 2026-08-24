import { splitProps, type JSX } from "solid-js";
import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends JSX.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /**
   * The document-style treatment: no lift shadow, and a crisp radius instead of
   * a pill. For a surface that already separates itself from the paper, where a
   * raised, fully-rounded button would be the only thing casting light on it.
   */
  quiet?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary: "bg-olive-500 text-paper hover:bg-olive-600 active:bg-olive-700 disabled:bg-ink-faint",
  secondary:
    "tilik-raised bg-paper-raised text-ink border border-line hover:border-line-strong hover:bg-paper-sunk",
  ghost: "text-ink-soft hover:text-ink hover:bg-paper-sunk",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-5 text-[0.95rem] gap-2.5",
};

export default function Button(props: ButtonProps) {
  const [local, rest] = splitProps(props, [
    "variant",
    "size",
    "loading",
    "quiet",
    "class",
    "children",
  ]);

  const lifted = () => (local.variant ?? "primary") === "primary" && !local.quiet;

  return (
    <button
      {...rest}
      class={cn(
        "inline-flex items-center justify-center font-medium tracking-tight",
        local.quiet ? "rounded-lg" : "rounded-full",
        "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-70",
        VARIANTS[local.variant ?? "primary"],
        lifted() && "shadow-lift",
        SIZES[local.size ?? "md"],
        local.class,
      )}
      disabled={rest.disabled || local.loading}
      aria-busy={local.loading}
    >
      {local.loading ? (
        <span
          class="size-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden="true"
        />
      ) : null}
      {local.children}
    </button>
  );
}
