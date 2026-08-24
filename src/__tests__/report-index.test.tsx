/**
 * The header makes two claims about the report below it — which sections it has,
 * and what those sections are made of. Both are covered here, because a header
 * that lies is worse than one that says nothing.
 *
 * The index duplicates the section titles, because the sections take different
 * props and can't be rendered from one list. This is the guard on that
 * duplication: rename a section and the index stops matching it here, rather
 * than in front of a reader who clicked "Flood" and landed on something else.
 *
 * jsdom has no IntersectionObserver, so the "you are here" highlight falls back
 * to the first chip. That the panel still renders at all is part of what this
 * covers — the observer is a nicety, not a dependency.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReportPanel, { resultSummary } from "../components/report/ReportPanel";
import { locationStore } from "../lib/store";
import { buildReport } from "./fixtures/report";
import type { DataSource, LocationInfo, ReportMeta } from "../lib/types";

const REPORT = buildReport({
  name: "Pluit",
  elevation: -1,
  terrain: "coastal",
  floodRisk: "high",
  events: 12,
  area: "Jakarta Utara",
});

async function renderReport() {
  const result = render(() => <ReportPanel />);
  locationStore.select({ latitude: -6.1, longitude: 106.8, name: "Pluit", origin: "map" });
  await locationStore.check();
  // Anchored on the index rather than the header's heading: the heading is
  // copy and comes and goes, the index is the thing these tests are about.
  await waitFor(() =>
    expect(screen.getByRole("navigation", { name: /report sections/i })).toBeTruthy(),
  );
  return result;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input).includes("/report")
            ? REPORT
            : { query: "", results: [], provider: "test", degraded: false },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
  locationStore.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the report index", () => {
  it("names exactly the sections the report renders, in order", async () => {
    const { container } = await renderReport();

    const nav = screen.getByRole("navigation", { name: /report sections/i });
    const chips = [...nav.querySelectorAll("button")].map((button) =>
      // the leading numeral is the chip's own ornament, not the title
      (button.textContent ?? "").replace(/^\s*\d+\s*/, "").trim(),
    );
    const headings = [...container.querySelectorAll("section h3")].map((heading) =>
      (heading.textContent ?? "").trim(),
    );

    expect(chips).toEqual(headings);
    expect(chips).toHaveLength(7);
  });

  it("points every chip at a section that exists", async () => {
    const { container } = await renderReport();

    for (let index = 1; index <= 7; index += 1) {
      expect(container.querySelector(`#tilik-section-${index}`)).toBeTruthy();
    }
  });

  it("scrolls the section into view rather than moving the page", async () => {
    const { container } = await renderReport();
    const target = container.querySelector("#tilik-section-3")! as HTMLElement;
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;

    fireEvent.click(screen.getByRole("button", { name: /hazard index/i }));

    // `block: "start"` plus the section's own scroll margin is what keeps the
    // heading clear of the sticky header that sent it there.
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("marks where the reader is, and survives having no observer to ask", async () => {
    await renderReport();

    // No IntersectionObserver in jsdom: the index still renders, and falls back
    // to marking the first section.
    const marked = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "true");
    expect(marked).toHaveLength(1);
    expect(marked[0].textContent).toContain("Terrain");
  });
});

describe("what the result is about, and made of", () => {
  const at = (overrides: Partial<LocationInfo> = {}): LocationInfo =>
    ({
      latitude: -6.1,
      longitude: 106.8,
      name: "Pluit",
      displayName: null,
      locality: null,
      district: null,
      city: null,
      province: null,
      ...overrides,
    }) as LocationInfo;

  const meta = (...qualities: Array<DataSource["quality"]>): ReportMeta => ({
    generatedAt: "2026-01-01T00:00:00Z",
    degraded: [],
    sources: qualities.map((quality, index) => ({
      field: `field-${index}`,
      provider: "test",
      quality,
    })),
  });

  const CLOSING = "Every section below names its own source and how confident it is.";

  it("names the place, the count, and how each figure was come by", () => {
    expect(resultSummary(at(), meta("live", "database", "estimate"))).toBe(
      "This information about Pluit is built from 3 data sources. 2 measured directly " +
        `and 1 estimated from models. ${CLOSING}`,
    );
  });

  it("treats cached and live alike, because the reader can't act on the difference", () => {
    expect(resultSummary(at(), meta("live", "live"))).toContain("2 measured directly.");
    expect(resultSummary(at(), meta("database", "database"))).toContain("2 measured directly.");
  });

  it("names the checks that came back empty", () => {
    expect(resultSummary(at(), meta("live", "unavailable", "unavailable"))).toContain(
      "1 measured directly and 2 that returned nothing",
    );
  });

  it("reads all three clauses as a list, not a chain of ands", () => {
    expect(resultSummary(at(), meta("live", "estimate", "unavailable"))).toContain(
      "1 measured directly, 1 estimated from models and 1 that returned nothing",
    );
  });

  it("drops the zeroes rather than printing them", () => {
    // "3 measured, 0 estimated, 0 with no data" is three claims where one will do.
    expect(resultSummary(at(), meta("live", "live", "live"))).toBe(
      `This information about Pluit is built from 3 data sources. 3 measured directly. ${CLOSING}`,
    );
  });

  it("counts one source as a source", () => {
    expect(resultSummary(at(), meta("live"))).toContain("from 1 data source.");
  });

  it("falls back through the place names it has, then to the point itself", () => {
    // A map click has coordinates long before it has a name.
    expect(resultSummary(at({ name: null, locality: "Penjaringan" }), meta("live"))).toContain(
      "about Penjaringan",
    );
    expect(resultSummary(at({ name: null, city: "Jakarta Utara" }), meta("live"))).toContain(
      "about Jakarta Utara",
    );
    expect(resultSummary(at({ name: null }), meta("live"))).toContain("about this point");
  });

  it("keeps the promise when there is no tally to give", () => {
    // The fixtures arrive with no sources, and so does a badly degraded check.
    expect(resultSummary(at(), meta())).toBe(
      `This information about Pluit is built from public data sources. ${CLOSING}`,
    );
  });
});
