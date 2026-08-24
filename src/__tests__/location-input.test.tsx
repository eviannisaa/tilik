/**
 * Coordinate entry is the path someone uses when they already know the exact
 * spot, so it gets covered end to end: typing a value must select that point
 * without any geocoder round trip.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CoordinateInput from "../components/location/CoordinateInput";
import LocationInput from "../components/location/LocationInput";
import SelectedLocation from "../components/location/SelectedLocation";
import { displayStore, locationStore } from "../lib/store";

function stubFetch() {
  return vi.fn(
    async () =>
      new Response(JSON.stringify({ query: "", results: [], provider: "test", degraded: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
}

/** Paste is the default entry mode, so field-based tests switch over first. */
async function useFields() {
  fireEvent.click(screen.getByRole("button", { name: /type in fields/i }));
  await waitFor(() => expect(screen.getByLabelText("Latitude degrees")).toBeTruthy());
}

describe("CoordinateInput", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  /** Fill the structured fields for the format currently selected. */
  function typeDD(latitude: string, longitude: string) {
    fireEvent.input(screen.getByLabelText("Latitude degrees"), { target: { value: latitude } });
    fireEvent.input(screen.getByLabelText("Longitude degrees"), { target: { value: longitude } });
  }

  it("offers the notation before any typing, defaulting to DD", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    expect(screen.getByRole("radio", { name: "DD" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "DDM" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "DMS" })).toBeTruthy();
    expect(screen.getByText(/decimal degrees/i)).toBeTruthy();

    // DD has one box per axis: no minutes or seconds fields.
    expect(screen.getByLabelText("Latitude degrees")).toBeTruthy();
    expect(screen.queryByLabelText("Latitude minutes")).toBeNull();
    expect(screen.queryByLabelText("Latitude seconds")).toBeNull();
  });

  it("reshapes the fields for DDM and DMS", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    fireEvent.click(screen.getByRole("radio", { name: "DDM" }));
    await waitFor(() => expect(screen.getByLabelText("Latitude minutes")).toBeTruthy());
    expect(screen.queryByLabelText("Latitude seconds")).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(screen.getByLabelText("Latitude seconds")).toBeTruthy());
    expect(screen.getByLabelText("Latitude minutes")).toBeTruthy();
  });

  it("selects the point from DD fields", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    typeDD("6.9175", "107.6191");

    // Hemisphere is a toggle, so the sign can't be forgotten.
    fireEvent.click(screen.getByRole("radio", { name: "S" }));
    fireEvent.click(screen.getByRole("radio", { name: "E" }));
    fireEvent.click(screen.getByRole("button", { name: /use these coordinates/i }));

    await waitFor(() => expect(locationStore.selected()).not.toBeNull());
    expect(locationStore.selected()).toMatchObject({
      latitude: -6.9175,
      longitude: 107.6191,
      origin: "coordinates",
    });
  });

  it("selects the point from DMS fields", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(screen.getByLabelText("Latitude seconds")).toBeTruthy());

    fireEvent.input(screen.getByLabelText("Latitude degrees"), { target: { value: "6" } });
    fireEvent.input(screen.getByLabelText("Latitude minutes"), { target: { value: "55" } });
    fireEvent.input(screen.getByLabelText("Latitude seconds"), { target: { value: "3" } });
    fireEvent.input(screen.getByLabelText("Longitude degrees"), { target: { value: "107" } });
    fireEvent.input(screen.getByLabelText("Longitude minutes"), { target: { value: "37" } });
    fireEvent.input(screen.getByLabelText("Longitude seconds"), { target: { value: "8.76" } });
    fireEvent.click(screen.getByRole("radio", { name: "S" }));

    fireEvent.click(screen.getByRole("button", { name: /use these coordinates/i }));

    await waitFor(() => expect(locationStore.selected()).not.toBeNull());
    expect(locationStore.selected()!.latitude).toBeCloseTo(-6.9175, 4);
    expect(locationStore.selected()!.longitude).toBeCloseTo(107.6191, 4);
  });

  it("carries the value across a notation change", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    typeDD("6.9175", "107.6191");
    fireEvent.click(screen.getByRole("radio", { name: "S" }));

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));

    // Switching notation must re-express the point, not discard it.
    await waitFor(() =>
      expect((screen.getByLabelText("Latitude minutes") as HTMLInputElement).value).toBe("55"),
    );
    expect((screen.getByLabelText("Latitude degrees") as HTMLInputElement).value).toBe("6");
    expect((screen.getByLabelText("Latitude seconds") as HTMLInputElement).value).toBe("3");
  });

  it("shows all three notations once a point is complete", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    typeDD("6.9175", "107.6191");
    fireEvent.click(screen.getByRole("radio", { name: "S" }));

    await waitFor(() => expect(screen.getByText(/6\.91750° S · 107\.61910° E/)).toBeTruthy());
    expect(screen.getByText(/6° 55\.0500' S · 107° 37\.1460' E/)).toBeTruthy();
    expect(screen.getByText(/6° 55' 3\.00" S · 107° 37' 8\.76" E/)).toBeTruthy();
  });

  it("refuses out-of-range minutes rather than selecting a wrong point", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(screen.getByLabelText("Latitude minutes")).toBeTruthy());

    fireEvent.input(screen.getByLabelText("Latitude degrees"), { target: { value: "6" } });
    fireEvent.input(screen.getByLabelText("Latitude minutes"), { target: { value: "75" } });
    fireEvent.input(screen.getByLabelText("Longitude degrees"), { target: { value: "107" } });

    const submit = screen.getByRole("button", { name: /use these coordinates/i });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(locationStore.selected()).toBeNull();
  });

  it("still accepts a pasted string behind the paste toggle", async () => {
    render(() => <CoordinateInput />);
    const input = screen.getByLabelText(/latitude and longitude/i);
    fireEvent.input(input, { target: { value: "3.83359° N·96.85162° E" } });
    fireEvent.click(screen.getByRole("button", { name: /use these coordinates/i }));

    await waitFor(() => expect(locationStore.selected()?.latitude).toBe(3.83359));
  });

  it("reorders a longitude-first paste and says so", async () => {
    render(() => <CoordinateInput />);
    const input = screen.getByLabelText(/latitude and longitude/i);
    fireEvent.input(input, { target: { value: "107.6191, -6.9175" } });

    await waitFor(() => expect(screen.getByText(/read as longitude first/i)).toBeTruthy());
  });
});

