/**
 * One broken section must not cost the reader the report.
 *
 * This is the server's own rule, held on the client. `build_report` degrades a
 * failed provider to one empty section and returns the other nine; the panel
 * used to do the opposite. Any section that threw while rendering unmounted the
 * whole report, and because the skeleton is what shows until a report renders,
 * the reader was left on a loading state that never resolved. No error message,
 * no gaps notice, no other section.
 *
 * The case that proved it is the one reproduced here. A browser holding a
 * bundle that knows about `airQuality` asked an API still serving the older
 * report shape, the field arrived `undefined`, and the new section threw on it.
 * Every deploy has a window where the two disagree, and a dev server started
 * without `--reload` sits in that window indefinitely.
 */

import { cleanup, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReportPanel from "../components/report/ReportPanel";
import { locationStore } from "../lib/store";
import { buildReport } from "./fixtures/report";

function reportWithout(field: string): Record<string, unknown> {
     // Cast through `unknown`: a stale API serves a report that is missing a
     // field, which is exactly a shape `LocationReport` says cannot exist.
     const report = buildReport({
          name: "Bandung",
          elevation: 700,
          terrain: "highland",
          floodRisk: "low",
          events: 2,
          area: "Kota Bandung",
     }) as unknown as Record<string, unknown>;
     delete report[field];
     return report;
}

function serve(report: Record<string, unknown>) {
     vi.stubGlobal(
          "fetch",
          vi.fn(async (input: RequestInfo | URL) =>
               new Response(
                    JSON.stringify(
                         String(input).includes("/report")
                              ? report
                              : { query: "", results: [], provider: "t", degraded: false },
                    ),
                    { status: 200, headers: { "Content-Type": "application/json" } },
               ),
          ),
     );
}

async function check() {
     const result = render(() => <ReportPanel />);
     locationStore.select({
          latitude: -6.9,
          longitude: 107.6,
          name: "Bandung",
          origin: "map",
     });
     await locationStore.check();
     return result;
}

beforeEach(() => {
     locationStore.clear();
     // The fallback logs the real error for whoever is debugging. Expected here.
     vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
     cleanup();
     vi.unstubAllGlobals();
     vi.restoreAllMocks();
});

describe("a section that throws", () => {
     it("does not leave the reader on the skeleton", async () => {
          serve(reportWithout("airQuality"));
          await check();

          // The symptom was that this never appeared.
          await waitFor(() =>
               expect(
                    screen.getByRole("navigation", { name: /report sections/i }),
               ).toBeTruthy(),
          );
     });

     it("costs its own section and nothing else", async () => {
          serve(reportWithout("airQuality"));
          const { container } = await check();

          await waitFor(() =>
               expect(container.textContent).toContain("could not be displayed"),
          );

          // The eight other sections are all still there, with their content.
          expect(container.textContent).toContain("Description for Bandung");
          expect(container.textContent).toContain("Flood reason for Bandung");
          expect(container.querySelectorAll("section").length).toBeGreaterThanOrEqual(8);
     });

     it("keeps the anchor and heading its index chip points at", async () => {
          serve(reportWithout("airQuality"));
          const { container } = await check();

          await waitFor(() => expect(container.querySelector("#tilik-section-6")).toBeTruthy());

          const heading = container.querySelector("#tilik-section-6 h3");
          expect(heading?.textContent?.trim()).toBe("Air quality");
     });

     it("says nothing that could be read as a finding", async () => {
          serve(reportWithout("airQuality"));
          const { container } = await check();

          await waitFor(() =>
               expect(container.textContent).toContain("could not be displayed"),
          );
          // A blank section must never imply clean air, low risk or no hazard.
          expect(container.textContent).toContain(
               "nothing here should be read as a finding",
          );
     });

     it("holds for any section, not just the newest one", async () => {
          // Every field added to the report reopens this window.
          serve(reportWithout("terrain"));
          const { container } = await check();

          await waitFor(() =>
               expect(
                    screen.getByRole("navigation", { name: /report sections/i }),
               ).toBeTruthy(),
          );
          expect(container.textContent).toContain("could not be displayed");
          // Air quality, four sections further down, still rendered.
          expect(container.textContent).toContain("Air-quality reading for Bandung");
     });
});
