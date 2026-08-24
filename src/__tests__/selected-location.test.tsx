/**
 * The selection card is the other `Panel` consumer, and it sits on the path
 * between picking a point and checking it — a render crash here blocks the
 * whole flow, so it gets its own smoke test.
 */

import { cleanup, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SelectedLocation from "../components/location/SelectedLocation";
import { displayStore, locationStore } from "../lib/store";

describe("SelectedLocation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ results: [], provider: "test", degraded: false }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    locationStore.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("prompts for a location before anything is picked", () => {
    render(() => <SelectedLocation />);

    expect(screen.getByText(/nothing picked yet\./i)).toBeTruthy();
    // The pill names the state the panel is in, so it is part of the prompt.
    expect(screen.getByText(/awaiting a point/i)).toBeTruthy();
  });

  it("shows the picked coordinates and the check action", async () => {
    render(() => <SelectedLocation />);

    locationStore.select({
      latitude: -6.9175,
      longitude: 107.6191,
      name: "Bandung",
      origin: "search",
    });

    await waitFor(() => expect(screen.getByText("Bandung")).toBeTruthy());
    expect(screen.getByText(/6\.91750° S/)).toBeTruthy();
    expect(screen.getByText(/107\.61910° E/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /check the ground/i })).toBeTruthy();
  });

  it("swaps to the new location when another point is picked", async () => {
    render(() => <SelectedLocation />);

    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });
    await waitFor(() => expect(screen.getByText("Bandung")).toBeTruthy());

    locationStore.select({ latitude: -8.6705, longitude: 115.2126, name: "Denpasar", origin: "map" });

    await waitFor(() => expect(screen.getByText("Denpasar")).toBeTruthy());
    expect(screen.queryByText("Bandung")).toBeNull();
    expect(screen.getByText(/115\.21260° E/)).toBeTruthy();
  });
});

describe("SelectedLocation presentation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ results: [], provider: "test", degraded: false }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    locationStore.clear();
    displayStore.setCoordinateFormat("dd");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("names how the point was picked, per route in", async () => {
    for (const [origin, label] of [
      ["search", "From search"],
      ["map", "From the map"],
      ["geolocation", "Your location"],
      ["coordinates", "Typed in"],
    ] as const) {
      cleanup();
      render(() => <SelectedLocation />);
      locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin });

      await waitFor(() => expect(screen.getByText(label)).toBeTruthy());
    }
  });

  it("says what the check will cover, so the button isn't a leap of faith", async () => {
    render(() => <SelectedLocation />);
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });

    await waitFor(() => expect(screen.getByText("Bandung")).toBeTruthy());
    expect(screen.getByText(/terrain, flood, hazards, past disasters/i)).toBeTruthy();
  });

  it("tells the user a name is being looked up rather than showing nothing", async () => {
    render(() => <SelectedLocation />);
    // A map click has coordinates but no name; the store resolves one in the
    // background, which should be visible rather than a silent gap.
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: null, origin: "map" });

    await waitFor(() => expect(screen.getByText(/looking up the name/i)).toBeTruthy());
  });

  it("puts copy directly beside the coordinates", async () => {
    render(() => <SelectedLocation />);
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });

    const readout = await waitFor(() => screen.getByText(/6\.91750° S/));
    const copy = screen.getByLabelText("Copy coordinates");

    // Copy acts on the value, so it sits with it rather than with the format
    // switch, which changes the value's shape instead.
    expect(copy.parentElement).toBe(readout.parentElement);
  });

  it("keeps the format switch in the same readout strip", async () => {
    render(() => <SelectedLocation />);
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });

    const readout = await waitFor(() => screen.getByText(/6\.91750° S/));
    const strip = readout.closest("div")!.parentElement!;

    expect(strip.textContent).toContain("DD");
    expect(strip.querySelector('[aria-label="Copy coordinates"]')).toBeTruthy();
  });

  it("shows the checking state on the button while a report runs", async () => {
    render(() => <SelectedLocation />);
    locationStore.select({ latitude: -6.9175, longitude: 107.6191, name: "Bandung", origin: "map" });
    await waitFor(() => expect(screen.getByText("Bandung")).toBeTruthy());

    const pending = locationStore.check();
    expect(screen.getByText(/reading the ground/i)).toBeTruthy();

    await pending;
    await waitFor(() => expect(screen.getByText(/check the ground/i)).toBeTruthy());
  });
});
