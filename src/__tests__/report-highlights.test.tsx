/**
 * The highlights row and the hazard meters.
 *
 * The status colours here were picked with the palette validator, not by eye, so
 * they're asserted: a "tidy-up" that swaps them back to adjacent steps would
 * make high and medium hazard indistinguishable for a protanope.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import HazardSection from "../components/report/HazardSection";
import ReportHighlights from "../components/report/ReportHighlights";
import TerrainSection from "../components/report/TerrainSection";
import type { HazardIndex, HazardReading, LocationReport } from "../lib/types";

function reading(overrides: Partial<HazardReading>): HazardReading {
  return {
    key: "flood",
    label: "Flood",
    index: 0.5,
    level: "medium",
    status: "ok",
    source: "inarisk",
    resolutionMeters: null,
    withinMeters: 0,
    description: "",
    ...overrides,
  };
}

const hazards: HazardIndex = {
  source: "BNPB InaRISK",
  confidence: "high",
  note: null,
  readings: [
    reading({ key: "flood", label: "Flood", index: 0.2, level: "low" }),
    reading({ key: "landslide", label: "Landslide", index: 0.5, level: "medium" }),
    reading({ key: "earthquake", label: "Earthquake", index: 0.9, level: "high" }),
    reading({
      key: "tsunami",
      label: "Tsunami",
      index: null,
      level: "unknown",
      status: "no_data",
      source: "none",
      withinMeters: null,
    }),
  ],
};

const report = {
  terrain: { elevation: 628, unit: "meters", terrain: "highland", description: "", confidence: "high" },
  flood: {
    risk: "high",
    reason: "",
    nearestRiver: null,
    zoneName: null,
    confidence: "high",
    hazardIndex: 0.73,
    basis: "inarisk",
  },
  hazards,
  places: {
    radiusMeters: 1500,
    total: 4,
    confidence: "high",
    note: null,
    categories: [
      {
        key: "health",
        label: "Health",
        count: 2,
        nearest: { name: "Puskesmas Blangpidie", kind: "clinic", category: "health", distanceMeters: 820 },
        places: [],
      },
    ],
  },
} as unknown as LocationReport;

afterEach(cleanup);

describe("ReportHighlights", () => {
  it("leads with the four figures worth reading first", () => {
    render(() => <ReportHighlights report={report} />);

    expect(screen.getByText("Elevation")).toBeTruthy();
    expect(screen.getByText("628 m")).toBeTruthy();

    expect(screen.getByText("Flood risk")).toBeTruthy();
    expect(screen.getByText("High")).toBeTruthy();
    expect(screen.getByText("InaRISK 0.73")).toBeTruthy();

    expect(screen.getByText("Strongest hazard")).toBeTruthy();
    expect(screen.getByText("0.90")).toBeTruthy();
    expect(screen.getByText("Earthquake")).toBeTruthy();

    expect(screen.getByText("Nearest clinic")).toBeTruthy();
    expect(screen.getByText("820 m")).toBeTruthy();
  });

  it("sets values in the sans with proportional figures", () => {
    const { container } = render(() => <ReportHighlights report={report} />);
    const value = screen.getByText("628 m");

    // tabular-nums gives every digit a `0`'s width, which reads loose at display
    // size — it belongs in columns, not on a standalone figure.
    expect(value.className).not.toContain("tilik-figure");
    expect(value.className).toContain("font-semibold");
    expect(container.querySelectorAll("dt")).toHaveLength(4);
  });

  it("falls back rather than inventing a figure", () => {
    const bare = {
      ...report,
      terrain: { ...report.terrain, elevation: null },
      hazards: { ...hazards, readings: [] },
      places: { ...report.places, categories: [] },
    } as unknown as LocationReport;

    render(() => <ReportHighlights report={bare} />);

    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("None mapped here")).toBeTruthy();
    expect(screen.getByText("None mapped nearby")).toBeTruthy();
  });
});

describe("HazardSection meters", () => {
  it("renders a table, which is also the relief for a low-contrast fill", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);

    expect(screen.getByRole("table")).toBeTruthy();
    // Every row names its hazard, so the fill colour is never the only signal.
    expect(screen.getByRole("rowheader", { name: "Flood" })).toBeTruthy();
    expect(screen.getByRole("rowheader", { name: "Earthquake" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Index" })).toBeTruthy();
    // The bar column is decorative; it must not present as a second "Index".
    expect(screen.getAllByRole("columnheader", { name: "Index" })).toHaveLength(1);
  });

  it("uses the validated status steps", () => {
    const { container } = render(() => <HazardSection hazards={hazards} index={3} />);
    const classes = container.innerHTML;

    // Separation checked with the validator: olive-700 / khaki-500 / clay-600
    // clear the normal-vision floor at 17.5 and CVD at 15.4.
    expect(classes).toContain("bg-olive-700");
    expect(classes).toContain("bg-khaki-500");
    expect(classes).toContain("bg-clay-600");
    // The pair that failed: clay-500 against khaki-600 was ΔE 3.1 for protanopia.
    expect(classes).not.toContain("bg-clay-500");
  });

  it("anchors each fill at the baseline with a rounded data-end", () => {
    const { container } = render(() => <HazardSection hazards={hazards} index={3} />);
    const fills = [...container.querySelectorAll('[class*="rounded-r-"]')];

    expect(fills.length).toBe(3); // one per answered reading
    for (const fill of fills) {
      // Rounded only at the data end; square where it meets the baseline.
      expect(fill.className).toContain("rounded-r-[4px]");
      expect(fill.className).not.toContain("rounded-full");
    }
  });

  it("states the index and status as text on every visible row", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);

    expect(screen.getByText("0.20")).toBeTruthy();
    expect(screen.getByText("0.50")).toBeTruthy();
    expect(screen.getByText("0.90")).toBeTruthy();
    expect(screen.getByText(/high · here/i)).toBeTruthy();
  });

  it("counts the layers with nothing to report and reveals them on request", async () => {
    render(() => <HazardSection hazards={hazards} index={3} />);
    const table = screen.getByRole("table");

    // Three of four have a reading; the fourth is counted, not listed.
    expect(table.querySelectorAll("tbody tr")).toHaveLength(3);
    // The count is emphasised per numeral, so "3" and "4" sit in their own
    // elements; `getByText` reads only an element's own text nodes.
    expect(
      screen.getByText((_, element) => /^3 of 4$/.test(element?.textContent?.trim() ?? "")),
    ).toBeTruthy();

    const toggle = screen.getByRole("button", { name: /1 more layer/i });
    fireEvent.click(toggle);

    await waitFor(() => expect(table.querySelectorAll("tbody tr")).toHaveLength(4));
    expect(screen.getByRole("rowheader", { name: "Tsunami" })).toBeTruthy();
    expect(table.textContent).toContain("No hazard mapped");
    expect(table.textContent).toContain("—");
  });

  it("lists every layer when none of them has a reading", () => {
    const silent = {
      ...hazards,
      readings: hazards.readings.map((r) => ({
        ...r,
        index: null,
        status: "no_data" as const,
        level: "unknown" as const,
      })),
    };
    render(() => <HazardSection hazards={silent} index={3} />);

    // Collapsing everything would leave an empty table, which tells the reader
    // nothing about what was checked.
    expect(screen.getByRole("table").querySelectorAll("tbody tr")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: /more layer/i })).toBeNull();
  });

  it("keeps the reference legend out of the way until opened", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);

    const details = screen.getByText(/what these readings mean/i).closest("details");
    expect(details).toBeTruthy();
    expect((details as HTMLDetailsElement).open).toBe(false);
  });

  it("explains the class boundaries the hairlines mark", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);
    expect(screen.getByText(/0\.33 and 0\.67/)).toBeTruthy();
  });
});

describe("hazard section heading", () => {
  it("is set at display size in the serif, and scales up on wider screens", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);
    const heading = screen.getByRole("heading", { name: "Hazard index" });

    // Instrument Serif only reads as a display face at this size; at 1.35rem it
    // is just a small serif.
    expect(heading.className).toContain("font-display");
    expect(heading.className).toContain("text-[2rem]");
    expect(heading.className).toContain("sm:text-[2.4rem]");
  });

  it("carries no colour of its own", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);
    const heading = screen.getByRole("heading", { name: "Hazard index" });

    // Olive and terracotta already mean hazard levels in this section; a heading
    // wearing them would read as a level rather than a title.
    expect(heading.className).toContain("text-ink");
    expect(heading.querySelector(".text-clay-600")).toBeNull();
    expect(heading.querySelector(".text-olive-700")).toBeNull();
  });

  it("keeps a plain accessible name for the progress label to reuse", () => {
    render(() => <HazardSection hazards={hazards} index={3} />);
    expect(screen.getByRole("heading", { name: "Hazard index" })).toBeTruthy();
  });

  it("leaves other sections on the standard heading size", () => {
    render(() => <TerrainSection terrain={report.terrain} index={1} />);
    const heading = screen.getByRole("heading", { name: "Terrain" });

    expect(heading.className).toContain("text-[1.35rem]");
    expect(heading.className).not.toContain("text-[2rem]");
  });
});
