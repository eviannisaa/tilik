import { describe, expect, it } from "vitest";
import {
  COORDINATE_FORMATS,
  EXAMPLE_POINT,
  examplePair,
  examplePlaceholders,
  formatAxis,
  formatPair,
  formatSignedPair,
  fromParts,
  looksLikeCoordinates,
  parseCoordinates,
  splitAxis,
} from "../lib/coordinates";

describe("parseCoordinates", () => {
  it("reads plain decimal pairs", () => {
    expect(parseCoordinates("-6.9175, 107.6191")).toEqual({
      latitude: -6.9175,
      longitude: 107.6191,
      swapped: false,
    });
    expect(parseCoordinates("-6.9175 107.6191")?.latitude).toBe(-6.9175);
    expect(parseCoordinates("-6.9175;107.6191")?.longitude).toBe(107.6191);
    expect(parseCoordinates("3.83359,96.85162")?.latitude).toBe(3.83359);
  });

  it("round-trips this app's own readout format", () => {
    // The report renders coordinates exactly like this, so copying a value out
    // of it and pasting it back must work.
    expect(parseCoordinates("3.83359° N·96.85162° E")).toEqual({
      latitude: 3.83359,
      longitude: 96.85162,
      swapped: false,
    });
    expect(parseCoordinates("6.91750° S · 107.61910° E")).toEqual({
      latitude: -6.9175,
      longitude: 107.6191,
      swapped: false,
    });
  });

  it("honours hemisphere letters before or after the number", () => {
    expect(parseCoordinates("3.83359 N, 96.85162 E")?.latitude).toBe(3.83359);
    expect(parseCoordinates("N 3.83359, E 96.85162")?.latitude).toBe(3.83359);
    expect(parseCoordinates("7.7956 S, 110.3695 E")?.latitude).toBe(-7.7956);
    expect(parseCoordinates("0.9471S 100.4172E")?.latitude).toBe(-0.9471);
  });

  it("reads degrees-minutes-seconds", () => {
    const parsed = parseCoordinates("6°55'3\"S 107°37'9\"E");
    expect(parsed?.latitude).toBeCloseTo(-6.9175, 3);
    expect(parsed?.longitude).toBeCloseTo(107.61917, 3);
  });

  it("reads degrees and decimal minutes", () => {
    const parsed = parseCoordinates("6°55.05'S 107°37.15'E");
    expect(parsed?.latitude).toBeCloseTo(-6.9175, 3);
    expect(parsed?.longitude).toBeCloseTo(107.61917, 3);
  });

  it("reorders a longitude-first pair and says so", () => {
    // GeoJSON and WKT are lng-first, so this paste is common.
    expect(parseCoordinates("107.6191, -6.9175")).toEqual({
      latitude: -6.9175,
      longitude: 107.6191,
      swapped: true,
    });
    expect(parseCoordinates("107.6191 E, 6.9175 S")).toEqual({
      latitude: -6.9175,
      longitude: 107.6191,
      swapped: true,
    });
  });

  it("keeps an ambiguous in-range pair in the order given", () => {
    // Both values are valid latitudes, so guessing would be worse than obeying.
    expect(parseCoordinates("3.5, 4.5")).toEqual({
      latitude: 3.5,
      longitude: 4.5,
      swapped: false,
    });
  });

  it("rejects anything off-planet or incomplete", () => {
    expect(parseCoordinates("")).toBeNull();
    expect(parseCoordinates("Bandung")).toBeNull();
    expect(parseCoordinates("-6.9175")).toBeNull();
    expect(parseCoordinates("999, 999")).toBeNull();
    expect(parseCoordinates("91, 200")).toBeNull();
  });

  it("accepts the exact coordinates from the Aceh checks", () => {
    expect(parseCoordinates("3.71645, 96.82016")?.latitude).toBe(3.71645);
    expect(parseCoordinates("3.76689, 96.78477")?.longitude).toBe(96.78477);
  });
});

describe("looksLikeCoordinates", () => {
  it("recognises coordinate-shaped input", () => {
    expect(looksLikeCoordinates("-6.9175, 107.6191")).toBe(true);
    expect(looksLikeCoordinates("3.83359° N·96.85162° E")).toBe(true);
    expect(looksLikeCoordinates("6°55'3\"S 107°37'9\"E")).toBe(true);
  });

  it("leaves place names to the geocoder", () => {
    expect(looksLikeCoordinates("Bandung")).toBe(false);
    expect(looksLikeCoordinates("Jalan Merdeka 12")).toBe(false);
    expect(looksLikeCoordinates("-6.91")).toBe(false);
  });
});

