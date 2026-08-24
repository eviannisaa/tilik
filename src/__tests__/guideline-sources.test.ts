/**
 * The guideline's source table has to name what the app actually queries.
 *
 * It listed "Other disasters: GDACS", which was removed outright: its
 * coordinates are centroids of affected regions rather than places, and it
 * publishes no casualty figures. Three sources replaced it, each with a
 * different limit, and a table that names the wrong one is worse than no table.
 *
 * It also has to state where the archive stops. The DesInventar mirror holds
 * 32,447 records from 1815 to 2019 and then ends, so an empty disaster history
 * for 2020 onwards says nothing about the land.
 */

import { describe, expect, it } from "vitest";

const GUIDELINE = import.meta.glob("../pages/guideline.astro", {
     query: "?raw",
     import: "default",
     eager: true,
}) as Record<string, string>;

/**
 * Reader-facing text only. Comments are for whoever reads the source, and one of
 * them names GDACS precisely to record that it was removed.
 */
const PAGE = (Object.values(GUIDELINE)[0] ?? "")
     .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
     .replace(/\/\*[\s\S]*?\*\//g, "")
     .replace(/^\s*\/\/.*$/gm, "");

describe("the guideline source table", () => {
     it("was read at all", () => {
          expect(PAGE.length).toBeGreaterThan(1000);
     });

     it("no longer credits GDACS", () => {
          // Removed from the disaster history entirely, not merely demoted.
          expect(PAGE).not.toContain("GDACS");
     });

     it.each([
          ["BNPB InaRISK", "hazard indices"],
          ["USGS", "earthquakes"],
          ["NOAA", "tsunamis"],
          ["DesInventar", "the archive behind every other hazard"],
          ["Nominatim", "place search"],
          ["Overpass", "nearby places"],
          ["OpenTopography", "elevation"],
          ["PostGIS", "the local store"],
          ["MapLibre", "the map"],
     ])("names %s, for %s", (source) => {
          expect(PAGE).toContain(source);
     });

     it("says where the archive stops, in prose and not only in a cell", () => {
          expect(PAGE).toContain("stops at the end of 2019");
          expect(PAGE).toContain("32,447");
     });

     it("says which hazards are unaffected by that cut-off", () => {
          // Otherwise the reader discounts the whole section, including the two
          // sources that are current.
          const note = PAGE.slice(PAGE.indexOf("stops at the end of 2019"));
          expect(note).toMatch(/earthquakes and tsunamis are not affected/i);
     });

     it("no longer says the archive is missing until someone imports it", () => {
          // It is imported. The limit now is its end date, not its absence.
          expect(PAGE).not.toContain("unless someone imports them");
     });
});
