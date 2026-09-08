import { API_BASE_URL } from "./config";
import type {
  AirQualityResponse,
  ApiErrorBody,
  DisastersResponse,
  ElevationResponse,
  FloodRiskResponse,
  HazardsResponse,
  HealthResponse,
  LocationReport,
  NewsResponse,
  PlacesResponse,
  SearchResponse,
} from "./types";

/**
 * A failure the UI is allowed to show a user. Raw backend stack traces never
 * reach this — the API always answers with a structured error body, and
 * anything unexpected is collapsed into a generic message here.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = status === 0 || status === 429 || status >= 500;
  }
}

const DEFAULT_TIMEOUT_MS = 20_000;

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

function buildUrl(path: string, params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const suffix = query.toString();
  return `${API_BASE_URL}${path}${suffix ? `?${suffix}` : ""}`;
}

async function request<T>(
  path: string,
  params: Record<string, string | number | undefined> = {},
  options: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  // Chain the caller's signal (used to cancel stale search keystrokes).
  const onAbort = () => controller.abort();
  options.signal?.addEventListener("abort", onAbort, { once: true });

  try {
    const response = await fetch(buildUrl(path, params), {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw await toApiError(response);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      // Distinguish "user typed another character" from "the server hung".
      if (options.signal?.aborted) throw error;
      throw new ApiError("That took too long. Try again in a moment.", "timeout", 0);
    }
    throw new ApiError("Can't reach the Tilik service right now.", "network_error", 0);
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", onAbort);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = "Something went wrong on our side.";

  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body?.error?.message) {
      message = body.error.message;
      code = body.error.code ?? code;
    }
  } catch {
    // Non-JSON body (proxy error page, gateway timeout). Keep the generic copy.
  }

  if (response.status === 429) {
    message = "Too many checks too fast. Give it a few seconds.";
    code = "rate_limited";
  }

  return new ApiError(message, code, response.status);
}

export const api = {
  health: (options?: RequestOptions) => request<HealthResponse>("/api/health", {}, options),

  search: (query: string, options?: RequestOptions) =>
    request<SearchResponse>("/api/location/search", { q: query, limit: 6 }, options),

  report: (lat: number, lng: number, options?: RequestOptions) =>
    request<LocationReport>("/api/location/report", { lat, lng }, { timeoutMs: 30_000, ...options }),

  elevation: (lat: number, lng: number, options?: RequestOptions) =>
    request<ElevationResponse>("/api/location/elevation", { lat, lng }, options),

  disasters: (lat: number, lng: number, options?: RequestOptions) =>
    request<DisastersResponse>("/api/location/disasters", { lat, lng }, options),

  floodRisk: (lat: number, lng: number, options?: RequestOptions) =>
    request<FloodRiskResponse>("/api/location/flood-risk", { lat, lng }, options),

  hazards: (lat: number, lng: number, options?: RequestOptions) =>
    request<HazardsResponse>("/api/location/hazards", { lat, lng }, options),

  news: (lat: number, lng: number, options?: RequestOptions) =>
    request<NewsResponse>("/api/location/news", { lat, lng }, options),

  airQuality: (lat: number, lng: number, options?: RequestOptions) =>
    request<AirQualityResponse>("/api/location/air-quality", { lat, lng }, options),

  places: (lat: number, lng: number, options?: RequestOptions) =>
    request<PlacesResponse>("/api/location/places", { lat, lng }, options),

  reverse: (lat: number, lng: number, options?: RequestOptions) =>
    request<SearchResponse>("/api/location/reverse", { lat, lng }, options),
};