describe("coordinate formatting", () => {
  const CASES: Array<[number, number]> = [
    [-6.9175, 107.6191],
    [3.83359, 96.85162],
    [3.71645, 96.82016],
    [-8.6705, 115.2126],
    [5.5483, 95.3238],
    [0, 0],
    [-0.9471, 100.4172],
  ];

  it("writes decimal degrees with a hemisphere", () => {
    expect(formatAxis(-6.9175, "lat", "dd")).toBe("6.91750° S");
    expect(formatAxis(107.6191, "lng", "dd")).toBe("107.61910° E");
    expect(formatAxis(3.83359, "lat", "dd")).toBe("3.83359° N");
  });

  it("writes degrees and decimal minutes", () => {
    expect(formatAxis(-6.9175, "lat", "ddm")).toBe("6° 55.0500' S");
    expect(formatAxis(107.6191, "lng", "ddm")).toBe("107° 37.1460' E");
  });

  it("writes degrees, minutes and seconds", () => {
    expect(formatAxis(-6.9175, "lat", "dms")).toBe(`6° 55' 3.00" S`);
    expect(formatAxis(107.6191, "lng", "dms")).toBe(`107° 37' 8.76" E`);
  });

  it("carries the rounding instead of printing 60", () => {
    // 6.99999992° is 6° 59' 59.9997"; naive rounding would print 60.00".
    expect(formatAxis(6.99999992, "lat", "dms")).toBe(`7° 0' 0.00" N`);
    expect(formatAxis(6.9999999, "lat", "ddm")).toBe("7° 0.0000' N");
  });

  it("round-trips through every format", () => {
    // The formats are only useful if a value written in one can be read back.
    for (const [latitude, longitude] of CASES) {
      for (const format of COORDINATE_FORMATS) {
        const text = formatPair(latitude, longitude, format);
        const parsed = parseCoordinates(text);

        expect(parsed, `${format}: ${text}`).not.toBeNull();
        expect(parsed!.latitude, `${format} lat: ${text}`).toBeCloseTo(latitude, 4);
        expect(parsed!.longitude, `${format} lng: ${text}`).toBeCloseTo(longitude, 4);
      }
    }
  });

  it("keeps the southern and western signs through a round trip", () => {
    const text = formatPair(-8.6705, -70.1234, "dms");
    expect(text).toContain("S");
    expect(text).toContain("W");

    const parsed = parseCoordinates(text)!;
    expect(parsed.latitude).toBeLessThan(0);
    expect(parsed.longitude).toBeLessThan(0);
  });
});

describe("Indonesian notation", () => {
  it("applies LS and BT as hemisphere markers", () => {
    // Ignoring LS silently produced +35 instead of −35 — the wrong hemisphere.
    expect(parseCoordinates("35° LS, 119,87° BT")).toEqual({
      latitude: -35,
      longitude: 119.87,
      swapped: false,
    });
    expect(parseCoordinates("6,9175° LS 107,6191° BT")).toEqual({
      latitude: -6.9175,
      longitude: 107.6191,
      swapped: false,
    });
  });

  it("handles LU and BB too", () => {
    expect(parseCoordinates("3,83359° LU, 96,85162° BT")).toEqual({
      latitude: 3.83359,
      longitude: 96.85162,
      swapped: false,
    });
    expect(parseCoordinates("12,5° LU, 70,25° BB")).toEqual({
      latitude: 12.5,
      longitude: -70.25,
      swapped: false,
    });
  });

  it("accepts the markers spelled out", () => {
    expect(parseCoordinates("6,9175 Lintang Selatan, 107,6191 Bujur Timur")?.latitude).toBe(
      -6.9175,
    );
    expect(parseCoordinates("3,83 Lintang Utara 96,85 Bujur Timur")?.latitude).toBe(3.83);
  });

  it("reads comma decimals without breaking dot decimals", () => {
    expect(parseCoordinates("0,9° LS, 119,87° BT")).toEqual({
      latitude: -0.9,
      longitude: 119.87,
      swapped: false,
    });
    // A dot decimal means commas are separators, not decimal points.
    expect(parseCoordinates("-6.9175, 107.6191")?.latitude).toBe(-6.9175);
    expect(parseCoordinates("-6.9175,107.6191")?.longitude).toBe(107.6191);
  });

  it("still reads a plain integer pair as two values", () => {
    // No decimals anywhere, so the comma has to be the separator.
    expect(parseCoordinates("35 LS, 119 BT")).toEqual({
      latitude: -35,
      longitude: 119,
      swapped: false,
    });
  });

  it("treats Indonesian markers as coordinate-shaped input", () => {
    expect(looksLikeCoordinates("35° LS, 119,87° BT")).toBe(true);
    expect(looksLikeCoordinates("6,9175 LS 107,6191 BT")).toBe(true);
    expect(looksLikeCoordinates("Blang Pidie")).toBe(false);
  });
});