describe("LocationInput", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("starts on place search and switches to coordinates", async () => {
    render(() => <LocationInput />);

    expect(screen.getByPlaceholderText(/search an address/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: /coordinates/i }));

    // Coordinates mode opens on the paste box, which is the default entry path.
    await waitFor(() => expect(screen.getByLabelText(/latitude and longitude/i)).toBeTruthy());
    expect(screen.queryByPlaceholderText(/search an address/i)).toBeNull();
  });

  it("keeps 'use my location' available in both modes", async () => {
    render(() => <LocationInput />);
    expect(screen.getByRole("button", { name: /use my location/i })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: /coordinates/i }));

    await waitFor(() => expect(screen.getByLabelText(/latitude and longitude/i)).toBeTruthy());
    expect(screen.getByRole("button", { name: /use my location/i })).toBeTruthy();
  });

  it("recognises coordinates pasted into the place field", async () => {
    render(() => <LocationInput />);
    const search = screen.getByPlaceholderText(/search an address/i);

    fireEvent.input(search, { target: { value: "3.76689, 96.78477" } });

    await waitFor(() => expect(screen.getByText(/use these coordinates/i)).toBeTruthy());
    fireEvent.click(screen.getByText(/use these coordinates/i));

    await waitFor(() => expect(locationStore.selected()?.longitude).toBe(96.78477));

    // The geocoder must not be asked to *search* for a coordinate pair. A
    // reverse lookup afterwards is fine — that's how the point gets a name.
    const searched = vi
      .mocked(fetch)
      .mock.calls.some(([input]) => String(input).includes("/api/location/search"));
    expect(searched).toBe(false);
  });
});

