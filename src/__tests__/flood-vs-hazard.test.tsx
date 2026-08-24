/**
 * Flood and the hazard index both speak about flood, and the report has to say
 * how they relate. Without this, the same InaRISK reading appears in both
 * sections with nothing marking it as one reading, and reads as two independent
 * sources agreeing.
 */

import { cleanup, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import FloodSection from "../components/report/FloodSection";
import type { FloodInfo, RiskLevel } from "../lib/types";

function flood(overrides: Partial<FloodInfo>): FloodInfo {
  return {
    risk: "high",
    reason: "Reason.",
    nearestRiver: null,
    zoneName: null,
    confidence: "high",
    hazardIndex: null,
    hazardLevel: null,
    basis: "heuristic",
    ...overrides,
  } as FloodInfo;
}

afterEach(cleanup);

describe("how Flood names its relationship to the hazard index", () => {
  it("says the model is the same reading, not a second source", () => {
    render(() => (
      <FloodSection index={2} flood={flood({ basis: "inarisk", hazardIndex: 0.78, hazardLevel: "high" })} />
    ));

    const line = screen.getByText(/the same reading rather than a second source/i);
    // `reason` already quotes the index, so this line must not quote it again.
    expect(line.textContent).not.toMatch(/0\.78|of 1\.00/);
  });

  it("says so out loud when the mapped zone and the model disagree", () => {
    render(() => (
      <FloodSection
        index={2}
        flood={flood({ basis: "postgis", risk: "high", hazardIndex: 0.2, hazardLevel: "low", zoneName: "Pluit" })}
      />
    ));

    // The gap is the most useful thing this section can report, so it is stated
    // rather than left for the reader to find by comparing two sections.
    const line = screen.getByText(/BNPB's national model reads this lower/i);
    expect(line.textContent).toContain("0.20 of 1.00");
    expect(line.textContent).toMatch(/mapped zone is the more specific source/i);
  });

  it("credits the model when it agrees", () => {
    render(() => (
      <FloodSection index={2} flood={flood({ basis: "heuristic", risk: "high", hazardIndex: 0.9, hazardLevel: "high" })} />
    ));

    expect(screen.getByText(/national model agrees, at index 0\.90/i)).toBeTruthy();
  });

  it("stays quiet when the model never answered", () => {
    render(() => <FloodSection index={2} flood={flood({ basis: "heuristic" })} />);

    expect(screen.queryByText(/national model/i)).toBeNull();
  });

  it("keeps the zone and the index as separate facts", () => {
    // One cell showing whichever existed hid the mapped zone as soon as the
    // index started arriving alongside it.
    render(() => (
      <FloodSection
        index={2}
        flood={flood({ basis: "postgis", hazardIndex: 0.2, hazardLevel: "low", zoneName: "Pluit" })}
      />
    ));

    expect(screen.getByText("Flood zone")).toBeTruthy();
    expect(screen.getByText("Pluit")).toBeTruthy();
    expect(screen.getByText("InaRISK flood index")).toBeTruthy();
    expect(screen.getByText("0.20")).toBeTruthy();
  });
});
