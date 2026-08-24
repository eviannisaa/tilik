/**
 * Parsing coordinates that people actually paste.
 *
 * Sources vary wildly: Google Maps gives `-6.9175, 107.6191`, GPS apps give
 * degrees-minutes-seconds, and this app's own readout gives
 * `3.83359° N·96.85162° E` — which has to round-trip, since copying a value out
 * of the report and back in is the obvious thing to try.
 */

export interface ParsedCoordinates {
  latitude: number;
  longitude: number;
  /**
   * True when the input read as longitude-first and was reordered. Common when
   * pasting from GeoJSON or a WKT point, so it's corrected and surfaced rather
   * than rejected.
   */
  swapped: boolean;
}

/**
 * One coordinate component: an optional leading hemisphere, a signed degree
 * value, optional minutes and seconds, and an optional trailing hemisphere.
 */
const COMPONENT =
  /(?:([NSEW])\s*)?([+-]?\d+(?:\.\d+)?)\s*(?:°|º|deg)?\s*(?:(\d+(?:\.\d+)?)\s*['′’]\s*)?(?:(\d+(?:\.\d+)?)\s*(?:"|″|”|'')\s*)?\s*([NSEW])?/gi;

interface Component {
  value: number;
  /** `lat`, `lng`, or null when no hemisphere letter was given. */
  axis: "lat" | "lng" | null;
}

/**
 * Indonesian hemisphere markers, mapped onto the letters the parser works in.
 *
 * LU/LS = Lintang Utara/Selatan (north/south latitude), BT/BB = Bujur
 * Timur/Barat (east/west longitude). Leaving these unhandled was worse than
 * failing: `35° LS` parsed as +35 rather than −35, silently moving the point
 * into the wrong hemisphere.
 */
const INDONESIAN_MARKERS: ReadonlyArray<[RegExp, string]> = [
  [/\blintang\s+utara\b/gi, "N"],
  [/\blintang\s+selatan\b/gi, "S"],
  [/\bbujur\s+timur\b/gi, "E"],
  [/\bbujur\s+barat\b/gi, "W"],
  [/\bLU\b/gi, "N"],
  [/\bLS\b/gi, "S"],
  [/\bBT\b/gi, "E"],
  [/\bBB\b/gi, "W"],
];

function normaliseMarkers(input: string): string {
  let output = input;
  for (const [pattern, letter] of INDONESIAN_MARKERS) {
    output = output.replace(pattern, letter);
  }
  return output;
}

function hemisphereAxis(letter: string | undefined): "lat" | "lng" | null {
  if (!letter) return null;
  return /[NS]/i.test(letter) ? "lat" : "lng";
}

function hemisphereSign(letter: string | undefined): number {
  if (!letter) return 1;
  return /[SW]/i.test(letter) ? -1 : 1;
}

function readComponents(input: string): Component[] {
  const components: Component[] = [];

  // Reset lastIndex: the regex is module-level and stateful with /g.
  COMPONENT.lastIndex = 0;

  for (const match of input.matchAll(COMPONENT)) {
    const [, leading, degrees, minutes, seconds, trailing] = match;
    if (degrees === undefined) continue;

    const letter = leading ?? trailing;
    const magnitude =
      Math.abs(Number(degrees)) + Number(minutes ?? 0) / 60 + Number(seconds ?? 0) / 3600;

    // An explicit minus and a S/W letter mean the same thing; either is enough.
    const negative = degrees.startsWith("-") || hemisphereSign(letter) < 0;

    components.push({
      value: negative ? -magnitude : magnitude,
      axis: hemisphereAxis(letter),
    });

    if (components.length === 2) break;
  }

  return components;
}

const inLatRange = (value: number) => value >= -90 && value <= 90;
const inLngRange = (value: number) => value >= -180 && value <= 180;

/**
 * Parse a coordinate string. Returns `null` when it isn't a usable pair.
 */
export function parseCoordinates(input: string): ParsedCoordinates | null {
  if (!input) return null;

  // `·` is this app's own separator; the rest are common paste artefacts.
  const base = normaliseMarkers(input)
    .replace(/[·|/\\]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!base) return null;

  // Indonesian and most European locales write decimals with a comma, which
  // collides with comma-as-separator. Only try that reading when there's no dot
  // acting as a decimal point, and fall back if it doesn't produce a pair — so a
  // guess can never beat an interpretation that actually works.
  const readings = [base];
  if (!base.includes(".") && /\d\s*,\s*\d/.test(base)) {
    readings.unshift(base.replace(/(\d)\s*,\s*(\d)/g, "$1.$2"));
  }

  for (const reading of readings) {
    const parsed = interpret(reading);
    if (parsed) return parsed;
  }
  return null;
}

function interpret(normalised: string): ParsedCoordinates | null {
  const components = readComponents(normalised);
  if (components.length < 2) return null;

  const [first, second] = components as [Component, Component];
  if (!Number.isFinite(first.value) || !Number.isFinite(second.value)) return null;

  // Hemisphere letters are authoritative about which axis is which.
  if (first.axis === "lng" && second.axis === "lat") {
    return finalise(second.value, first.value, true);
  }
  if (first.axis === "lat" || second.axis === "lng") {
    return finalise(first.value, second.value, false);
  }

  // No letters: assume latitude first, but reorder if that can't be true and
  // the reverse can — pasting `lng, lat` is a common mistake.
  if (!inLatRange(first.value) && inLatRange(second.value) && inLngRange(first.value)) {
    return finalise(second.value, first.value, true);
  }

  return finalise(first.value, second.value, false);
}

function finalise(
  latitude: number,
  longitude: number,
  swapped: boolean,
): ParsedCoordinates | null {
  if (!inLatRange(latitude) || !inLngRange(longitude)) return null;
  // Round to ~11 cm, the most any of these sources meaningfully carries.
  return {
    latitude: Number(latitude.toFixed(6)),
    longitude: Number(longitude.toFixed(6)),
    swapped,
  };
}

/** `true` when the input looks like an attempt at coordinates, valid or not.
 *
 * Used to decide whether to offer a coordinate jump instead of waiting on the
 * geocoder, so it only has to separate "numbers and unit symbols" from
 * "a place name".
 */
export function looksLikeCoordinates(input: string): boolean {
  const trimmed = input.trim();
  if (trimmed.length < 3) return false;

  // Only digits, separators, unit symbols and hemisphere markers — including
  // the Indonesian LU/LS/BT/BB, whose letters would otherwise look like a name.
  if (!/^[NSEWnsewLUBTlubt\d\s.,;:+°º'"′″’”·|/\\-]+$/.test(trimmed)) return false;

  const numbers = normaliseMarkers(trimmed).match(/\d+(?:[.,]\d+)?/g) ?? [];
  return numbers.length >= 2;
}

/* -------------------------------------------------------------------------- */
/*  Formatting                                                                */
/* -------------------------------------------------------------------------- */

/**
 * The three notations the same point gets written in. Land certificates tend to
 * use DMS, handheld GPS units DDM, and web maps DD — so a coordinate often has
 * to be read in one and quoted in another.
 */
export type CoordinateFormat = "dd" | "ddm" | "dms";

export const COORDINATE_FORMATS: readonly CoordinateFormat[] = ["dd", "ddm", "dms"];

export const COORDINATE_FORMAT_LABELS: Record<CoordinateFormat, string> = {
  dd: "DD",
  ddm: "DDM",
  dms: "DMS",
};

export const COORDINATE_FORMAT_NAMES: Record<CoordinateFormat, string> = {
  dd: "Decimal degrees",
  ddm: "Degrees and decimal minutes",
  dms: "Degrees, minutes, seconds",
};

//: Chosen so a value survives a round trip through text at ~0.2 m or better.
const MINUTE_DECIMALS = 4;
const SECOND_DECIMALS = 2;

type Axis = "lat" | "lng";

function hemisphere(value: number, axis: Axis): string {
  if (axis === "lat") return value >= 0 ? "N" : "S";
  return value >= 0 ? "E" : "W";
}

/**
 * Split a magnitude into degrees/minutes/seconds, rounding at the requested
 * precision and carrying upwards.
 *
 * Rounding has to happen before the carry, or 6.99999992° prints as
 * `6° 59' 60.00"` instead of `7° 0' 0.00"`.
 */
export interface AxisParts {
  degrees: number;
  minutes: number;
  seconds: number;
  /** N/S for latitude, E/W for longitude. */
  hemisphere: string;
}

/** Split a signed value into the fields a structured input needs.
 *
 * In DD the whole magnitude belongs in `degrees` — a decimal-degrees form has
 * one box per axis, not three.
 */
export function splitAxis(value: number, axis: Axis, format: CoordinateFormat): AxisParts {
  const marker = hemisphere(value, axis);
  const magnitude = Math.abs(value);

  if (format === "dd") {
    // Signed, because decimal degrees are conventionally written `-6.9175` and
    // that's what people paste. DDM and DMS always spell the hemisphere out.
    return { degrees: Number(value.toFixed(6)), minutes: 0, seconds: 0, hemisphere: marker };
  }

  const { degrees, minutes, seconds } = toParts(magnitude, format);
  return { degrees, minutes, seconds, hemisphere: marker };
}

/**
 * Rebuild a signed decimal degree from structured fields.
 *
 * Returns `null` when the parts can't describe a real coordinate, so a
 * half-typed form doesn't produce a plausible-looking wrong point.
 */
export function fromParts(parts: AxisParts, axis: Axis): number | null {
  const { degrees, minutes, seconds, hemisphere: marker } = parts;

  if (![degrees, minutes, seconds].every(Number.isFinite)) return null;
  // Only degrees may be signed; a negative minute or second is meaningless.
  if (minutes < 0 || seconds < 0) return null;
  if (minutes >= 60 || seconds >= 60) return null;

  const magnitude = Math.abs(degrees) + minutes / 60 + seconds / 3600;
  const limit = axis === "lat" ? 90 : 180;
  if (magnitude > limit) return null;

  // A leading minus and a S/W marker mean the same thing, and either is enough —
  // the same rule the string parser uses, so both entry paths agree.
  const negative = degrees < 0 || /[SW]/i.test(marker);
  return Number((negative ? -magnitude : magnitude).toFixed(6));
}

function toParts(magnitude: number, format: CoordinateFormat) {
  let degrees = Math.floor(magnitude);
  let minutes = (magnitude - degrees) * 60;

  if (format === "ddm") {
    minutes = Number(minutes.toFixed(MINUTE_DECIMALS));
    if (minutes >= 60) {
      minutes -= 60;
      degrees += 1;
    }
    return { degrees, minutes, seconds: 0 };
  }

  let wholeMinutes = Math.floor(minutes);
  let seconds = Number(((minutes - wholeMinutes) * 60).toFixed(SECOND_DECIMALS));

  if (seconds >= 60) {
    seconds -= 60;
    wholeMinutes += 1;
  }
  if (wholeMinutes >= 60) {
    wholeMinutes -= 60;
    degrees += 1;
  }

  return { degrees, minutes: wholeMinutes, seconds };
}

/** Format one axis of a coordinate in the requested notation. */
export function formatAxis(value: number, axis: Axis, format: CoordinateFormat): string {
  const suffix = hemisphere(value, axis);
  const magnitude = Math.abs(value);

  if (format === "dd") {
    return `${magnitude.toFixed(5)}° ${suffix}`;
  }

  const { degrees, minutes, seconds } = toParts(magnitude, format);

  if (format === "ddm") {
    return `${degrees}° ${minutes.toFixed(MINUTE_DECIMALS)}' ${suffix}`;
  }

  return `${degrees}° ${minutes}' ${seconds.toFixed(SECOND_DECIMALS)}" ${suffix}`;
}

/** Format a full pair, e.g. `6° 55' 3.00" S · 107° 37' 8.76" E`. */
export function formatPair(
  latitude: number,
  longitude: number,
  format: CoordinateFormat,
): string {
  return `${formatAxis(latitude, "lat", format)} · ${formatAxis(longitude, "lng", format)}`;
}

/* -------------------------------------------------------------------------- */
/*  Examples                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * The point every placeholder is built from — Bandung, which exercises a
 * southern latitude and an eastern longitude, so hemisphere markers show up.
 */
export const EXAMPLE_POINT = { latitude: -6.9175, longitude: 107.6191 } as const;

/**
 * A full example pair in the given notation.
 *
 * Generated by the same formatters the app renders with, rather than written out
 * by hand, so a placeholder can never drift from what the parser accepts — the
 * tests assert each one parses back to `EXAMPLE_POINT`.
 */
export function examplePair(format: CoordinateFormat): string {
  return formatPair(EXAMPLE_POINT.latitude, EXAMPLE_POINT.longitude, format);
}

/**
 * A signed decimal pair, e.g. `-6.91750, 107.61910`.
 *
 * The form decimal degrees usually arrive in — Google Maps, GeoJSON, most APIs —
 * so it's what the DD paste hint shows.
 */
export function formatSignedPair(latitude: number, longitude: number): string {
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

/** Example field values for one axis, matching a structured form's boxes. */
export function exampleParts(axis: Axis, format: CoordinateFormat): AxisParts {
  const value = axis === "lat" ? EXAMPLE_POINT.latitude : EXAMPLE_POINT.longitude;
  return splitAxis(value, axis, format);
}

/** How each field should read as placeholder text, padded like a real entry. */
export function examplePlaceholders(
  axis: Axis,
  format: CoordinateFormat,
): { degrees: string; minutes: string; seconds: string } {
  const parts = exampleParts(axis, format);
  return {
    // DD keeps its sign in the hint, since that's how it's typed.
    degrees: format === "dd" ? parts.degrees.toFixed(5) : String(Math.abs(parts.degrees)),
    minutes: format === "ddm" ? parts.minutes.toFixed(MINUTE_DECIMALS) : String(parts.minutes),
    seconds: parts.seconds.toFixed(SECOND_DECIMALS),
  };
}