describe("coordinate conversion", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn() } });
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("switches the selected location's readout between formats", async () => {
    render(() => <SelectedLocation />);

    locationStore.select({
      latitude: -6.9175,
      longitude: 107.6191,
      name: "Bandung",
      origin: "coordinates",
    });

    await waitFor(() => expect(screen.getByText(/6\.91750° S/)).toBeTruthy());

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(screen.getByText(/6° 55' 3\.00" S/)).toBeTruthy());
    expect(screen.queryByText(/6\.91750° S/)).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "DDM" }));
    await waitFor(() => expect(screen.getByText(/6° 55\.0500' S/)).toBeTruthy());
  });

  it("copies the coordinate in the chosen format", async () => {
    render(() => <SelectedLocation />);
    locationStore.select({
      latitude: -6.9175,
      longitude: 107.6191,
      name: "Bandung",
      origin: "coordinates",
    });

    await waitFor(() => expect(screen.getByText(/6\.91750° S/)).toBeTruthy());
    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(screen.getByText(/6° 55' 3\.00" S/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /copy coordinates/i }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `6° 55' 3.00" S · 107° 37' 8.76" E`,
      ),
    );
  });
});

describe("placeholders follow the chosen notation", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const hint = (label: string) =>
    (screen.getByLabelText(label) as HTMLInputElement).placeholder;

  it("hints a signed decimal in DD", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    // Southern latitudes are written with a minus in DD, so the hint shows one.
    expect(hint("Latitude degrees")).toBe("-6.91750");
    expect(hint("Longitude degrees")).toBe("107.61910");
  });

  it("hints degrees and decimal minutes in DDM", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    fireEvent.click(screen.getByRole("radio", { name: "DDM" }));

    await waitFor(() => expect(screen.getByLabelText("Latitude minutes")).toBeTruthy());
    expect(hint("Latitude degrees")).toBe("6");
    expect(hint("Latitude minutes")).toBe("55.0500");
  });

  it("hints degrees, minutes and seconds in DMS", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));

    await waitFor(() => expect(screen.getByLabelText("Latitude seconds")).toBeTruthy());
    expect(hint("Latitude degrees")).toBe("6");
    expect(hint("Latitude minutes")).toBe("55");
    expect(hint("Latitude seconds")).toBe("3.00");
  });

  it("changes the paste placeholder with the notation", async () => {
    render(() => <CoordinateInput />);
    const box = screen.getByLabelText(/latitude and longitude/i);
    // DD pastes as a signed pair; the spelled-out notations use markers.
    expect((box as HTMLInputElement).placeholder).toBe("-6.91750, 107.61910");

    fireEvent.click(screen.getByRole("radio", { name: "DDM" }));
    await waitFor(() =>
      expect((screen.getByLabelText(/latitude and longitude/i) as HTMLInputElement).placeholder).toBe(
        "6° 55.0500' S · 107° 37.1460' E",
      ),
    );

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() =>
      expect((screen.getByLabelText(/latitude and longitude/i) as HTMLInputElement).placeholder).toBe(
        `6° 55' 3.00" S · 107° 37' 8.76" E`,
      ),
    );
  });
});

