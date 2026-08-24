/**
 * The "incomplete check" notice.
 *
 * Built from real `meta.sources` payloads: the previous copy said "parts of this
 * report are estimated" and left the reader to work out which parts.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReportGaps from "../components/report/ReportGaps";
import { locationStore } from "../lib/store";
import type { DataSource, ReportMeta } from "../lib/types";

/** Captured from a report run with InaRISK and Overpass pointed at dead hosts. */
const SOURCES: DataSource[] = [
  { field: "location", provider: "nominatim", quality: "live", note: null },
  { field: "elevation", provider: "opentopodata", quality: "live", note: null },
  {
    field: "waterways",
    provider: "overpass",
    quality: "unavailable",
    note: "OpenStreetMap did not answer in time.",
  },
  { field: "flood", provider: "heuristic", quality: "estimate", note: null },
  {
    field: "hazards",
    provider: "inarisk",
    quality: "unavailable",
    note: "BNPB InaRISK did not answer.",
  },
  { field: "disasters", provider: "USGS", quality: "live", note: null },
  {
    field: "places",
    provider: "overpass",
    quality: "unavailable",
    note: "Overpass did not answer in time.",
  },
];

const meta = (sources: DataSource[]): ReportMeta => ({
  generatedAt: "2026-01-01T00:00:00Z",
  sources,
  degraded: [],
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ results: [], provider: "test", degraded: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  locationStore.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReportGaps", () => {
  it("says nothing when every source answered", () => {
    const { container } = render(() => (
      <ReportGaps meta={meta(SOURCES.filter((s) => s.quality !== "unavailable"))} />
    ));

    expect(container.textContent).toBe("");
  });

  it("counts the affected sections", () => {
    render(() => <ReportGaps meta={meta(SOURCES)} />);

    // Three fields failed, across two providers.
    expect(screen.getByText("3 sections are incomplete")).toBeTruthy();
  });

  it("names the section, not just 'parts of this report'", () => {
    render(() => <ReportGaps meta={meta(SOURCES)} />);
    const notice = screen.getByLabelText(/gaps in this report/i);

    expect(notice.textContent).toContain("hazard index");
    expect(notice.textContent).toContain("nearby water");
    expect(notice.textContent).toContain("what's nearby");
  });

  it("groups fields under the provider that failed", () => {
    render(() => <ReportGaps meta={meta(SOURCES)} />);
    const notice = screen.getByLabelText(/gaps in this report/i);

    // Overpass took two sections with it; that's one problem, not two.
    expect(notice.querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText(/nearby water and what's nearby are missing/i)).toBeTruthy();
  });

  it("translates provider slugs into names people recognise", () => {
    render(() => <ReportGaps meta={meta(SOURCES)} />);

    expect(screen.getByText("OpenStreetMap")).toBeTruthy();
    expect(screen.getByText("BNPB InaRISK")).toBeTruthy();
    expect(screen.queryByText("overpass")).toBeNull();
    expect(screen.queryByText("inarisk")).toBeNull();
  });

  it("uses singular wording for a single gap", () => {
    const one = SOURCES.filter((s) => s.field !== "waterways" && s.field !== "places");
    render(() => <ReportGaps meta={meta(one)} />);

    expect(screen.getByText("Hazard index is incomplete")).toBeTruthy();
    expect(screen.getByText(/hazard index is missing/i)).toBeTruthy();
  });

  it("offers a retry in place, rather than telling the user to re-run it later", async () => {
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });
    render(() => <ReportGaps meta={meta(SOURCES)} />);

    const retry = screen.getByRole("button", { name: /retry check/i });
    fireEvent.click(retry);

    await waitFor(() => expect(locationStore.reportStatus()).not.toBe("idle"));
  });

  it("shows the retry working while a check runs", async () => {
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });
    render(() => <ReportGaps meta={meta(SOURCES)} />);

    const pending = locationStore.check();
    expect(screen.getByText(/retrying/i)).toBeTruthy();
    expect((screen.getByRole("button", { name: /retrying/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    await pending;
    await waitFor(() => expect(screen.getByText(/retry check/i)).toBeTruthy());
  });
});

describe("gap wording", () => {
  it("joins three or more sections with commas and a final 'and'", () => {
    const many: DataSource[] = [
      { field: "waterways", provider: "overpass", quality: "unavailable", note: null },
      { field: "places", provider: "overpass", quality: "unavailable", note: null },
      { field: "location", provider: "overpass", quality: "unavailable", note: null },
    ];
    render(() => <ReportGaps meta={meta(many)} />);

    expect(screen.getByText(/nearby water, what's nearby and place name are missing/i)).toBeTruthy();
  });
});