describe("regression: the wrong-hemisphere bug", () => {
  it("never drops an Indonesian hemisphere marker", () => {
    // `35° LS` once parsed as +35: the Southern Ocean read as inland China.
    // Any marker being ignored puts a plot on the wrong side of the equator or
    // meridian, so assert the sign explicitly for all four.
    expect(parseCoordinates("35° LS, 119,87° BT")!.latitude).toBeLessThan(0);
    expect(parseCoordinates("35° LU, 119,87° BT")!.latitude).toBeGreaterThan(0);
    expect(parseCoordinates("35° LS, 119,87° BB")!.longitude).toBeLessThan(0);
    expect(parseCoordinates("35° LS, 119,87° BT")!.longitude).toBeGreaterThan(0);
  });

  it("never silently truncates a comma decimal", () => {
    // `119,87` once became `119`, losing 96 km of longitude.
    expect(parseCoordinates("35° LS, 119,87° BT")!.longitude).toBe(119.87);
    expect(parseCoordinates("0,9° LS, 119,87° BT")!.latitude).toBe(-0.9);
  });
});

describe("structured field entry", () => {
  it("splits a value into the fields each format needs", () => {
    // DD has one box per axis and keeps the sign, since that's how it's written.
    expect(splitAxis(-6.9175, "lat", "dd")).toEqual({
      degrees: -6.9175,
      minutes: 0,
      seconds: 0,
      hemisphere: "S",
    });
    expect(splitAxis(-6.9175, "lat", "ddm")).toMatchObject({
      degrees: 6,
      minutes: 55.05,
      hemisphere: "S",
    });
    expect(splitAxis(-6.9175, "lat", "dms")).toEqual({
      degrees: 6,
      minutes: 55,
      seconds: 3,
      hemisphere: "S",
    });
    expect(splitAxis(107.6191, "lng", "dms")).toMatchObject({
      degrees: 107,
      minutes: 37,
      hemisphere: "E",
    });
  });

  it("rebuilds the signed value from fields", () => {
    expect(
      fromParts({ degrees: 6, minutes: 55, seconds: 3, hemisphere: "S" }, "lat"),
    ).toBeCloseTo(-6.9175, 4);
    expect(
      fromParts({ degrees: 107, minutes: 37, seconds: 8.76, hemisphere: "E" }, "lng"),
    ).toBeCloseTo(107.6191, 4);
    expect(fromParts({ degrees: 6, minutes: 55.05, seconds: 0, hemisphere: "N" }, "lat")).toBe(
      6.9175,
    );
  });

  it("round-trips split and rebuild for every format", () => {
    for (const [value, axis] of [
      [-6.9175, "lat"],
      [107.6191, "lng"],
      [3.83359, "lat"],
      [-0.9, "lat"],
      [119.87, "lng"],
    ] as Array<[number, "lat" | "lng"]>) {
      for (const format of COORDINATE_FORMATS) {
        const rebuilt = fromParts(splitAxis(value, axis, format), axis);
        expect(rebuilt, `${format} ${value}`).toBeCloseTo(value, 4);
      }
    }
  });

  it("refuses parts that can't be a coordinate", () => {
    // A half-typed form must not resolve to a plausible wrong point.
    expect(fromParts({ degrees: 6, minutes: 60, seconds: 0, hemisphere: "S" }, "lat")).toBeNull();
    expect(fromParts({ degrees: 6, minutes: 0, seconds: 60, hemisphere: "S" }, "lat")).toBeNull();
    expect(fromParts({ degrees: 91, minutes: 0, seconds: 0, hemisphere: "N" }, "lat")).toBeNull();
    expect(fromParts({ degrees: 181, minutes: 0, seconds: 0, hemisphere: "E" }, "lng")).toBeNull();
    expect(fromParts({ degrees: NaN, minutes: 0, seconds: 0, hemisphere: "N" }, "lat")).toBeNull();
    // A negative minute or second is meaningless, unlike a negative degree.
    expect(fromParts({ degrees: 6, minutes: -1, seconds: 0, hemisphere: "N" }, "lat")).toBeNull();
    expect(fromParts({ degrees: 6, minutes: 0, seconds: -1, hemisphere: "N" }, "lat")).toBeNull();
  });
});

