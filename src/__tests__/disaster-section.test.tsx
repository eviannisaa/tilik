/**
 * Disaster history reads out shaking and human cost, not just magnitude.
 *
 * The section used to print "4.4 mb" and stop. That number is unreadable for
 * the person Tilik is for: magnitude 4.4 is a non-event 194 km down in the slab
 * under Java and a damaging quake at 10 km, and it says nothing at all about a
 * flood, which is the hazard that actually recurs around Tangerang. Intensity
 * describes what the ground did at a place; the impact counts describe what it
 * did to people. Both now lead.
 */

import { cleanup, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import DisasterSection from "../components/report/DisasterSection";
import { formatImpact, formatIntensity, formatMagnitude } from "../lib/format";
import type { DisasterEvent, DisasterHistory } from "../lib/types";

afterEach(cleanup);

function event(overrides: Partial<DisasterEvent> = {}): DisasterEvent {
     return {
          id: "e1",
          type: "earthquake",
          hazardTypes: ["earthquake"],
          areaName: null,
          title: "11 km NE of Sukabumi, Indonesia",
          occurredAt: "2022-11-21T06:21:00Z",
          magnitude: 5.6,
          magnitudeScale: "mw",
          magnitudeScaleSource: "mww",
          depthKm: 10,
          intensityMmi: 8.471,
          intensityBasis: "modelled",
          feltReports: 169,
          impact: null,
          distanceMeters: 42_000,
          distanceBasis: "measured" as const,
          waterHeightM: null,
          source: "USGS",
          url: null,
          scope: "point",
          severity: "orange",
          ...overrides,
     };
}

function history(events: DisasterEvent[]): DisasterHistory {
     return {
          radiusMeters: 50_000,
          events,
          searchedYears: 25,
          earthquakeRadiusMeters: null,
          tsunamiYears: null,
          confidence: "high",
          searchedSources: ["USGS earthquake catalogue"],
          coveredTypes: ["earthquake"],
          note: null,
     };
}

describe("formatIntensity", () => {
     it("gives the degree and what it means", () => {
          expect(formatIntensity(8.471)).toBe("VIII (extremely strong)");
          expect(formatIntensity(2)).toBe("II (weak)");
          expect(formatIntensity(6)).toBe("VI (strong)");
     });

     it("keeps one consistent ladder, without light or severe", () => {
          // USGS's own words mix registers: "weak, light, moderate" leaves a
          // reader guessing whether light is milder than weak, and "severe,
          // violent, extreme" is three near-synonyms in a row.
          const ladder = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((d) =>
               formatIntensity(d),
          );

          expect(ladder.some((l) => /light/.test(l!))).toBe(false);
          expect(ladder.some((l) => /severe/.test(l!))).toBe(false);
          expect(formatIntensity(6)).toBe("VI (strong)");
          expect(formatIntensity(7)).toBe("VII (very strong)");
          expect(formatIntensity(8)).toBe("VIII (extremely strong)");
     });

     it("does not move a word to a different degree", () => {
          // MMI VI officially means Strong. Shifting that word down to V would
          // have the report overstate what the ground actually did.
          expect(formatIntensity(5)).not.toBe("V (strong)");
          expect(formatIntensity(5)).toBe("V (moderately strong)");
          expect(formatIntensity(4)).toBe("IV (moderate)");
     });

     it("reports MMI I as not felt rather than hiding it", () => {
          expect(formatIntensity(1)).toBe("I (not felt)");
     });

     it("clamps to the ends of the scale", () => {
          expect(formatIntensity(0.2)).toBe("I (not felt)");
          expect(formatIntensity(14)).toBe("XII (extreme)");
     });

     it("has nothing to say without a reading", () => {
          expect(formatIntensity(null)).toBeNull();
          expect(formatIntensity(undefined)).toBeNull();
     });
});

describe("formatMagnitude", () => {
     it("keeps the scale attached to the number", () => {
          expect(formatMagnitude(4.4, "mb")).toBe("M 4.4 mb");
     });

     it("prints no scale when the source named none", () => {
          // BMKG publishes a bare magnitude; inventing "mb" would be a claim
          // about method that the bulletin never made.
          expect(formatMagnitude(3.9, "m")).toBe("M 3.9");
          expect(formatMagnitude(3.9, null)).toBe("M 3.9");
     });

     it("does not label an unrecognised scale as if it were known", () => {
          expect(formatMagnitude(5, "other")).toBe("M 5");
     });
});

describe("formatImpact", () => {
     it("lists the figures a loss database recorded", () => {
          expect(
               formatImpact({
                    deaths: 100,
                    missing: null,
                    injured: 50,
                    displaced: 4600,
                    housesDestroyed: 327,
                    housesDamaged: null,
               }),
          ).toBe("100 deaths · 50 injured · 4,600 displaced · 327 houses destroyed");
     });

     it("inflects a count of one", () => {
          // "1 deaths" read as a bug and undercut the figure beside it.
          expect(
               formatImpact({
                    deaths: 1,
                    missing: null,
                    injured: null,
                    displaced: null,
                    housesDestroyed: 1,
                    housesDamaged: null,
               }),
          ).toBe("1 death · 1 house destroyed");
     });

     it("stays silent when a source published no figures", () => {
          expect(formatImpact(null)).toBeNull();
     });

     it("does not render reported zeros as impact", () => {
          // A recorded zero is real information, but "0 deaths" in a list of
          // events reads as reassurance the row cannot support.
          expect(
               formatImpact({
                    deaths: 0,
                    missing: 0,
                    injured: 0,
                    displaced: 0,
                    housesDestroyed: 0,
                    housesDamaged: 0,
               }),
          ).toBeNull();
     });
});

describe("DisasterSection", () => {
     it("leads a quake with what the ground did, then the magnitude", () => {
          render(() => <DisasterSection disasters={history([event()])} index={1} />);

          // The intensity sits in its own span (it carries a tooltip), so the
          // reading order is asserted on the metadata line that holds them all.
          const line = screen.getByText(/shaking VIII \(extremely strong\)/i).parentElement!;
          expect(line.textContent).toContain("M 5.6 mw");
          expect(line.textContent).toContain("10 km deep");
          expect(line.textContent!.indexOf("shaking")).toBeLessThan(
               line.textContent!.indexOf("M 5.6"),
          );
     });

     it("keeps the provider's own scale wording available", () => {
          render(() => <DisasterSection disasters={history([event()])} index={1} />);

          expect(screen.getByTitle("Scale as reported: mww")).toBeTruthy();
     });

     it("separates a modelled intensity from a witnessed one", () => {
          render(() =>
               <DisasterSection
                    disasters={history([event({ intensityBasis: "reported" })])}
                    index={1}
               />,
          );

          expect(
               screen.getByTitle(/from felt reports/),
          ).toBeTruthy();
     });

     it("shows the human cost of a flood that has no magnitude at all", () => {
          // The Tangerang case: 46 of the 91 recorded events there are floods,
          // and not one of them has a magnitude. Under the old markup a flood
          // rendered as a bare title.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({
                              type: "flood",
                              hazardTypes: ["flood"],
                              title: "Flood — Kota Tangerang",
                              magnitude: null,
                              magnitudeScale: null,
                              magnitudeScaleSource: null,
                              depthKm: null,
                              intensityMmi: null,
                              intensityBasis: null,
                              feltReports: null,
                              severity: null,
                              scope: "regional",
                              impact: {
                                   deaths: 5,
                                   missing: null,
                                   injured: 1,
                                   displaced: 23_200,
                                   housesDestroyed: null,
                                   housesDamaged: null,
                              },
                         }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText("5 deaths · 1 injured · 23,200 displaced")).toBeTruthy();
          expect(screen.queryByText(/shaking/i)).toBeNull();
          expect(screen.queryByText(/km deep/)).toBeNull();
     });

     it("prints the alert only when it carries information", () => {
          // PAGER runs on 99 Indonesian events a year and 96 come back green,
          // meaning "no significant impact expected" — a chip repeating that on
          // nearly every row was noise. Above green is the 3% worth reading.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ severity: "orange" }),
                         event({ id: "e2", severity: "green" }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText(/Orange alert/i)).toBeTruthy();
          expect(screen.queryByText(/Green alert/i)).toBeNull();
     });

     it("says nothing when the provider ran no estimate", () => {
          render(() =>
               <DisasterSection
                    disasters={history([event({ severity: null })])}
                    index={1}
               />,
          );

          expect(screen.queryByText(/alert/i)).toBeNull();
     });

     it("names what each figure is measured to, differently per scope", () => {
          // A measured epicentre really is that far from the pin. A district
          // record is not: only the district's centre is, so labelling it
          // "from pin" would claim a precision the row cannot support.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ distanceMeters: 24_000 }),
                         event({
                              id: "e2",
                              title: "Flood — Kota Jakarta Selatan",
                              areaName: "Kota Jakarta Selatan",
                              scope: "regional",
                              distanceMeters: 14_000,
                         }),
                         event({
                              id: "e3",
                              title: "Flood — Sigi",
                              areaName: "Sigi",
                              scope: "provincial",
                              distanceMeters: 63_000,
                         }),
                    ])}
                    index={1}
               />,
          );

          // One label for every row: the figure is the distance from the
          // coordinate the reader entered. The old per-scope labels named the
          // far end ("to district centre"), which stopped being true once area
          // records were measured against their boundary — Bogor's centre is
          // 30 km out while its edge is 5.9 km.
          expect(screen.getAllByText("from coordinate")).toHaveLength(3);
          expect(screen.queryByText(/centre/i)).toBeNull();
     });

     it("labels every row the same way, so one column is one frame", () => {
          // Mixing "from pin" on one row with "to district centre" on another
          // read as though only some distances started at the pin. Every figure
          // is measured from the pin, so the label names the far end.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ distanceMeters: 24_000 }),
                         event({ id: "e2", scope: "regional", distanceMeters: 14_000 }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.queryByText(/from pin/)).toBeNull();
          expect(screen.getAllByText("from coordinate")).toHaveLength(2);
     });

     it("does not call a GDACS centroid a district", () => {
          // Its coordinate is the centre of an affected region, not an
          // Indonesian administrative district.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ scope: "regional", areaName: null, source: "GDACS" }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText("from coordinate")).toBeTruthy();
     });

     it("anchors the search radius to the checked location", () => {
          render(() => <DisasterSection disasters={history([event()])} index={1} />);

          // The anchor has to be named, whichever word is used for it: without
          // it, "within 25 km" reads as a property of the rows rather than of
          // the search.
          expect(screen.getByText(/searched within/i).textContent).toMatch(
               /of your (pin|coordinate)/i,
          );
     });

     it("says an area holds the coordinate instead of printing zero", () => {
          // "0 m from coordinate" was true of the polygon and false of the
          // event: the archive stores no location inside a district — 0 of
          // 33,010 rows carry a coordinate — so zero claimed the event was at
          // the reader's feet.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({
                              type: "drought",
                              hazardTypes: ["drought"],
                              areaName: "Kota Tangerang Selatan",
                              title: "Drought — Kota Tangerang Selatan",
                              scope: "regional",
                              distanceMeters: 0,
                              distanceBasis: "area_edge",
                              magnitude: null,
                              intensityMmi: null,
                              severity: null,
                         }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText("Same district")).toBeTruthy();
          expect(screen.queryByText(/0 m/)).toBeNull();
          expect(screen.queryByText("from coordinate")).toBeNull();
     });

     it("still states the gap to a neighbouring area", () => {
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({
                              areaName: "Bogor",
                              title: "Landslide — Bogor",
                              scope: "regional",
                              distanceMeters: 5_900,
                              distanceBasis: "area_edge",
                         }),
                    ])}
                    index={1}
               />,
          );

          // A lower bound, not an estimate: the event lies inside that area, so
          // it cannot have been nearer than its closest edge.
          expect(screen.getByText("≥")).toBeTruthy();
          // The symbol is decoration to a screen reader, so the words have to
          // survive beside it — otherwise the bound is silently lost.
          expect(screen.getByText("at least")).toBeTruthy();
          expect(screen.getByText(/5\.9 km/)).toBeTruthy();
          expect(screen.queryByText(/~/)).toBeNull();
     });

     it("never says a measured epicentre is in this area", () => {
          // A point row's zero would mean the epicentre is exactly underfoot,
          // and its distance is a real measurement either way.
          render(() =>
               <DisasterSection
                    disasters={history([event({ scope: "point", distanceMeters: 0 })])}
                    index={1}
               />,
          );

          expect(screen.queryByText("Same district")).toBeNull();
          expect(screen.getByText("from coordinate")).toBeTruthy();
     });

     it("claims no bound when the figure is only a centroid", () => {
          // 2.1% of rows have no boundary in the source and fall back to an
          // area's centre. The event may be nearer than that, so "at least"
          // would be a false claim — those keep the hedge.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({
                              areaName: "Sigi",
                              title: "Flood — Sigi",
                              scope: "provincial",
                              distanceMeters: 63_000,
                              distanceBasis: "area_centre",
                         }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText("to area centre")).toBeTruthy();
          expect(screen.queryByText("≥")).toBeNull();
          expect(screen.getAllByText("~").length).toBeGreaterThan(0);
     });

     it("phrases each figure by what it measures", () => {
          // Three different claims in one column, so each has to say which it
          // is: an exact measurement, a lower bound, or an unbounded hedge.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ distanceMeters: 42_000, distanceBasis: "measured" }),
                         event({
                              id: "e2",
                              areaName: "Bogor",
                              title: "Flood — Bogor",
                              scope: "regional",
                              distanceMeters: 16_000,
                              distanceBasis: "area_edge",
                         }),
                         event({
                              id: "e3",
                              areaName: "Sigi",
                              title: "Flood — Sigi",
                              scope: "provincial",
                              distanceMeters: 63_000,
                              distanceBasis: "area_centre",
                         }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText("from coordinate")).toBeTruthy();
          expect(screen.getByText("≥")).toBeTruthy();
          expect(screen.getByText("to area centre")).toBeTruthy();
          // The hedge belongs to the unbounded row alone.
          expect(screen.getAllByText("~")).toHaveLength(1);
     });

     it("keeps the area-record caveat one click away", () => {
          render(() =>
               <DisasterSection
                    disasters={history([event({ scope: "regional" })])}
                    index={1}
               />,
          );

          // Folded into a `<details>`: it costs no vertical space above the
          // list, but its text is in the document — reachable by keyboard and
          // by in-page search, unlike the `title` attribute this once used,
          // which was invisible for a second and dead on a touch screen.
          expect(screen.getByText(/what these distances mean/i)).toBeTruthy();
          expect(
               screen.getByText(/not the actual location of the event/i),
          ).toBeTruthy();
          // The grouped layout was rejected; no group headings may return.
          expect(screen.queryByText(/measured locations/i)).toBeNull();
          expect(screen.queryByText(/district records/i)).toBeNull();
     });

     it("drops the caveat when every figure is measured", () => {
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ scope: "point", distanceBasis: "measured" }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.queryByText(/what these distances mean/i)).toBeNull();
     });

     it("drops the caveat when no row needs it", () => {
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({ scope: "point", distanceBasis: "measured" }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.queryByRole("note")).toBeNull();
     });

     it("does not name the catalogues beside the radius", () => {
          // Every row prints its own source, so a list of catalogues here only
          // repeated what sat underneath it.
          render(() =>
               <DisasterSection disasters={history([])} index={1} />,
          );

          expect(screen.queryByText(/^Searched: /)).toBeNull();
          expect(screen.getByText(/Searched within/)).toBeTruthy();
     });

     it("keeps a province-level row unbounded", () => {
          // Its figure is a centroid's, so no bound may be claimed in either
          // direction — the event could be nearer than the number.
          render(() =>
               <DisasterSection
                    disasters={history([
                         event({
                              scope: "provincial",
                              distanceMeters: 63_000,
                              distanceBasis: "area_centre",
                         }),
                    ])}
                    index={1}
               />,
          );

          expect(screen.getByText(/63 km/)).toBeTruthy();
          expect(screen.getByText("to area centre")).toBeTruthy();
          expect(screen.queryByText("≥")).toBeNull();
     });

     it("says nothing about impact when the catalogue counts nothing", () => {
          render(() => <DisasterSection disasters={history([event()])} index={1} />);

          expect(screen.queryByText(/deaths/)).toBeNull();
     });
});

describe("the search caption", () => {
     it("states both limits, not just the radius", () => {
          // A radius on its own reads as "everything ever recorded within
          // 25 km", which is a stronger claim than the search makes.
          render(() => <DisasterSection disasters={history([event()])} index={1} />);

          // Read from the fixture rather than hardcoded: the point is that both
          // figures appear, not what they happen to be set to.
          const caption = screen.getByText(/searched within/i).textContent ?? "";
          expect(caption).toMatch(/50 km/);
          expect(caption).toMatch(/last 25 years/i);
     });
});
