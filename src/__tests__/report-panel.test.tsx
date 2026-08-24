/**
 * Does the report UI actually re-render when a second location is checked?
 *
 * The store and the panel are exercised together, against a stubbed fetch, so a
 * regression that leaves stale values on screen fails here rather than being
 * spotted by eye.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReportPanel from "../components/report/ReportPanel";
import ReportSummary from "../components/report/ReportSummary";
import { locationStore } from "../lib/store";
import { buildReport } from "./fixtures/report";

const JAKARTA = buildReport({
  name: "Pluit",
  elevation: -1,
  terrain: "coastal",
  floodRisk: "high",
  events: 12,
  area: "Jakarta Utara",
});

const BANDUNG = buildReport({
  name: "Bandung",
  elevation: 698,
  terrain: "highland",
  floodRisk: "low",
  events: 3,
  area: "Kota Bandung",
});

/** Serve a different report per latitude, so staleness is visible. */
function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const lat = Number(url.searchParams.get("lat"));
    const body = url.pathname.includes("/report")
      ? lat < -6.5
        ? BANDUNG
        : JAKARTA
      : { query: "", results: [], provider: "test", degraded: false };

    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

/**
 * The report as the page assembles it: the verdict card and the detail sections.
 * Splitting them across two components is a layout decision, so the tests keep
 * asserting against the whole result rather than one half of it.
 */
function ReportUi() {
  return (
    <>
      <ReportSummary />
      <ReportPanel />
    </>
  );
}

describe("ReportPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the checked location's own values", async () => {
    render(() => <ReportUi />);

    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();

    // Elevation and terrain appear twice on purpose: once as a highlight tile,
    // once in the Terrain section that explains them.
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));
    expect(screen.getAllByText("Coastal")).toHaveLength(2);
    expect(screen.getByText("Jakarta Utara")).toBeTruthy();
    expect(screen.getByText(/high risk/i)).toBeTruthy();
  });

  it("replaces every section when a second location is checked", async () => {
    render(() => <ReportUi />);

    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });
    await locationStore.check();

    // Terrain, flood, disasters and area must all follow the new report.
    await waitFor(() => expect(screen.getAllByText("698 m")).toHaveLength(2));
    expect(screen.getAllByText("Highland")).toHaveLength(2);
    expect(screen.getByText("Kota Bandung")).toBeTruthy();
    expect(screen.getByText(/low risk/i)).toBeTruthy();
    expect(screen.getByText(/Headline for Bandung/)).toBeTruthy();

    // And none of the first location's values may survive, in either place.
    expect(screen.queryAllByText("-1 m")).toHaveLength(0);
    expect(screen.queryAllByText("Coastal")).toHaveLength(0);
    expect(screen.queryByText("Jakarta Utara")).toBeNull();
  });
});

describe("re-checking a location", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("holds the previous report instead of flashing a skeleton", async () => {
    const { container } = render(() => <ReportUi />);

    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    // Start a second check without awaiting it: mid-flight, the old report must
    // still be on screen rather than replaced by a placeholder.
    const pending = locationStore.check();

    const article = container.querySelector("article")!;
    expect(article.getAttribute("aria-busy")).toBe("true");
    expect(article.className).toContain("opacity-60");
    expect(screen.getAllByText("-1 m")).toHaveLength(2);

    await pending;
    await waitFor(() => expect(container.querySelector("article")?.getAttribute("aria-busy")).toBe("false"));
  });

  it("still shows a skeleton for the very first check", async () => {
    const { container } = render(() => <ReportUi />);

    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    const pending = locationStore.check();

    // Nothing to hold on to yet, so a placeholder is right here.
    expect(container.querySelector("article")).toBeNull();
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();

    await pending;
    await waitFor(() => expect(container.querySelector("article")).toBeTruthy());
  });
});

describe("report readability", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function showReport() {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));
  }

  it("gives every section a plain-language lede", async () => {
    await showReport();

    expect(screen.getByText(/how high the ground sits/i)).toBeTruthy();
    expect(screen.getByText(/whether water is likely to be a problem/i)).toBeTruthy();
    expect(screen.getByText(/what has actually been recorded/i)).toBeTruthy();
    expect(screen.getByText(/day-to-day essentials/i)).toBeTruthy();
  });

  it("labels confidence in words rather than jargon", async () => {
    await showReport();

    // "Measured" / "Modelled" / "Estimated" beat "Measured data" in small caps.
    expect(screen.getAllByText(/^(Measured|Modelled|Estimated|No data)$/).length).toBeGreaterThan(2);
  });

  it("caps the disaster list rather than printing all twelve", async () => {
    await showReport();

    const list = screen.getByText(/5 of 12/).closest("section")!;
    expect(list.querySelectorAll("li").length).toBeLessThanOrEqual(5);

    const more = screen.getByRole("button", { name: /show all 12 events/i });
    fireEvent.click(more);

    await waitFor(() => expect(list.querySelectorAll("li").length).toBe(12));
  });
});

describe("progress and counts stay visible", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("announces a re-check instead of only dimming", async () => {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    const pending = locationStore.check();

    // Dimming is easy to miss; a status line is not.
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText(/updating this report/i)).toBeTruthy();

    await pending;
    await waitFor(() => expect(screen.queryByText(/updating this report/i)).toBeNull());
  });

  it("says how many events it is showing of the total", async () => {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();

    // A capped list must not look like missing data.
    await waitFor(() => expect(screen.getByText(/5 of 12/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /show all 12 events/i }));
    await waitFor(() => expect(screen.queryByText(/5 of 12/)).toBeNull());
    expect(screen.getByText(/^12$/)).toBeTruthy();
  });
});

