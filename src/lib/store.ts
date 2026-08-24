import { createSignal } from "solid-js";
import { ApiError, api } from "./api";
import type { CoordinateFormat } from "./coordinates";
import type { LocationReport } from "./types";

/**
 * Single source of truth for the check flow. It lives at module scope so the
 * map, the search box and the report can stay independent components without
 * prop-drilling through the island root.
 */

export interface SelectedLocation {
  latitude: number;
  longitude: number;
  /** Best label we have so far — may be filled in later by reverse geocoding. */
  name: string | null;
  /** How the point got picked, used for subtle copy in the UI. */
  origin: "search" | "map" | "geolocation" | "coordinates";
  /**
   * Kecamatan, kabupaten or kota, and province, once reverse geocoding answers.
   *
   * A street name alone does not identify a place: Indonesia has more than one
   * Serpong and more than one Palu. Ordering them is `adminChain`'s job, because
   * the geocoder does not put them under consistent keys.
   */
  district?: string | null;
  city?: string | null;
  province?: string | null;
}

export type ReportStatus = "idle" | "loading" | "ready" | "error";

const [selected, setSelected] = createSignal<SelectedLocation | null>(null);
const [reportStatus, setReportStatus] = createSignal<ReportStatus>("idle");
const [report, setReport] = createSignal<LocationReport | null>(null);
const [reportError, setReportError] = createSignal<string | null>(null);
const [resolvingName, setResolvingName] = createSignal(false);

let inFlight: AbortController | null = null;

/**
 * Preferred coordinate notation, shared so the selection card and the
 * coordinate field agree, and sticky for the session — someone working from
 * DMS certificates shouldn't have to reselect it on every check.
 */
const [coordinateFormat, setCoordinateFormat] = createSignal<CoordinateFormat>("dd");

export type InputMode = "place" | "coordinates";

/**
 * Which way of picking a point is on screen. It lives here rather than inside
 * the input because the empty state offers the same routes in, and a shortcut
 * that can't move the control it points at is just a label.
 */
const [inputMode, setInputMode] = createSignal<InputMode>("place");

/** Bumped to ask whichever input is showing to take the cursor. */
const [focusRequest, setFocusRequest] = createSignal(0);

/**
 * Whether the evidence is on screen. The trigger sits at the foot of the
 * verdict block and the dialog is mounted out beside the map, so neither of them
 * can own this — the same reason `inputMode` lives here.
 */
const [reportOpen, setReportOpen] = createSignal(false);

export const displayStore = {
  coordinateFormat,
  setCoordinateFormat,
  inputMode,
  setInputMode,
  focusRequest,
  reportOpen,

  /** Show `mode` and put the cursor in it — one call for "start here". */
  startWith(mode: InputMode) {
    setInputMode(mode);
    setFocusRequest((n) => n + 1);
  },

  openReport() {
    setReportOpen(true);
  },

  closeReport() {
    setReportOpen(false);
  },
};

export const locationStore = {
  selected,
  reportStatus,
  report,
  reportError,
  resolvingName,

  select(next: SelectedLocation) {
    inFlight?.abort();
    inFlight = null;
    setSelected(next);
    setReport(null);
    setReportError(null);
    setReportStatus("idle");

    // A map click has coordinates but no name yet, and a search result has a
    // name but not always the administrative chain: Nominatim omits the address
    // block for some results, and the offline fallback has none at all. Either
    // gap is worth one quiet lookup; the report still works if it fails.
    if (!next.name || !next.province) void locationStore.resolveName(next);
  },

  async resolveName(target: SelectedLocation) {
    setResolvingName(true);
    try {
      const response = await api.reverse(target.latitude, target.longitude);
      const match = response.results[0];
      const current = selected();
      if (
        match &&
        current &&
        current.latitude === target.latitude &&
        current.longitude === target.longitude
      ) {
        // Gaps only. A name the reader chose from the search box is the one
        // they recognise, and replacing it with the nearest street would be a
        // worse label than the one they picked.
        setSelected({
          ...current,
          name: current.name ?? match.name,
          district: current.district ?? match.district,
          city: current.city ?? match.city,
          province: current.province ?? match.province,
        });
      }
    } catch {
      // Nameless coordinates are perfectly usable — stay silent.
    } finally {
      setResolvingName(false);
    }
  },

  clear() {
    inFlight?.abort();
    inFlight = null;
    setInputMode("place");
    setSelected(null);
    setReport(null);
    setReportError(null);
    setReportStatus("idle");
  },

  async check() {
    const target = selected();
    if (!target) return;

    inFlight?.abort();
    const controller = new AbortController();
    inFlight = controller;

    setReportStatus("loading");
    setReportError(null);

    try {
      const result = await api.report(target.latitude, target.longitude, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setReport(result);
      setReportStatus("ready");

      // The report carries a better name than a raw map click ever will.
      const current = selected();
      if (current && !current.name && result.location.name) {
        setSelected({ ...current, name: result.location.name });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setReportError(
        error instanceof ApiError
          ? error.message
          : "We couldn't finish this check. Try again in a moment.",
      );
      setReportStatus("error");
    } finally {
      if (inFlight === controller) inFlight = null;
    }
  },
};
