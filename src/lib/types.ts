/**
 * Wire types for the Tilik API.
 *
 * These mirror the Pydantic schemas in `api/schemas/`. The backend serialises
 * with camelCase aliases, so field names here match the JSON exactly.
 */

export type ConfidenceLevel = "high" | "medium" | "low" | "none";
export type RiskLevel = "low" | "medium" | "high" | "unknown";
export type AssessmentLevel = "low" | "moderate" | "higher" | "unknown";
export type TerrainKind =
  | "coastal"
  | "lowland"
  | "hilly"
  | "highland"
  | "mountainous"
  | "unknown";

/** Where a single piece of data came from, so the UI can be honest about it. */
export interface DataSource {
  field: string;
  provider: string;
  /** `live` = fetched now, `database` = local PostGIS, `estimate` = derived, `unavailable` = missing. */
  quality: "live" | "database" | "estimate" | "unavailable";
  note?: string | null;
}

export interface LocationInfo {
  latitude: number;
  longitude: number;
  name: string | null;
  displayName: string | null;
  locality: string | null;
  district: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
  postcode: string | null;
}

export interface SearchResult {
  latitude: number;
  longitude: number;
  name: string;
  displayName: string;
  category: string | null;
  boundingBox: [number, number, number, number] | null;
  /** The administrative chain, when the geocoder gave one. */
  district: string | null;
  city: string | null;
  province: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  provider: string;
  degraded: boolean;
}

export interface TerrainInfo {
  elevation: number | null;
  unit: "meters";
  terrain: TerrainKind;
  description: string;
  confidence: ConfidenceLevel;
}

export interface WaterFeature {
  name: string | null;
  kind: string;
  distanceMeters: number;
}

export interface FloodInfo {
  risk: RiskLevel;
  reason: string;
  nearestRiver: WaterFeature | null;
  zoneName: string | null;
  confidence: ConfidenceLevel;
  /**
   * BNPB InaRISK flood-hazard index (0–1) when that layer answered, whatever
   * decided `risk` — so a mapped zone and the national model can be compared.
   */
  hazardIndex: number | null;
  /** InaRISK's own class for `hazardIndex`, so the UI never re-derives it. */
  hazardLevel: RiskLevel | null;
  /** Which source decided the level. */
  basis: "postgis" | "inarisk" | "heuristic" | "none";
}

/**
 * `status` matters as much as `index`: "no hazard modelled here" and "we
 * couldn't reach the model" both give a null index but mean opposite things.
 */
export interface HazardReading {
  key: string;
  label: string;
  index: number | null;
  level: RiskLevel;
  status: "ok" | "no_data" | "unavailable" | "out_of_coverage";
  /** `postgis` when read from ingested cells, `inarisk` when fetched live. */
  source: "postgis" | "inarisk" | "none";
  /** Grid resolution of the ingested cell, when it came from PostGIS. */
  resolutionMeters: number | null;
  /** Metres from the queried point; 0 means the point itself is in the hazard area. */
  withinMeters: number | null;
  description: string;
}

export interface HazardIndex {
  source: string;
  readings: HazardReading[];
  confidence: ConfidenceLevel;
  note: string | null;
}

export interface NearbyPlace {
  name: string;
  kind: string;
  category: string;
  distanceMeters: number;
}

export interface PlaceCategory {
  key: string;
  label: string;
  count: number;
  nearest: NearbyPlace | null;
  places: NearbyPlace[];
}

export interface NearbyPlaces {
  radiusMeters: number;
  total: number;
  categories: PlaceCategory[];
  confidence: ConfidenceLevel;
  note: string | null;
}

/**
 * Normalised magnitude scale. Agencies label the same earthquake differently —
 * USGS computes `mb` for moderate Indonesian events and `mw` above ~6.5, while
 * BMKG publishes a bare number with no scale at all, which is `m`. Two rows are
 * only comparable on this, never on `magnitudeScaleSource`.
 */
export type MagnitudeScale = "mb" | "mw" | "ms" | "ml" | "md" | "m" | "other";

/**
 * Recorded human impact. Only loss databases (BNPB DIBI) carry this; a seismic
 * catalogue never does. `null` means no figure was published, which is not the
 * same as zero.
 */
export interface DisasterImpact {
  deaths: number | null;
  missing: number | null;
  injured: number | null;
  displaced: number | null;
  housesDestroyed: number | null;
  housesDamaged: number | null;
}