describe("per-section progress", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows progress in every section header, disaster history included", async () => {
    const { container } = render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    const disasters = screen.getByText(/what has actually been recorded/i).closest("section")!;
    expect(disasters.getAttribute("aria-busy")).toBe("false");

    const pending = locationStore.check();

    // Someone scrolled down to a section can't see a status line at the top, so
    // the section itself has to say it's updating.
    expect(disasters.getAttribute("aria-busy")).toBe("true");
    expect(disasters.textContent).toContain("Updating");
    expect(container.querySelectorAll('section[aria-busy="true"]').length).toBe(7);

    await pending;
    await waitFor(() => expect(disasters.getAttribute("aria-busy")).toBe("false"));
    expect(disasters.textContent).not.toContain("Updating");
  });

  it("swaps the confidence chip rather than adding to it", async () => {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    // Five sections report a confidence; Area and Local news have none to report.
    const before = screen.getAllByText(/^(Measured|Modelled|Estimated|No data)$/).length;
    expect(before).toBe(5);

    const pending = locationStore.check();

    // Chips are replaced, not stacked, so no section changes height. All six
    // sections show progress, including the one with no confidence chip.
    expect(screen.queryAllByText(/^(Measured|Modelled|Estimated|No data)$/)).toHaveLength(0);
    expect(screen.getAllByText("Updating")).toHaveLength(7);

    await pending;
    await waitFor(() =>
      expect(screen.getAllByText(/^(Measured|Modelled|Estimated|No data)$/).length).toBe(before),
    );
    expect(screen.queryAllByText("Updating")).toHaveLength(0);
  });
});

describe("section progress bar", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function ready() {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));
  }

  it("gives disaster history its own progress bar while updating", async () => {
    await ready();
    expect(screen.queryByRole("progressbar", { name: /disaster history/i })).toBeNull();

    const pending = locationStore.check();

    const bar = screen.getByRole("progressbar", { name: /updating disaster history/i });
    expect(bar).toBeTruthy();
    // Indeterminate: one API call has no percentage to report.
    expect(bar.getAttribute("aria-valuenow")).toBeNull();

    await pending;
    await waitFor(() =>
      expect(screen.queryByRole("progressbar", { name: /disaster history/i })).toBeNull(),
    );
  });

  it("bars every section, and costs no layout to show", async () => {
    await ready();
    const disasters = screen.getByText(/what has actually been recorded/i).closest("section")!;
    const heightBefore = disasters.getBoundingClientRect().height;

    const pending = locationStore.check();

    expect(screen.getAllByRole("progressbar")).toHaveLength(7);
    // Absolutely positioned, so appearing must not resize the section.
    expect(disasters.getBoundingClientRect().height).toBe(heightBefore);

    await pending;
    await waitFor(() => expect(screen.queryAllByRole("progressbar")).toHaveLength(0));
  });
});

describe("verdict block stands apart from the report card", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("uses a dedicated surface, not one of the faint -50 tints", async () => {
    const { container } = render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    const verdict = screen.getByText("Overall assessment").closest("div")!;

    // The -50 tints separated from the card by only 1.20–1.30:1.
    expect(verdict.className).toMatch(/bg-verdict-(low|moderate|higher|unknown)/);
    expect(verdict.className).not.toMatch(/bg-(olive|khaki|clay)-50\b/);
    // An edge carries as much of the separation as the fill does.
    expect(verdict.className).toContain("border-b");
    expect(container.querySelector(".bg-verdict-moderate")).toBeTruthy();
  });

  it("sets the level in ink, with the colour on the dot beside it", async () => {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();

    const level = await waitFor(() => screen.getByText("Moderate concern"));

    // Khaki is too light to be text on a khaki-tinted surface, so the word wears
    // a text token and the dot carries identity.
    expect(level.className).toContain("text-ink");
    expect(level.className).not.toMatch(/text-(khaki|clay|olive)-/);
    expect(level.parentElement?.querySelector(".bg-khaki-700")).toBeTruthy();
  });
});

describe("hazard status text", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("capitalises the level without capitalising the unit", async () => {
    render(() => <ReportUi />);
    locationStore.select({ latitude: -6.11, longitude: 106.79, name: "Pluit", origin: "map" });
    await locationStore.check();
    await waitFor(() => expect(screen.getAllByText("-1 m")).toHaveLength(2));

    // The cell used CSS `capitalize`, which title-cases every word and rendered
    // "high · 320 m away" as "High · 320 M Away". The level is capitalised in the
    // string instead, so the metre unit stays a metre unit.
    const cell = screen.getByText(/320 m away/);
    expect(cell.textContent).toBe("High · 320 m away");
    expect(cell.className).not.toContain("capitalize");
  });
});

describe("the report's own caveat", () => {
     /**
      * `assessment.disclaimer` existed in the schema and the types and was
      * rendered nowhere — it appeared only in test fixtures. It is the one thing
      * on the page that has to be read: every figure above it comes from a
      * national model or a national archive, and none of them surveyed the plot.
      */
     beforeEach(() => {
          vi.stubGlobal("fetch", stubFetch());
          locationStore.clear();
     });

     afterEach(() => {
          cleanup();
          vi.unstubAllGlobals();
     });

     it("is shown, not merely carried in the payload", async () => {
          const { container } = render(() => <ReportUi />);

          locationStore.select({
               latitude: -6.11,
               longitude: 106.79,
               name: "Pluit",
               origin: "map",
          });
          await locationStore.check();

          await waitFor(() =>
               expect(container.querySelector("footer")).toBeTruthy(),
          );
          // Whatever the wording, the payload's text has to reach the page.
          expect(container.textContent).toContain("Not a survey.");
     });
});
