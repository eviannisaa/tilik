import MapPinOff from "lucide-solid/icons/map-pin-off";

/**
 * Shown when MapLibre never finishes starting. Searching and checking still
 * work without it, so this says that rather than pretending the app is down.
 */
export default function MapUnavailable() {
  return (
    <div class="absolute inset-0 grid place-items-center bg-paper-sunk px-6 text-center">
      <div class="max-w-xs">
        <span class="inline-flex text-ink-faint">
          <MapPinOff size={20} />
        </span>
        <p class="mt-3 text-sm font-medium text-ink">The map didn't load</p>
        <p class="mt-1 text-xs leading-relaxed text-ink-soft">
          Check your connection or the configured map style. You can still search for a
          place and check it. You just can't pick a point by tapping.
        </p>
        <button
          type="button"
          onClick={() => location.reload()}
          class="mt-4 h-8 rounded-full border border-line bg-paper-raised px-4 text-xs text-ink transition-colors hover:border-line-strong"
        >
          Reload
        </button>
      </div>
    </div>
  );
}