describe("placeholder examples", () => {
  it("shows a distinct example for each notation", () => {
    const examples = COORDINATE_FORMATS.map(examplePair);
    expect(new Set(examples).size).toBe(3);

    expect(examplePair("dd")).toBe("6.91750° S · 107.61910° E");
    expect(examplePair("ddm")).toBe("6° 55.0500' S · 107° 37.1460' E");
    expect(examplePair("dms")).toBe(`6° 55' 3.00" S · 107° 37' 8.76" E`);
  });

  it("every example is itself valid input", () => {
    // Placeholders are generated by the formatters, so this guards against a
    // hint that shows a form the parser would reject.
    for (const format of COORDINATE_FORMATS) {
      const parsed = parseCoordinates(examplePair(format));
      expect(parsed, format).not.toBeNull();
      expect(parsed!.latitude, format).toBeCloseTo(EXAMPLE_POINT.latitude, 4);
      expect(parsed!.longitude, format).toBeCloseTo(EXAMPLE_POINT.longitude, 4);
    }
  });

  it("gives per-field hints matching the notation's boxes", () => {
    expect(examplePlaceholders("lat", "dd")).toMatchObject({ degrees: "-6.91750" });
    expect(examplePlaceholders("lng", "dd")).toMatchObject({ degrees: "107.61910" });
    expect(examplePlaceholders("lat", "ddm")).toMatchObject({
      degrees: "6",
      minutes: "55.0500",
    });
    expect(examplePlaceholders("lat", "dms")).toMatchObject({
      degrees: "6",
      minutes: "55",
      seconds: "3.00",
    });
    expect(examplePlaceholders("lng", "dms")).toMatchObject({
      degrees: "107",
      minutes: "37",
      seconds: "8.76",
    });
  });
});

describe("signed decimal degrees", () => {
  it("accepts a negative degree without any hemisphere marker", () => {
    // DD is conventionally written signed, so requiring N/S there would be wrong.
    expect(fromParts({ degrees: -6.9175, minutes: 0, seconds: 0, hemisphere: "" }, "lat")).toBe(
      -6.9175,
    );
    expect(fromParts({ degrees: 107.6191, minutes: 0, seconds: 0, hemisphere: "" }, "lng")).toBe(
      107.6191,
    );
    expect(fromParts({ degrees: -70.25, minutes: 0, seconds: 0, hemisphere: "" }, "lng")).toBe(
      -70.25,
    );
  });

  it("treats a minus and an S/W marker as the same instruction", () => {
    const viaSign = fromParts({ degrees: -6.9175, minutes: 0, seconds: 0, hemisphere: "" }, "lat");
    const viaMarker = fromParts({ degrees: 6.9175, minutes: 0, seconds: 0, hemisphere: "S" }, "lat");
    const viaBoth = fromParts({ degrees: -6.9175, minutes: 0, seconds: 0, hemisphere: "S" }, "lat");

    expect(viaSign).toBe(-6.9175);
    expect(viaMarker).toBe(-6.9175);
    // Both together must not double-negate back to positive.
    expect(viaBoth).toBe(-6.9175);
  });

  it("still enforces the range on a signed value", () => {
    expect(fromParts({ degrees: -91, minutes: 0, seconds: 0, hemisphere: "" }, "lat")).toBeNull();
    expect(fromParts({ degrees: -181, minutes: 0, seconds: 0, hemisphere: "" }, "lng")).toBeNull();
  });

  it("writes the signed pair people paste", () => {
    expect(formatSignedPair(-6.9175, 107.6191)).toBe("-6.91750, 107.61910");
    expect(parseCoordinates(formatSignedPair(-6.9175, 107.6191))).toMatchObject({
      latitude: -6.9175,
      longitude: 107.6191,
    });
  });
});
