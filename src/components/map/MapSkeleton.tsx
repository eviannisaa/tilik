/**
 * Shown until MapLibre reports `load`. A faint graticule reads as "a map is
 * coming" without a spinner.
 */
export default function MapSkeleton() {
  return (
    <div class="absolute inset-0 grid place-items-center bg-paper-sunk" aria-hidden="true">
      <svg class="absolute inset-0 h-full w-full text-line-strong" preserveAspectRatio="none">
        <defs>
          <pattern id="tilik-grid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M48 0H0V48" fill="none" stroke="currentColor" stroke-width="1" opacity="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#tilik-grid)" />
      </svg>
      <span class="tilik-raised relative rounded-full border border-line bg-paper-raised px-3 py-1.5 text-xs text-ink-soft">
        Loading map…
      </span>
    </div>
  );
}