describe("DD accepts a signed value", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const latBox = () => screen.getByLabelText("Latitude degrees") as HTMLInputElement;

  it("selects a southern point from a negative number alone", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    // No hemisphere toggle touched: the sign has to be sufficient.
    fireEvent.input(latBox(), { target: { value: "-6.9175" } });
    fireEvent.input(screen.getByLabelText("Longitude degrees"), {
      target: { value: "107.6191" },
    });
    fireEvent.click(screen.getByRole("button", { name: /use these coordinates/i }));

    await waitFor(() => expect(locationStore.selected()).not.toBeNull());
    expect(locationStore.selected()).toMatchObject({
      latitude: -6.9175,
      longitude: 107.6191,
    });
  });

  it("moves the toggle to match a typed sign", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    fireEvent.input(latBox(), { target: { value: "-6.9175" } });
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "S" }).getAttribute("aria-checked")).toBe("true"),
    );

    fireEvent.input(latBox(), { target: { value: "6.9175" } });
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "N" }).getAttribute("aria-checked")).toBe("true"),
    );
  });

  it("flips the sign when the toggle is used instead", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    fireEvent.input(latBox(), { target: { value: "6.9175" } });
    fireEvent.click(screen.getByRole("radio", { name: "S" }));

    await waitFor(() => expect(latBox().value).toBe("-6.9175"));

    fireEvent.click(screen.getByRole("radio", { name: "N" }));
    await waitFor(() => expect(latBox().value).toBe("6.9175"));
  });

  it("hints the signed form and allows negative input", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    expect(latBox().placeholder).toBe("-6.91750");
    expect(latBox().min).toBe("-90");
    expect((screen.getByLabelText("Longitude degrees") as HTMLInputElement).min).toBe("-180");
    expect(screen.getByText(/negative value is enough/i)).toBeTruthy();
  });

  it("keeps DDM and DMS on magnitude plus a marker", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));

    await waitFor(() => expect(screen.getByLabelText("Latitude seconds")).toBeTruthy());
    // Those notations always spell the hemisphere out, so no negative degrees.
    expect(latBox().min).toBe("0");
    expect(latBox().placeholder).toBe("6");
    expect(screen.queryByText(/negative value is enough/i)).toBeNull();
  });
});

describe("switching notation converts what's entered", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const val = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;

  function enterBandungAsDD() {
    fireEvent.input(screen.getByLabelText("Latitude degrees"), { target: { value: "-6.9175" } });
    fireEvent.input(screen.getByLabelText("Longitude degrees"), {
      target: { value: "107.6191" },
    });
  }

  it("converts DD to DMS and back without drift", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    enterBandungAsDD();

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() => expect(val("Latitude seconds")).toBe("3"));
    expect(val("Latitude degrees")).toBe("6");
    expect(val("Latitude minutes")).toBe("55");
    expect(val("Longitude degrees")).toBe("107");
    expect(val("Longitude minutes")).toBe("37");
    expect(val("Longitude seconds")).toBe("8.76");
    expect(screen.getByRole("radio", { name: "S" }).getAttribute("aria-checked")).toBe("true");

    fireEvent.click(screen.getByRole("radio", { name: "DD" }));
    await waitFor(() => expect(val("Latitude degrees")).toBe("-6.9175"));
    expect(val("Longitude degrees")).toBe("107.6191");
  });

  it("converts DD to DDM", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    enterBandungAsDD();

    fireEvent.click(screen.getByRole("radio", { name: "DDM" }));
    await waitFor(() => expect(val("Latitude minutes")).toBe("55.05"));
    expect(val("Latitude degrees")).toBe("6");
    expect(val("Longitude minutes")).toBe("37.146");
  });

  it("converts through all three in sequence and returns to the start", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    enterBandungAsDD();

    for (const step of ["DDM", "DMS", "DD"]) {
      fireEvent.click(screen.getByRole("radio", { name: step }));
      await waitFor(() =>
        expect(screen.getByRole("radio", { name: step }).getAttribute("aria-checked")).toBe("true"),
      );
    }

    // A full round trip must land back on the value that was typed.
    await waitFor(() => expect(val("Latitude degrees")).toBe("-6.9175"));
    expect(val("Longitude degrees")).toBe("107.6191");
  });

  it("converts when the format is changed from elsewhere in the app", async () => {
    render(() => <CoordinateInput />);
    await useFields();
    enterBandungAsDD();

    // The selected-location card carries its own picker; a decimal degree left
    // in a whole-degrees box was the bug this covers.
    displayStore.setCoordinateFormat("dms");

    await waitFor(() => expect(val("Latitude degrees")).toBe("6"));
    expect(val("Latitude minutes")).toBe("55");
    expect(val("Latitude seconds")).toBe("3");
  });

  it("rewrites pasted text into the new notation", async () => {
    render(() => <CoordinateInput />);
    const box = screen.getByLabelText(/latitude and longitude/i) as HTMLInputElement;
    fireEvent.input(box, { target: { value: "-6.9175, 107.6191" } });

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));
    await waitFor(() =>
      expect((screen.getByLabelText(/latitude and longitude/i) as HTMLInputElement).value).toBe(
        `6° 55' 3.00" S · 107° 37' 8.76" E`,
      ),
    );

    fireEvent.click(screen.getByRole("radio", { name: "DD" }));
    await waitFor(() =>
      expect((screen.getByLabelText(/latitude and longitude/i) as HTMLInputElement).value).toBe(
        "-6.91750, 107.61910",
      ),
    );
  });

  it("leaves an empty form alone when the notation changes", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    fireEvent.click(screen.getByRole("radio", { name: "DMS" }));

    await waitFor(() => expect(screen.getByLabelText("Latitude seconds")).toBeTruthy());
    expect(val("Latitude degrees")).toBe("");
    expect(screen.getByRole("button", { name: /use these coordinates/i })).toHaveProperty(
      "disabled",
      true,
    );
  });
});

