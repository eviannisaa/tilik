/**
 * Air quality is the only instrument reading in the report, which makes it the
 * one section a reader is most likely to over-trust.
 *
 * Three things have to survive here, and each is a claim the section makes
 * rather than a detail of its markup:
 *
 * * **The station's distance is on the page.** WAQI answers with whichever
 *   monitor is nearest and never says how far that is. Its `demo` token proves
 *   why it matters: asked about Jakarta it returns Shanghai, 4,440 km away, and
 *   the reading looks entirely plausible.
 * * **The attributions are rendered.** WAQI's terms require crediting the
 *   project and the originating EPA, and the originating EPA appears nowhere
 *   else. This is a licence condition, not decoration.
 * * **The four empty states read differently.** "No token configured", "turned
 *   off", "no station here" and "the service didn't answer" mean four different
 *   things, and none of them means clean air.
 */

import { cleanup, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import AirQualitySection from "../components/report/AirQualitySection";
import type { AirQuality } from "../lib/types";

afterEach(cleanup);

function air(overrides: Partial<AirQuality> = {}): AirQuality {
     return {
          aqi: 78,
          band: "moderate",
          level: "low",
          bandLabel: "Moderate",
          dominantPollutant: "pm25",
          dominantLabel: "PM2.5",
          pollutants: [
               {
                    key: "pm25",
                    label: "PM2.5",
                    aqi: 78,
                    band: "moderate",
                    bandLabel: "Moderate",
                    level: "low",
                    dominant: true,
               },
               {
                    key: "pm10",
                    label: "PM10",
                    aqi: 31,
                    band: "good",
                    bandLabel: "Good",
                    level: "low",
                    dominant: false,
               },
          ],
          // Six on the EPA scale; BMKG's stations mostly report one.
          pollutantsPossible: 6,
          // A real WAQI station. The DKI AQMS names ("Kebon Jeruk", "Bundaran
          // HI") are not in this feed, and a fixture naming one would suggest
          // coverage that does not exist.
          stationName: "Kemayoran, Indonesia",
          stationUrl: "https://aqicn.org/city/indonesia/kemayoran",
          stationDistanceMeters: 4_200,
          measuredAt: "2026-01-01T00:00:00Z",
          attributions: [
               { name: "BMKG | Badan Meteorologi, Klimatologi dan Geofisika", url: "http://www.bmkg.go.id/" },
               { name: "World Air Quality Index Project", url: "https://waqi.info/" },
          ],
          status: "ok",
          confidence: "high",
          description: "AQI 78, which the US EPA scale calls moderate.",
          note: null,
          ...overrides,
     };
}

/**
 * The headline figure, not the pollutant row that shares its value.
 *
 * They are the same number on purpose: WAQI's overall AQI *is* its dominant
 * pollutant's sub-index, so a fixture where they differ would not be a WAQI
 * reading. That makes `getByText("78")` ambiguous, and the ambiguity is real
 * rather than a fixture artefact.
 */
const headline = (container: HTMLElement) =>
     container.querySelector(".text-4xl")?.textContent?.trim();

const render$ = (reading: AirQuality) =>
     render(() => <AirQualitySection index={6} airQuality={reading} />);

describe("a reading that came back", () => {
     it("leads with the figure and the band the EPA calls it", () => {
          const { container } = render$(air());

          expect(headline(container)).toBe("78");
          expect(screen.getByText("Moderate")).toBeTruthy();
     });

     it("keeps the six EPA bands rather than the three-tone palette", () => {
          // "Moderate" and "Good" both colour olive, so the palette cannot tell
          // them apart. Losing the band names is how a six-band standard
          // silently becomes a three-band one.
          const { container } = render$(air());
          const status = [...container.querySelectorAll("tbody tr")].map(
               (row) => row.querySelector("td:last-child")?.textContent?.trim(),
          );

          expect(status).toEqual(["Moderate · sets the index", "Good"]);
     });

     it("puts the pollutant table in the same shape as the hazard table", () => {
          // `HazardSection` reads Hazard | bar | Index | Status. This one has to
          // read Pollutant | bar | AQI | Status, with the qualifier in Status
          // rather than jammed against the name.
          const { container } = render$(air());
          const columns = [...container.querySelectorAll("thead th")].map(
               (cell) => (cell.textContent ?? "").trim() || "(bar)",
          );

          expect(columns).toEqual(["Pollutant", "(bar)", "AQI", "Status"]);

          const first = container.querySelector("tbody tr")!;
          const cells = [...first.querySelectorAll("th,td")].map(
               (cell) => (cell.textContent ?? "").replace(/\s+/g, " ").trim(),
          );
          // The name is the name. Nothing is appended to it.
          expect(cells[0]).toBe("PM2.5");
          expect(cells[2]).toBe("78");
          expect(cells[3]).toBe("Moderate · sets the index");
     });

     it("names every pollutant and marks the one setting the index", () => {
          const { container } = render$(air());

          expect(screen.getByText("PM10")).toBeTruthy();
          // One marker, for one dominant pollutant, and it sits in Status.
          expect(container.textContent!.match(/sets the index/g)).toHaveLength(1);
          expect(
               container.querySelector("tbody tr td:last-child")?.textContent,
          ).toContain("sets the index");
     });

     it("says how many pollutants the station actually measures", () => {
          // BMKG's stations mostly report PM2.5 alone. Without this line a
          // one-row table reads as a complete picture of the air.
          const { container } = render$(
               air({
                    pollutants: [
                         {
                              key: "pm25",
                              label: "PM2.5",
                              aqi: 152,
                              band: "unhealthy",
                              bandLabel: "Unhealthy",
                              level: "high",
                              dominant: true,
                         },
                    ],
               }),
          );

          expect(container.textContent).toContain("1");
          // No verb: "1 of 6 pollutants are measured" does not agree.
          expect(container.textContent).toContain(
               "pollutants measured at this station",
          );
          expect(container.textContent).not.toContain("pollutants are measured");
     });

     it("drops the dominant marker when there was nothing to beat", () => {
          // "sets the index" claims this pollutant won a comparison. With one
          // measurement no comparison happened.
          const { container } = render$(
               air({
                    pollutants: [
                         {
                              key: "pm25",
                              label: "PM2.5",
                              aqi: 152,
                              band: "unhealthy",
                              bandLabel: "Unhealthy",
                              level: "high",
                              dominant: true,
                         },
                    ],
               }),
          );

          expect(container.textContent).not.toContain("sets the index");
          expect(
               container.querySelector("tbody tr td:last-child")?.textContent?.trim(),
          ).toBe("Unhealthy");
     });

     it("separates attributions with something their own names do not contain", () => {
          // "BMKG | Badan Meteorologi, Klimatologi dan Geofisika" carries two
          // commas, so comma-separating the list showed four candidate names
          // where there were two.
          const { container } = render$(air());
          const credits = [...container.querySelectorAll("p")].find((node) =>
               node.textContent?.includes("Measured and published by"),
          );

          expect(credits).toBeTruthy();
          expect(credits!.textContent).toContain("·");
          // The comma inside BMKG's name must not read as a separator.
          expect(credits!.textContent).not.toContain("Geofisika, World");
     });

     it("says how far away the station is, because WAQI never does", () => {
          const { container } = render$(air());

          expect(screen.getByText("Kemayoran, Indonesia")).toBeTruthy();
          expect(container.textContent).toContain("4.2 km");
     });

     it("credits the sources the licence requires", () => {
          render$(air());

          expect(
               screen.getByText(/Badan Meteorologi, Klimatologi dan Geofisika/),
          ).toBeTruthy();
          expect(screen.getByText("World Air Quality Index Project")).toBeTruthy();
     });

     it("warns when the figure stopped being about this point", () => {
          const { container } = render$(
               air({ stationDistanceMeters: 38_000, confidence: "low" }),
          );

          expect(container.textContent).toContain("38 km");
          expect(container.textContent).toContain(
               "not a measurement of the air at this point",
          );
     });

     it("says the distance once, and only adds what to do about it", () => {
          // Three copies of "38 km" in one section reads as three problems.
          const { container } = render$(
               air({
                    stationDistanceMeters: 38_000,
                    confidence: "low",
                    description: "AQI 78. The nearest station is far from this point.",
               }),
          );

          expect(container.textContent!.match(/38 km/g)).toHaveLength(1);
     });

     it("stays quiet about distance when the station is next door", () => {
          const { container } = render$(air());

          expect(container.textContent).not.toContain("not over this plot");
     });

     it("survives a reading with no station name, url or timestamp", () => {
          // A real WAQI body with `city.location: ""` and no `time.iso`.
          const { container } = render$(
               air({
                    stationName: null,
                    stationUrl: null,
                    measuredAt: null,
                    stationDistanceMeters: null,
                    confidence: "none",
               }),
          );

          expect(container.textContent).toContain("Station unnamed");
          expect(headline(container)).toBe("78");
     });
});

describe("a reading that did not", () => {
     it.each([
          ["not_configured", /isn't set up/i],
          ["disabled", /turned off/i],
          ["no_station", /No station is reporting for this point/i],
          ["unavailable", /didn't answer/i],
     ] as const)("says what %s actually means", (status, expected) => {
          render$(
               air({
                    status,
                    aqi: null,
                    band: "unknown",
                    level: "unknown",
                    bandLabel: null,
                    pollutants: [],
                    attributions: [],
                    confidence: "none",
                    note: null,
               }),
          );

          expect(screen.getByText(expected)).toBeTruthy();
     });

     it("shows a distant station's figure rather than withholding it", () => {
          // The Bandung case: WAQI's nearest monitor is Kemayoran in Jakarta,
          // 120 km off. A cutoff used to suppress the number here and left most
          // of the country with a blank section, so the figure is shown with
          // its distance instead.
          const { container } = render$(
               air({
                    aqi: 152,
                    band: "unhealthy",
                    bandLabel: "Unhealthy",
                    level: "high",
                    confidence: "low",
                    stationName: "Kemayoran, Indonesia",
                    stationDistanceMeters: 120_344,
                    pollutants: [
                         {
                              key: "pm25",
                              label: "PM2.5",
                              aqi: 152,
                              band: "unhealthy",
                              bandLabel: "Unhealthy",
                              level: "high",
                              dominant: true,
                         },
                    ],
               }),
          );

          expect(headline(container)).toBe("152");
          expect(container.textContent).toContain("Kemayoran, Indonesia");
          expect(container.textContent).toContain("120 km away");
          // Demoted, not hidden: "Estimated" is the badge, and the flag says
          // plainly what the figure is.
          expect(container.textContent).toContain("Estimated");
          expect(container.textContent).toContain(
               "not a measurement of the air at this point",
          );
          expect(container.textContent).not.toContain("could not be displayed");
     });

     it("keeps the far-station flag true at any distance", () => {
          // It has to hold at 26 km and at the 4,440 km the demo token answers,
          // so it must not claim the reading describes "this area".
          for (const metres of [26_000, 120_344, 4_440_000]) {
               const { container, unmount } = render$(
                    air({ stationDistanceMeters: metres, confidence: "low" }),
               );
               expect(container.textContent).toContain(
                    "This is the nearest station's reading",
               );
               unmount();
          }
     });

     it("never lets an empty section read as clean air", () => {
          const { container } = render$(
               air({
                    status: "no_station",
                    aqi: null,
                    band: "unknown",
                    level: "unknown",
                    bandLabel: null,
                    pollutants: [],
                    attributions: [],
                    confidence: "none",
                    note: null,
               }),
          );

          expect(container.textContent).toContain("not clean air");
          expect(container.textContent).not.toContain("Good");
     });

     it("prefers the backend's own account of the failure", () => {
          // The service can name the particular failure; the generic copy can't.
          render$(
               air({
                    status: "unavailable",
                    aqi: null,
                    band: "unknown",
                    bandLabel: null,
                    pollutants: [],
                    attributions: [],
                    confidence: "none",
                    note: "WAQI would not accept the configured token.",
               }),
          );

          expect(
               screen.getByText(/would not accept the configured token/i),
          ).toBeTruthy();
     });
});
