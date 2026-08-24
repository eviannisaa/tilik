/**
 * A distance in this column belongs to the place named beside it.
 *
 * The column used to read "658 m×6": the distance described one place — the
 * nearest — while the count described every place in the category inside the
 * 1.5 km radius. Set flush against each other the two read as arithmetic, and
 * the number that mattered stopped being attached to the name it belonged to.
 */

import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import PlacesSection from "../components/report/PlacesSection";
import type { NearbyPlaces } from "../lib/types";

afterEach(cleanup);

function places(overrides: Partial<NearbyPlaces> = {}): NearbyPlaces {
     return {
          radiusMeters: 1_500,
          total: 137,
          confidence: "high",
          note: null,
          categories: [
               {
                    key: "health",
                    label: "Health",
                    count: 6,
                    nearest: {
                         name: "Rumah Sakit Bhayangkara",
                         kind: "hospital",
                         category: "health",
                         distanceMeters: 658,
                    },
                    places: [
                         {
                              name: "Rumah Sakit Bhayangkara",
                              kind: "hospital",
                              category: "health",
                              distanceMeters: 658,
                         },
                    ],
               },
          ],
          ...overrides,
     };
}

describe("PlacesSection", () => {
     it("summarises a category without opening it", () => {
          render(() => <PlacesSection places={places()} index={1} />);

          // The count is what a closed row has to carry: without it, five
          // clinics inside 1.5 km and fourteen look identical, which is the
          // difference the section exists to show.
          const summary = screen.getByText("Health").closest("summary");
          // Matched on the count's own element: `textContent` runs the
          // label straight into it as "Health6".
          expect(screen.getByText(/^6\b/)).toBeTruthy();
          // The reach is stated once in the caption, so each row need not repeat
          // it.
          expect(screen.getByText(/mapped place/i).textContent).toMatch(/1\.5 km/);
          // The count glyph must not come back: "658 m×6" read as a
          // multiplication, and the two numbers describe different things.
          expect(screen.queryByText(/×/)).toBeNull();
     });

     it("still states how many were found, and over what reach", () => {
          // Removing the per-row count is only safe because the total and the
          // radius are stated once, above the table.
          render(() => <PlacesSection places={places()} index={1} />);

          const caption = screen.getByText(/mapped place/i).textContent ?? "";
          expect(caption).toMatch(/137/);
          expect(caption).toMatch(/1\.5 km/);
     });

     it("lists every place in a category once it is opened", () => {
          // The whole point: five clinics inside 1.5 km and fourteen inside
          // 1.5 km are different places to buy land, and one row each made them
          // look identical.
          render(() =>
               <PlacesSection
                    places={places({
                         categories: [
                              {
                                   key: "health",
                                   label: "Health",
                                   count: 3,
                                   nearest: {
                                        name: "RS Woodward Palu",
                                        kind: "hospital",
                                        category: "health",
                                        distanceMeters: 579,
                                   },
                                   places: [
                                        {
                                             name: "RS Woodward Palu",
                                             kind: "hospital",
                                             category: "health",
                                             distanceMeters: 579,
                                        },
                                        {
                                             name: "RS Budi Agung",
                                             kind: "hospital",
                                             category: "health",
                                             distanceMeters: 1017,
                                        },
                                        {
                                             name: "Rumah Sakit Bhayangkara",
                                             kind: "hospital",
                                             category: "health",
                                             distanceMeters: 1068,
                                        },
                                   ],
                              },
                         ],
                    })}
                    index={1}
               />,
          );

          fireEvent.click(
               screen.getByText("Health").closest("summary")!,
          );

          expect(screen.getByText("RS Woodward Palu")).toBeTruthy();
          expect(screen.getByText("RS Budi Agung")).toBeTruthy();
          expect(screen.getByText("Rumah Sakit Bhayangkara")).toBeTruthy();
          // Each with its own real distance, not the nearest one repeated.
          // Scoped to the list: "579 m" also appears in the summary as the
          // nearest, which is the point of putting it there.
          const rows = screen.getByText("Health").closest("details")!
               .querySelector("ul")!;
          expect(rows.textContent).toMatch(/579 m/);
          expect(rows.textContent).toMatch(/1\.0 km/);
          expect(rows.textContent).toMatch(/1\.1 km/);
     });

     it("counts in words, never with a multiplication sign", () => {
          // "658 m×6" set a count flush against a distance and read as
          // arithmetic. Whatever the wording, the glyph must not come back.
          render(() => <PlacesSection places={places()} index={1} />);

          const summary = screen.getByText("Health").closest("summary")!;
          expect(screen.getByText(/^6\b/)).toBeTruthy();
          expect(summary.textContent).not.toMatch(/×/);
     });

     it("marks a category with nothing found rather than leaving it blank", () => {
          render(() =>
               <PlacesSection
                    places={places({
                         categories: [
                              {
                                   key: "safety",
                                   label: "Safety",
                                   count: 0,
                                   nearest: null,
                                   places: [],
                              },
                         ],
                    })}
                    index={1}
               />,
          );

          // An empty list would read as a rendering fault rather than an
          // absence.
          expect(screen.getByText("—")).toBeTruthy();
     });
});

