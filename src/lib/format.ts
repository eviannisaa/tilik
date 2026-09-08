/** Small display helpers shared by the report UI. */

export function formatCoordinate(value: number, axis: "lat" | "lng"): string {
  const hemisphere =
    axis === "lat" ? (value >= 0 ? "N" : "S") : value >= 0 ? "E" : "W";
  return `${Math.abs(value).toFixed(5)}° ${hemisphere}`;
}

export function formatDecimal(value: number, digits = 5): string {
  return value.toFixed(digits);
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return "—";
  if (meters < 1000) return `${Math.round(meters)} m`;
  if (meters < 10_000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters / 1000)} km`;
}

export function formatElevation(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return "—";
  return `${Math.round(meters)} m`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Date unknown";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Date unknown";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function relativeYears(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const years = (Date.now() - date.getTime()) / (365.25 * 24 * 3600 * 1000);
  if (years < 1) return "within the last year";
  return `${Math.round(years)} yr ago`;
}

/**
 * Short relative age for recent items. News is read for recency — "2 days ago"
 * answers "is this still happening?" in a way a calendar date doesn't.
 */
export function relativeDays(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days < 0) return null;
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;

  const months = Math.round(days / 30);
  if (months < 12) return `${months} mo ago`;
  return "over a year ago";
}

/**
 * Age of a reading that is only meaningful while it is fresh.
 *
 * `relativeDays` answers "is this still happening?" for a news story, and for
 * that it is right. An air-quality index is an hour of one day: read through
 * `relativeDays`, a measurement taken at 3am and one taken ten minutes ago both
 * render as "today", under a heading that promises what the air is doing right
 * now. Below a day this reports the hour instead, and above it hands back to
 * `relativeDays`, because a stale reading's exact hour stops mattering.
 */
export function relativeHours(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes < 0) return null;
  if (minutes < 60) return "within the hour";

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return relativeDays(iso);
}

/**
 * Modified Mercalli degree → its wording, as one consistent ladder.
 *
 * USGS's own words mix registers: "weak, light, moderate" leaves a reader
 * guessing whether light is milder than weak, and "severe, violent, extreme"
 * is three near-synonyms in a row. These stay on a single "strong" family with
 * modifiers, so the order reads without having to be memorised.
 *
 * The *degrees* are unchanged. MMI VI officially means Strong, so moving that
 * word down to V would have the report overstate what the ground did — the
 * wording is replaced, never repositioned. Only the top of the scale leaves the
 * family, because nothing sits naturally above "extremely strong".
 */
const MMI_LABELS: readonly [number, string][] = [
  [1, "not felt"],
  [2, "weak"],
  [4, "moderate"],
  [5, "moderately strong"],
  [6, "strong"],
  [7, "very strong"],
  [8, "extremely strong"],
  [9, "violent"],
  [10, "extreme"],
];

const ROMAN = [
  "",
  "I",
  "II",
  "III",
  "IV",
  "V",
  "VI",
  "VII",
  "VIII",
  "IX",
  "X",
  "XI",
  "XII",
];

/**
 * Shaking intensity, as a degree plus its plain meaning — "VI (strong)".
 *
 * This is the figure a reader can act on. Magnitude describes energy released
 * at the source, which is why a magnitude 4.5 can be a non-event 194 km down
 * and a damaging quake at 10 km; intensity describes what the ground actually
 * did at a place, on a scale defined by observable effects.
 */
export function formatIntensity(mmi: number | null | undefined): string | null {
  if (mmi === null || mmi === undefined) return null;
  const degree = Math.max(1, Math.min(12, Math.round(mmi)));
  let label = MMI_LABELS[0]![1];
  for (const [threshold, wording] of MMI_LABELS) {
    if (degree >= threshold) label = wording;
  }
  return `${ROMAN[degree]} (${label})`;
}

/**
 * Magnitude with its scale spelled out, or bare when the source named no scale.
 *
 * The scale has to travel with the number: a BMKG bulletin and a USGS bulletin
 * for the same earthquake print different values, and neither is wrong.
 */
export function formatMagnitude(
  magnitude: number | null | undefined,
  scale: string | null | undefined,
): string | null {
  if (magnitude === null || magnitude === undefined) return null;
  // "m" means the provider published no scale, so there is nothing to label.
  const suffix = scale && scale !== "m" && scale !== "other" ? ` ${scale}` : "";
  return `M ${magnitude}${suffix}`;
}

/**
 * The human cost, as the source counted it — "12 deaths · 4,600 displaced".
 *
 * Only figures above zero are listed. A reported zero is real information but
 * not worth a row here, and a `null` means nothing was published at all.
 */
export function formatImpact(
  impact: {
    deaths: number | null;
    missing: number | null;
    injured: number | null;
    displaced: number | null;
    housesDestroyed: number | null;
    housesDamaged: number | null;
  } | null,
): string | null {
  if (!impact) return null;

  const parts: string[] = [];
  /** `singular` is given only where the noun inflects — "1 deaths" read as a bug. */
  const add = (value: number | null, plural: string, singular = plural) => {
    if (value === null || value <= 0) return;
    parts.push(`${value.toLocaleString()} ${value === 1 ? singular : plural}`);
  };

  add(impact.deaths, "deaths", "death");
  add(impact.missing, "missing");
  add(impact.injured, "injured");
  add(impact.displaced, "displaced");
  add(impact.housesDestroyed, "houses destroyed", "house destroyed");
  add(impact.housesDamaged, "houses damaged", "house damaged");

  return parts.length ? parts.join(" · ") : null;
}

export function titleCase(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word[0]!.toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

/**
 * The administrative chain below a place name, smallest first.
 *
 * Nominatim does not use one key per Indonesian level. Around Tangerang the
 * kecamatan arrives as `district` and the kota as `city`, which reads correctly;
 * in Palu the two are swapped, so `district` holds "Palu" (the kota) and `city`
 * holds "Kecamatan Palu Timur". Printing the fields in a fixed order gets Palu
 * exactly backwards.
 *
 * Where the value carries its own Indonesian prefix, that prefix is the answer:
 * "Kecamatan X" is a kecamatan whatever key it arrived under, and "Kabupaten" or
 * "Kota" marks the level above it. Those are sorted into place; anything
 * unlabelled keeps the order the geocoder gave, which is right more often than
 * not. Repeats are dropped, because Palu appears as both locality and district.
 */
export function adminChain(location: {
  district?: string | null;
  city?: string | null;
  province?: string | null;
}): string[] {
  /**
   * Lower sorts first. A value that names its own level always beats one that
   * only has its key to go on, which is why the two scales do not overlap: in
   * Palu the unlabelled "Palu" arrives under `district` and would otherwise tie
   * with the explicit "Kecamatan Palu Timur" and win on stable-sort order.
   */
  const rank = (value: string, fallback: number): number => {
    if (/^kecamatan\b/i.test(value)) return 0;
    if (/^(kabupaten|kota)\b/i.test(value)) return 1;
    return fallback + 0.5;
  };

  const seen = new Set<string>();
  return [
    { value: location.district, fallback: 0 },
    { value: location.city, fallback: 1 },
    { value: location.province, fallback: 2 },
  ]
    .flatMap(({ value, fallback }) => {
      const trimmed = value?.trim();
      if (!trimmed) return [];
      const key = trimmed.toLowerCase();
      if (seen.has(key)) return [];
      seen.add(key);
      return [{ value: trimmed, rank: rank(trimmed, fallback) }];
    })
    .sort((a, b) => a.rank - b.rank)
    .map((entry) => entry.value);
}
