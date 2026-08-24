/**
 * The map is limited to Indonesia because every source behind the report is.
 *
 * The hazard layers, the disaster archive and the boundary polygons all stop at
 * the same box, so a pin dropped in Australia or the Philippines produces a
 * report with nothing in it. A map that roams there offers a check the app
 * cannot answer.
 *
 * What a rectangle can and cannot do is the interesting part, and the tests say
 * so rather than pretending otherwise.
 */

import { describe, expect, it } from "vitest";
import { INDONESIA_BOUNDS, MIN_ZOOM } from "../lib/config";

const [[west, south], [east, north]] = INDONESIA_BOUNDS;

function contains(lng: number, lat: number): boolean {
     return lng >= west && lng <= east && lat >= south && lat <= north;
}

/** Indonesia's outermost inhabited points, plus a few cities. */
const REACHABLE: [string, number, number][] = [
     ["Pulau Rondo, the westernmost point", 95.11, 6.07],
     ["Merauke, near the easternmost", 140.4, -8.49],
     ["Pulau Miangas, the northernmost", 126.59, 5.57],
     ["Pulau Rote, the southernmost", 123.12, -10.93],
     ["Jakarta", 106.85, -6.21],
     ["Jayapura", 140.72, -2.53],
     ["Banda Aceh", 95.32, 5.55],
];

/** Outside the archipelago, and excludable by a rectangle. */
const OUT_OF_REACH: [string, number, number][] = [
     ["Manila", 120.98, 14.6],
     ["Darwin", 130.84, -12.46],
     ["Bangkok", 100.5, 13.76],
     ["Perth", 115.86, -31.95],
     ["Port Moresby", 147.15, -9.44],
];

/**
 * Enclosed by the archipelago, so no rectangle can exclude them.
 *
 * Malaysia and Singapore sit between Sumatra and Borneo; Timor-Leste sits inside
 * Nusa Tenggara. Clipping the box to cut them out would cut off Indonesian
 * islands with them, which is the worse trade. The report's own coverage check is
 * what answers for a point there.
 */
const UNAVOIDABLY_INSIDE: [string, number, number][] = [
     ["Kuala Lumpur", 101.69, 3.14],
     ["Singapore", 103.82, 1.35],
     ["Bandar Seri Begawan", 114.94, 4.89],
     ["Dili", 125.56, -8.56],
];

describe("INDONESIA_BOUNDS", () => {
     it.each(REACHABLE)("reaches %s", (_name, lng, lat) => {
          expect(contains(lng, lat)).toBe(true);
     });

     it.each(OUT_OF_REACH)("stops short of %s", (_name, lng, lat) => {
          expect(contains(lng, lat)).toBe(false);
     });

     it.each(UNAVOIDABLY_INSIDE)(
          "cannot exclude %s, and the box does not pretend to",
          (_name, lng, lat) => {
               expect(contains(lng, lat)).toBe(true);
          },
     );

     it("is ordered as MapLibre expects: south-west corner first", () => {
          expect(west).toBeLessThan(east);
          expect(south).toBeLessThan(north);
     });

     it("floors the zoom, so the country cannot shrink to a smear", () => {
          // `maxBounds` alone still allows zooming out until Indonesia is a
          // speck in an ocean of empty tiles, which reads as broken rather than
          // bounded.
          expect(MIN_ZOOM).toBeGreaterThanOrEqual(3);
          expect(MIN_ZOOM).toBeLessThan(8);
     });
});
