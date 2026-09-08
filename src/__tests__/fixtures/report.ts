/**
 * A complete `LocationReport`, shared by the tests that need the report UI to
 * actually render. Kept out of any one test file because two divergent copies of
 * this shape is how a schema change starts passing in one suite and failing in
 * another.
 */

import type { LocationReport } from "../../lib/types";

export function buildReport(overrides: {
  name: string;
  elevation: number;
  terrain: string;
  floodRisk: string;
  events: number;
  area: string;
}): LocationReport {
  return {
    location: {
      latitude: 0,
      longitude: 0,
      name: overrides.name,
      displayName: overrides.name,
      locality: null,
      district: null,
      city: null,
      province: null,
      country: "Indonesia",
      postcode: null,
    },
    terrain: {
      elevation: overrides.elevation,
      unit: "meters",
      terrain: overrides.terrain as never,
      description: `Description for ${overrides.name}`,
      confidence: "high",
    },
    flood: {
      risk: overrides.floodRisk as never,
      reason: `Flood reason for ${overrides.name}`,
      nearestRiver: null,
      zoneName: null,
      confidence: "high",
      hazardIndex: null,
      hazardLevel: null,
      basis: "inarisk",
    },
    hazards: {
      source: "BNPB InaRISK",
      readings: [
        {
          key: "tsunami",
          label: "Tsunami",
          index: overrides.elevation < 50 ? 0.9 : null,
          level: overrides.elevation < 50 ? "high" : "unknown",
          status: overrides.elevation < 50 ? "ok" : "no_data",
          source: overrides.elevation < 50 ? "inarisk" : "none",
          resolutionMeters: null,
          withinMeters: overrides.elevation < 50 ? 320 : null,
          description: `Tsunami reading for ${overrides.name}`,
        },
      ],
      confidence: "medium",
      note: null,
    },
    disasters: {
      radiusMeters: 50000,
      events: Array.from({ length: overrides.events }, (_, index) => ({
        id: `${overrides.name}-${index}`,
        type: "earthquake",
        hazardTypes: ["earthquake"],
        areaName: null,
        title: `${overrides.name} event ${index}`,
        occurredAt: "2020-01-01T00:00:00Z",
        magnitude: 5,
        magnitudeScale: "mb" as const,
        magnitudeScaleSource: "mb",
        depthKm: 12,
        intensityMmi: 4.2,
        intensityBasis: "modelled" as const,
        feltReports: 31,
        impact: null,
        distanceMeters: 1000,
        distanceBasis: "measured" as const,
        source: "USGS",
        url: null,
        scope: "point" as const,
        waterHeightM: null,
        severity: null,
      })),
      searchedYears: 25,
      earthquakeRadiusMeters: null,
      tsunamiYears: null,
      confidence: "high",
      searchedSources: ["USGS earthquake catalogue"],
      coveredTypes: ["earthquake"],
      note: null,
    },
    news: {
      items: [],
      matchedArea: overrides.area,
      monthsSearched: 12,
      status: "no_results" as const,
      topics: [],
      note: null,
    },
    airQuality: {
      aqi: 78,
      band: "moderate" as const,
      level: "low" as const,
      bandLabel: "Moderate",
      dominantPollutant: "pm25",
      dominantLabel: "PM2.5",
      pollutants: [
        {
          key: "pm25",
          label: "PM2.5",
          aqi: 78,
          band: "moderate" as const,
          bandLabel: "Moderate",
          level: "low" as const,
          dominant: true,
        },
        {
          key: "pm10",
          label: "PM10",
          aqi: 31,
          band: "good" as const,
          bandLabel: "Good",
          level: "low" as const,
          dominant: false,
        },
      ],
      // Six on the EPA scale; BMKG's stations mostly report one.
      pollutantsPossible: 6,
      stationName: "Kemayoran, Indonesia",
      stationUrl: "https://aqicn.org/city/example",
      // Inside the 5 km "measured here" radius, so the fixture exercises the
      // confident path rather than the far-station warning.
      stationDistanceMeters: 4200,
      measuredAt: "2026-01-01T00:00:00Z",
      attributions: [
        { name: "World Air Quality Index Project", url: "https://waqi.info/" },
      ],
      status: "ok" as const,
      confidence: "high" as const,
      description: `Air-quality reading for ${overrides.name}`,
      note: null,
    },
    places: { radiusMeters: 1500, total: 0, categories: [], confidence: "low", note: null },
    area: {
      administrativeArea: overrides.area,
      country: "Indonesia",
      coordinates: { latitude: 0, longitude: 0 },
      nearbyFeatures: [],
    },
    assessment: {
      level: "moderate",
      headline: `Headline for ${overrides.name}`,
      factors: [],
      confidence: "high",
      disclaimer: "Not a survey.",
    },
    meta: { generatedAt: "2026-01-01T00:00:00Z", sources: [], degraded: [] },
  };
}