export interface DisasterEvent {
  id: string;
  /** Display label. May be compound ("earthquake and tsunami"). */
  type: string;
  /**
   * The atomic hazards this one event involved. Test hazard membership on this,
   * never on `type`: Palu 2018 and Aceh 2004 were quake *and* tsunami, and a
   * single label hides them from whichever category it omits.
   */
  hazardTypes: string[];
  /**
   * The administrative area a record belongs to. Set for records located by
   * area; `null` for a measured epicentre.
   */
  areaName: string | null;
  title: string;
  occurredAt: string | null;
  magnitude: number | null;
  magnitudeScale: MagnitudeScale | null;
  /** What the provider itself called the scale, e.g. "mww". Provenance only. */
  magnitudeScaleSource: string | null;
  /** Hypocentre depth in km — the number that decides whether a quake was felt. */
  depthKm: number | null;
  /** Modified Mercalli shaking intensity (1..12): what the ground did here. */
  intensityMmi: number | null;
  /** `modelled` is a ShakeMap estimate; `reported` came from people who felt it. */
  intensityBasis: "modelled" | "reported" | null;
  feltReports: number | null;
  impact: DisasterImpact | null;
  distanceMeters: number | null;
  /**
   * What `distanceMeters` measures to, which decides what may be said about it.
   *
   * `measured` — the event's own position, exact.
   * `area_edge` — the nearest edge of the area holding the record, so the event
   *   cannot have been nearer: a **lower bound**. Zero means the coordinate is
   *   inside the area.
   * `area_centre` — a centroid, because that area has no boundary; the event may
   *   be nearer or further, so no bound can be claimed.
   */
  distanceBasis: "measured" | "area_edge" | "area_centre" | null;
  /**
   * Height the water reached at this observation, in metres.
   *
   * The one tsunami figure that is genuinely local — NOAA/NCEI records it per
   * observation, so 10.7 m at Palu says what happened at Palu. Casualty totals
   * in the same database are per event and are deliberately not carried.
   */
  waterHeightM: number | null;
  source: string;
  url: string | null;
  /**
   * `regional` means the coordinate is an area centroid, so distance is
   * indicative. `provincial` means it is a whole province's centroid, which
   * makes the distance meaningless rather than merely approximate.
   */
  scope: "point" | "regional" | "provincial";
  /** Provider-native severity label, e.g. a GDACS alert level. */
  severity: string | null;
}

export interface DisasterHistory {
  /**
   * The radius every source was searched within. Nothing in the list can exceed
   * it: the wider-reaching GDACS feed was removed.
   */
  radiusMeters: number;
  events: DisasterEvent[];
  searchedYears: number;
  /**
   * The earthquake radius, when it is wider than `radiusMeters`.
   *
   * Epicentre distance is the wrong ruler for an earthquake: the M7.5 that
   * destroyed Palu sits 72 km from the city and shook it at MMI VIII, while an
   * M4.6 five kilometres away goes unnoticed.
   */
  earthquakeRadiusMeters: number | null;
  /** The tsunami window, when it is wider than `searchedYears`. */
  tsunamiYears: number | null;
  confidence: ConfidenceLevel;
  /** Catalogues actually queried. */
  searchedSources: string[];
  /** Event types those catalogues can return — anything absent was never searched. */
  coveredTypes: string[];
  note: string | null;
}

export interface NewsItem {
  id: string;
  title: string;
  url: string;
  publishedAt: string | null;
  /** Publisher, as the feed names it (e.g. "detikNews"). */
  source: string | null;
  /** Hazard key shared with HazardReading, so a story lines up with its row. */
  topic: string;
  topicLabel: string;
}

export interface LocalNews {
  items: NewsItem[];
  /** The place name actually searched — the results are only as precise as this. */
  matchedArea: string | null;
  monthsSearched: number;
  /** `no_area` means there was no place name to search on, not that nothing happened. */
  status: "ok" | "no_area" | "no_results" | "unavailable";
  topics: string[];
  note: string | null;
}

export interface AreaFeature {
  name: string;
  kind: string;
  distanceMeters: number | null;
}

export interface AreaInfo {
  administrativeArea: string | null;
  country: string | null;
  coordinates: { latitude: number; longitude: number };
  nearbyFeatures: AreaFeature[];
}

export interface AssessmentFactor {
  label: string;
  detail: string;
  impact: "positive" | "neutral" | "negative";
}

export interface Assessment {
  level: AssessmentLevel;
  headline: string;
  factors: AssessmentFactor[];
  confidence: ConfidenceLevel;
  disclaimer: string;
}

export interface ReportMeta {
  generatedAt: string;
  sources: DataSource[];
  degraded: string[];
}

export interface LocationReport {
  location: LocationInfo;
  terrain: TerrainInfo;
  flood: FloodInfo;
  hazards: HazardIndex;
  disasters: DisasterHistory;
  news: LocalNews;
  places: NearbyPlaces;
  area: AreaInfo;
  assessment: Assessment;
  meta: ReportMeta;
}

export interface ElevationResponse {
  latitude: number;
  longitude: number;
  terrain: TerrainInfo;
  provider: string;
}

export interface FloodRiskResponse {
  latitude: number;
  longitude: number;
  flood: FloodInfo;
}

export interface DisastersResponse {
  latitude: number;
  longitude: number;
  disasters: DisasterHistory;
}

export interface HazardsResponse {
  latitude: number;
  longitude: number;
  hazards: HazardIndex;
}

export interface PlacesResponse {
  latitude: number;
  longitude: number;
  places: NearbyPlaces;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  database: "connected" | "not_configured" | "unavailable";
  providers: Record<string, string>;
}

/** Shape of every non-2xx response from the API. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail?: string | null;
  };
}

export interface NewsResponse {
  latitude: number;
  longitude: number;
  news: LocalNews;
}