describe("when the lookup did not happen", () => {
     /**
      * A failed request and an empty area are opposite findings.
      *
      * Overpass returns 504 often enough that this is a normal state, not an
      * edge case. The section used to render "0 mapped places within 1.5 km"
      * over "Nothing mapped around this point", with the real reason —
      * "OpenStreetMap didn't answer" — in smaller type underneath. Every part of
      * that except the last line asserted something nobody knew.
      */
     const failed = (): NearbyPlaces => ({
          radiusMeters: 1_500,
          total: 0,
          confidence: "none",
          note: "OpenStreetMap didn't answer, so we couldn't list what's nearby.",
          categories: [],
     });

     it("does not report a count it never counted", () => {
          render(() => <PlacesSection places={failed()} index={1} />);

          expect(screen.queryByText(/0 mapped places/i)).toBeNull();
          expect(screen.getByText(/not checked/i)).toBeTruthy();
     });

     it("says we could not check, not that there is nothing", () => {
          render(() => <PlacesSection places={failed()} index={1} />);

          expect(screen.getByText(/couldn't check what's nearby/i)).toBeTruthy();
          expect(screen.queryByText(/nothing mapped around this point/i)).toBeNull();
          // The provider's own reason still shows.
          expect(screen.getByText(/didn't answer/i)).toBeTruthy();
     });

     it("still says nothing is mapped when the provider did answer", () => {
          render(() =>
               <PlacesSection
                    places={{ ...failed(), confidence: "low", note: null }}
                    index={1}
               />,
          );

          expect(screen.getByText(/nothing mapped around this point/i)).toBeTruthy();
          expect(screen.getByText(/0 mapped places/i)).toBeTruthy();
     });
});

describe("the show-all control", () => {
     /**
      * Every place is in the payload; the view is what holds back.
      *
      * The API used to truncate to three per category and the section rendered
      * one, so a reader could not reach the rest at all. Capping the view is
      * only honest because each category heading states its true count, and
      * because this button actually opens the whole list.
      */
     const busy = (): NearbyPlaces => ({
          radiusMeters: 1_500,
          // Deliberately not 5: with the section total equal to the category
          // count, a matcher for one silently matches the other.
          total: 12,
          confidence: "high",
          note: null,
          categories: [
               {
                    key: "health",
                    label: "Health",
                    count: 5,
                    nearest: {
                         name: "RS Woodward Palu",
                         kind: "hospital",
                         category: "health",
                         distanceMeters: 579,
                    },
                    places: [1, 2, 3, 4, 5].map((n) => ({
                         name: `Clinic ${n}`,
                         kind: "clinic",
                         category: "health",
                         distanceMeters: n * 100,
                    })),
               },
          ],
     });

     it("starts closed, stating the count rather than the rows", () => {
          render(() => <PlacesSection places={busy()} index={1} />);

          const details = screen.getByText("Health").closest("details");
          expect(details?.open).toBe(false);
          // Closed, but not silent about what it holds.
          expect(screen.getByText(/^5\b/)).toBeTruthy();
          // Deliberately not asserting the rows are absent from the document.
          // A closed `<details>` still contains them — the browser hides them —
          // and that is the property worth having: their text stays findable by
          // in-page search, unlike content held back in a signal.
          expect(details?.querySelector("ul")).toBeTruthy();
     });

     it("gives every category its own control", () => {
          // One button for the whole section would cost more height than the
          // rows it hid, and would open all 116 at once.
          render(() => <PlacesSection places={busy()} index={1} />);

          expect(screen.queryByRole("button", { name: /show all/i })).toBeNull();
          expect(screen.getByText("Health").closest("details")).toBeTruthy();
     });

     it("opens onto every place in that category, not the first three", () => {
          render(() => <PlacesSection places={busy()} index={1} />);

          const details = screen.getByText("Health").closest("details")!;
          fireEvent.click(details.querySelector("summary")!);

          for (const n of [1, 2, 3, 4, 5]) {
               expect(screen.getByText(`Clinic ${n}`)).toBeTruthy();
          }
     });
});