describe("single-row layout", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders exactly one submit button in each mode", async () => {
    render(() => <CoordinateInput />);

    // The fields and paste branches each carry their own button; only one of
    // them may ever be mounted.
    expect(screen.getByLabelText(/latitude and longitude/i)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /use these coordinates/i })).toHaveLength(1);

    await useFields();
    expect(screen.getAllByRole("button", { name: /use these coordinates/i })).toHaveLength(1);
  });

  it("keeps both axes and the action in one group", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    const latitude = screen.getByLabelText("Latitude degrees");
    const longitude = screen.getByLabelText("Longitude degrees");
    const go = screen.getByRole("button", { name: /use these coordinates/i });

    // Each axis is a group; the groups and the button must be siblings, which is
    // what puts them on one line instead of stacking.
    const latGroup = latitude.closest("div")!.parentElement!;
    const lngGroup = longitude.closest("div")!.parentElement!;

    expect(latGroup).not.toBe(lngGroup);
    expect(latGroup.parentElement).toBe(lngGroup.parentElement);
    expect(go.parentElement).toBe(latGroup.parentElement);
  });

  it("shows short axis labels so the row fits", async () => {
    render(() => <CoordinateInput />);
    await useFields();

    expect(screen.getByText("Latitude")).toBeTruthy();
    expect(screen.getByText("Longitude")).toBeTruthy();
    // The full names stay as accessible labels.
    expect(screen.getByLabelText("Latitude degrees")).toBeTruthy();
    expect(screen.getByLabelText("Longitude degrees")).toBeTruthy();
  });
});

describe("paste is the default entry mode", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubFetch());
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("opens on the paste box, not the field grid", () => {
    render(() => <CoordinateInput />);

    expect(screen.getByLabelText(/latitude and longitude/i)).toBeTruthy();
    expect(screen.queryByLabelText("Latitude degrees")).toBeNull();
    // The toggle offers the other direction.
    expect(screen.getByRole("button", { name: /type in fields/i })).toBeTruthy();
  });

  it("selects a point straight from a paste with no mode change", async () => {
    render(() => <CoordinateInput />);

    fireEvent.input(screen.getByLabelText(/latitude and longitude/i), {
      target: { value: "3.71645, 96.82016" },
    });
    fireEvent.click(screen.getByRole("button", { name: /use these coordinates/i }));

    await waitFor(() => expect(locationStore.selected()).not.toBeNull());
    expect(locationStore.selected()).toMatchObject({
      latitude: 3.71645,
      longitude: 96.82016,
      origin: "coordinates",
    });
  });

  it("can go to the fields and back", async () => {
    render(() => <CoordinateInput />);

    await useFields();
    expect(screen.queryByLabelText(/latitude and longitude/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /paste instead/i }));
    await waitFor(() => expect(screen.getByLabelText(/latitude and longitude/i)).toBeTruthy());
    expect(screen.queryByLabelText("Latitude degrees")).toBeNull();
  });
});
