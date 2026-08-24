/**
 * Layout order on the Explore page.
 *
 * The map is stubbed out: MapLibre needs WebGL2, which jsdom has no notion of,
 * and this file is about where things sit rather than about the map itself.
 * LocationMap's own failure path is covered by its unavailable state.
 */

import { cleanup, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LocationChecker from "../components/LocationChecker";
import { locationStore } from "../lib/store";
import { buildReport } from "./fixtures/report";

vi.mock("../components/map/LocationMap", () => ({
  default: () => <div aria-label="Map. Click anywhere to select a location." />,
}));

/**
 * The map arrives on its own, after the rest of the island.
 *
 * `maplibre-gl` is ~800 KB of what this island used to ship in one chunk, so it
 * is behind a `lazy()` now: the search box paints as soon as its own chunk
 * lands, and the map fills in behind its skeleton. Which means a synchronous
 * `querySelector` for it races the dynamic import and finds nothing.
 */
async function mapElement(container: HTMLElement) {
     return await waitFor(() => {
          const element = container.querySelector('[aria-label^="Map."]');
          if (!element) throw new Error("map not mounted yet");
          return element;
     });
}

describe("LocationChecker layout", () => {
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

  it("puts the report below the map", async () => {
    const { container } = render(() => <LocationChecker />);

    const report = await waitFor(() => {
      const element = container.querySelector("#report");
      if (!element) throw new Error("report region not rendered");
      return element;
    });

    const map = await mapElement(container);
    expect(map).toBeTruthy();

    // DOCUMENT_POSITION_FOLLOWING means the report comes after the map.
    expect(map!.compareDocumentPosition(report) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("puts the selection card between the map and the report", async () => {
    const { container } = render(() => <LocationChecker />);
    await waitFor(() => expect(container.querySelector("#report")).toBeTruthy());

    const map = await mapElement(container);
    const selection = screen.getByText(/nothing picked/i);
    const report = container.querySelector("#report")!;

    expect(map.compareDocumentPosition(selection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      selection.compareDocumentPosition(report) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps the input first", async () => {
    const { container } = render(() => <LocationChecker />);

    const input = await waitFor(() => screen.getByPlaceholderText(/search an address/i));
    const map = await mapElement(container);

    expect(input.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders a single column rather than a two-up grid", async () => {
    const { container } = render(() => <LocationChecker />);
    await waitFor(() => expect(container.querySelector("#report")).toBeTruthy());

    // The old layout used a 12-column grid to sit the map beside the report.
    expect(container.querySelector(".lg\\:grid-cols-12")).toBeNull();
  });
});

describe("bringing a finished report into view", () => {
  /**
   * Side by side with the map, the report is usually already on screen when a
   * check lands, and scrolling something the reader can already see is a jolt.
   * Stacked, it sits below the map and has to be brought up.
   *
   * These need a report that actually renders, so the fetch stub serves a real
   * one — with the earlier `{results: []}` stub the check ended in `error` and
   * the effect under test never ran at all.
   */
  const REPORT = buildReport({
    name: "Pluit",
    elevation: -1,
    terrain: "coastal",
    floodRisk: "high",
    events: 12,
    area: "Jakarta Utara",
  });

  let restoreRect: (() => void) | null = null;

  /** Pin #report at a chosen distance down the viewport. */
  function reportAt(top: number) {
    const original = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {
      if ((this as HTMLElement).id === "report") {
        return { top, bottom: top + 400, height: 400, width: 800, left: 0, right: 800 } as DOMRect;
      }
      return original.call(this);
    };
    restoreRect = () => {
      Element.prototype.getBoundingClientRect = original;
    };
  }

  beforeEach(() => {
    vi.stubGlobal("innerHeight", 900);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost");
        const body = url.pathname.includes("/report")
          ? REPORT
          : { results: [], provider: "test", degraded: false };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    locationStore.clear();
  });

  afterEach(() => {
    restoreRect?.();
    restoreRect = null;
    cleanup();
    vi.unstubAllGlobals();
  });

  async function check() {
    locationStore.select({ latitude: -6.1, longitude: 106.8, name: "Pluit", origin: "search" });
    await locationStore.check();
    await waitFor(() => expect(locationStore.reportStatus()).toBe("ready"));
  }

  it("leaves the page alone when the report is already being read", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    reportAt(120);

    render(() => <LocationChecker />);
    await check();

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("scrolls when the report has landed below the fold", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    reportAt(1400);

    render(() => <LocationChecker />);
    await check();

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });
});
