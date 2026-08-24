/**
 * Nominatim does not use one key per Indonesian administrative level.
 *
 * Around Tangerang the kecamatan arrives as `district` and the kota as `city`.
 * In Palu the two are swapped: `district` holds "Palu", the kota, and `city`
 * holds "Kecamatan Palu Timur". Printing the fields in a fixed order gets Palu
 * exactly backwards, which is worse than printing nothing.
 */

import { describe, expect, it } from "vitest";
import { adminChain } from "../lib/format";

describe("adminChain", () => {
     it("keeps the geocoder's order when the keys line up", () => {
          expect(
               adminChain({
                    district: "Serpong",
                    city: "Tangerang Selatan",
                    province: "Banten",
               }),
          ).toEqual(["Serpong", "Tangerang Selatan", "Banten"]);
     });

     it("reorders when the value names its own level", () => {
          // The real Palu response. "Kecamatan" in the string outranks the key it
          // arrived under.
          expect(
               adminChain({
                    district: "Palu",
                    city: "Kecamatan Palu Timur",
                    province: "Sulawesi Tengah",
               }),
          ).toEqual(["Kecamatan Palu Timur", "Palu", "Sulawesi Tengah"]);
     });

     it("treats Kabupaten and Kota as the level above a kecamatan", () => {
          expect(
               adminChain({
                    district: "Kabupaten Sleman",
                    city: "Kecamatan Depok",
                    province: "DI Yogyakarta",
               }),
          ).toEqual(["Kecamatan Depok", "Kabupaten Sleman", "DI Yogyakarta"]);
     });

     it("drops a repeat rather than printing it twice", () => {
          // Palu arrives as both locality and district.
          expect(
               adminChain({ district: "Palu", city: "Palu", province: "Sulawesi Tengah" }),
          ).toEqual(["Palu", "Sulawesi Tengah"]);
     });

     it("ignores case and stray whitespace when deduplicating", () => {
          expect(
               adminChain({ district: " Bogor ", city: "BOGOR", province: "Jawa Barat" }),
          ).toEqual(["Bogor", "Jawa Barat"]);
     });

     it("skips the levels the geocoder did not fill", () => {
          expect(
               adminChain({ district: null, city: "Kota Semarang", province: null }),
          ).toEqual(["Kota Semarang"]);
     });

     it("returns nothing rather than an empty label", () => {
          expect(adminChain({ district: null, city: "", province: "   " })).toEqual([]);
     });
});

describe("filling the chain from a selection", () => {
     /**
      * Two paths reach the heading and only one of them used to fill it.
      *
      * `select` triggered a reverse lookup when the point had no name, which is
      * the map-click case. A search result arrives with a name, so the lookup
      * never ran, so the administrative line under the heading stayed blank for
      * exactly the path most people use.
      */
     it("takes the chain straight from a search result", async () => {
          const { locationStore } = await import("../lib/store");

          locationStore.select({
               latitude: -6.3,
               longitude: 106.68,
               name: "Serpong",
               origin: "search",
               district: "Serpong",
               city: "Tangerang Selatan",
               province: "Banten",
          });

          expect(adminChain(locationStore.selected()!)).toEqual([
               "Serpong",
               "Tangerang Selatan",
               "Banten",
          ]);
          locationStore.clear();
     });

     it("has nothing to show for a bare map click, until the lookup lands", async () => {
          const { locationStore } = await import("../lib/store");

          locationStore.select({
               latitude: -6.3,
               longitude: 106.68,
               name: null,
               origin: "map",
          });

          expect(adminChain(locationStore.selected()!)).toEqual([]);
          locationStore.clear();
     });
});
