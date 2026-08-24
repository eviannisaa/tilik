# Tilik

**Before you buy the land, check the ground.**

Tilik is a focused location-checking tool. Drop a pin anywhere and it pulls
together the boring-but-important context: how high the ground sits, whether
water is likely to be a problem, what has been recorded there before, and which
administrative area it falls in.

> Tilik is informational only. It reads open data that can be incomplete, out of
> date, or wrong for your exact plot. It is not a survey, not legal or financial
> advice, and not a guarantee about any property.

---

## Stack

| Layer    | Choice                                                        |
| -------- | ------------------------------------------------------------- |
| Frontend | Astro (static) · SolidJS islands · TypeScript · Tailwind CSS v4 |
| Map      | MapLibre GL JS with a configurable, key-less style URL         |
| Icons    | Lucide                                                         |
| Backend  | Python · FastAPI · Pydantic v2 · httpx                         |
| Database | PostgreSQL + PostGIS (optional) via SQLAlchemy 2 + GeoAlchemy2 |
| Hosting  | Vercel — static frontend and Python function on one domain     |

Everything works with an empty `.env`: the default providers are free and need
no API key.

---

## The report

It leads with the verdict, then four stat tiles — elevation, flood risk, strongest
hazard, nearest clinic — before the six sections that explain them. Elevation and
terrain therefore appear twice, deliberately: once as a figure to scan, once with
the sentence that gives it meaning.

### Keeping it readable

The report was becoming a wall of text, so three things are held back rather than
printed every time:

| Was | Now |
| --- | --- |
| 11 hazard rows, 6 of them blank | Only layers with a reading, plus *"Show 6 more layers with no reading"* |
| A four-item legend under every hazard table | A closed `<details>`: *"What these readings mean"* |
| All 12 disaster events | Nearest 5, plus *"Show all 12 events"* |

While a re-check runs, **every section header shows its own progress chip** — the
confidence chip is swapped for a spinner and "Updating", not stacked with one, so
nothing changes height. A single status line at the top of the report is invisible
to a reader already scrolled down to the section they care about.

Both collapses print their own count — the disaster section reads "5 of 12 events"
until expanded, because a capped list that looks complete is indistinguishable from
missing data. And since the skeleton is now reserved for first loads, a re-check
shows an explicit "Updating this report…" status line rather than only dimming,
which was too quiet to notice.

Nothing is hidden silently — each collapse states its own count, so the reader can
see there is more without having to read it. The legend uses a native `<details>`:
keyboard accessible, findable by in-page search, and no state of its own.

Each section also gained a one-line lede saying what it answers ("Whether water is
likely to be a problem here"), the confidence chip now reads `Measured` / `Modelled`
/ `Estimated` instead of small-caps `Measured data`, and section content is
full-width — the old inset started tables at a different edge from everything
around them, which read as misalignment rather than hierarchy.

### The hazard heading

Set at display size — `2rem`, `2.4rem` from `sm` up, against `1.35rem` for every
other section. Only this one gets it: eleven readings make it the longest part of
the report and the part people come for.

The distinction is **typographic, not chromatic**. Olive and terracotta already
mean hazard levels inside this section, so a heading wearing them would read as a
level rather than a title. Tracking and ligatures come from `.font-display` and
both sizes want `line-height: 1`, which leaves size as the whole difference — and
size is what matters here, because Instrument Serif only reads as a display face
above ~2rem; at 1.35rem it is just a small serif.

`ReportSection` takes an `emphasis` flag for this, so `title` stays a plain string
and the progress label built from it (`Updating Hazard index`) is unaffected.

### The hazard meters

Eleven layers of one measure is tabular data, so it's a real `<table>`: rows named,
index as text, status as text. The bar restates the number beside it and carries no
accessible name of its own — two columns called "Index" only make a table harder to
navigate.

Marks follow the usual specs: 6px fills, square where they meet the baseline with a
4px data-end, and a track that is a lighter step of the fill's own ramp so state
reads across the whole bar. Hairlines at 0.33 and 0.67 mark BNPB's class boundaries,
which is also the answer to "why is 0.34 medium?".

**The status colours were computed, not chosen.** Running the palette validator on
the original trio found `#c96f4a` against `#828062` separating by only **ΔE 3.1 for
a protanope and 11.9 for normal vision** — below the floor of 15, meaning high and
medium hazard were near-indistinguishable even with full colour vision. The steps
now in use — `olive-700` / `khaki-500` / `clay-600` — clear 15.4 (CVD) and 17.5
(normal), and the assessment's concern dots use the same three so the two readings
can't disagree.

Two checks it still can't pass, both inherent rather than accidental:

- **Chroma floor.** These are deliberately low-chroma earth tones, so they read close
  to grey. That would be fatal for a *categorical* palette, where hue carries
  identity; here every row is named in text and the status is spelled out, so hue is
  reinforcement rather than the encoding.
- **Contrast of the medium fill** (`khaki-500`, 2.47:1 against the surface). The
  sanctioned relief is a visible label or a table view — this has both.

Stat-tile values use the sans with **proportional** figures. `tabular-nums` gives
every digit a `0`'s width, which reads loose at display size; it's reserved for
columns that align, like the index column in that table.

### The verdict block

It sat on one of the `-50` tints, which separated from the report card by only
**1.20–1.30:1** — close enough to invisible that the answer read as more page
rather than the thing the page is for. It now has its own surfaces at
**1.42–1.73:1**, plus a hairline at the foot, since an edge does as much of the
separating as a fill does.

| Level | Surface | vs card | ink | ink-soft |
| ----- | ------- | ------- | --- | -------- |
| Low | `#c0bfa7` | 1.73:1 | 7.35 | 4.72 |
| Moderate | `#d7d1bb` | 1.42:1 | 8.97 | 5.75 |
| Higher | `#e3c0aa` | 1.57:1 | 8.09 | 5.19 |
| Unknown | `#d2ccb5` | 1.49:1 | 8.52 | 5.47 |

Two consequences of going deeper:

- **The level word is now set in `ink`, not its level colour.** Khaki manages only
  3.55–3.90:1 as text on a khaki-tinted surface at these depths, so it can't carry
  the word. The coloured dot beside it carries identity instead — the same rule the
  hazard meters follow.
- **`ink-faint` is gone from this block.** It drops under 4.5:1 on every one of
  these surfaces, so the fine print uses `ink-soft`.

A darker, bolder block was tried and rejected: on `#2a2f24` the lifted olive and
khaki collapse to ΔE 6.9, below the separation floor, so the three levels stop
being tellable apart.

### When a source fails

The old notice read *"We couldn't reach BNPB InaRISK for this check, so parts of
this report are estimated. Re-run it later for a fuller picture."* Three problems:
it never said **which** parts, the only suggested action was to come back later,
and there was no way to retry from where it appeared.

It's now built from `meta.sources` rather than `meta.degraded`, because the sources
carry the `field` that failed:

```
⚠ 3 sections are incomplete
  OpenStreetMap didn't answer, so nearby water and what's nearby are missing
  BNPB InaRISK didn't answer, so hazard index is missing
  Every other section is unaffected.                        [ Retry check ]
```

Gaps are grouped by provider, not listed per field — Overpass failing takes two
sections with it, and saying so twice reads as two separate problems. Provider
slugs are translated (`overpass` → OpenStreetMap), the count is of affected
*sections*, and the retry runs the check in place. It sits above the stat tiles,
since knowing a check is incomplete changes how much weight its numbers deserve.

### Refetching

Re-checking a point holds the previous report at reduced opacity with `aria-busy`
rather than swapping in a skeleton — no layout jump, and the reader doesn't lose
what they were reading. The skeleton is only for a first load, when there is nothing
to hold.

## Colour

The whole interface derives from five colours:

| | Hex | Role |
| --- | --- | --- |
| ![](https://placehold.co/12x12/2a2f24/2a2f24.png) | `#2a2f24` | Ink, primary buttons, shadow tint |
| ![](https://placehold.co/12x12/4f5b2a/4f5b2a.png) | `#4f5b2a` | Primary accent, "low concern" |
| ![](https://placehold.co/12x12/a4a07a/a4a07a.png) | `#a4a07a` | Borders, "moderate concern", water references |
| ![](https://placehold.co/12x12/c96f4a/c96f4a.png) | `#c96f4a` | "Higher concern", the only warm signal |
| ![](https://placehold.co/12x12/f1eadc/f1eadc.png) | `#f1eadc` | Paper |

Nothing else is introduced. Surfaces are the cream mixed toward white
(`paper-raised`) and toward khaki (`paper-sunk`); secondary text is the dark
olive mixed toward khaki; each accent gets a `50/200/500/600/700` ramp where
`500` is the palette colour itself, tints are mixed on cream and shades toward
the dark olive. Shadows are tinted with `#2a2f24` rather than black, so nothing
on the page turns grey.

### How the palette leads

The colours carry the page rather than sitting in the margins:

| Surface | Colour | Contrast |
| ------- | ------ | -------- |
| Header and footer bands | `#2a2f24` full-bleed, cream text | 11.46:1 |
| Primary actions, active tabs | `#4f5b2a` with cream text | 6.13:1 |
| Headline | `#3c4427` with a `#9c5d3f` second line | 8.56 / 4.33 |
| Map pin, rules, numerals | `#c96f4a` | — |

**Terracotta never carries text.** Cream on it reaches only 3.00:1 and dark olive
3.83:1, so it works as a mark — the map pin, the hero rule, section numerals —
but never as a text background. That constraint came out of measuring rather than
taste.

**Text on the dark bands uses cream-lifted steps.** The base khaki manages
5.15:1 there but terracotta only 3.83, so `khaki-300` (#b7b292, 6.40) and
`clay-300` (#d28a6a, 4.96) exist purely for use on `#2a2f24`.

Two further consequences worth naming:

- **The three assessment states use olive → khaki → terracotta.** The palette has
  no yellow, and khaki sits naturally between the other two, so "moderate" uses
  it instead of importing a sixth hue.
- **Water has no blue.** River and waterway references share the khaki ramp for
  the same reason.

Every text/background pair was checked to WCAG AA. Body text clears 4.5:1 on all
three surfaces (`ink` 9.9–12.7, `ink-soft` 6.4–8.2, `ink-faint` 4.6–5.9), and
badge text clears it on its own tint (olive 7.3, khaki 4.6, clay 5.4). That check
caught a real defect: badges were using the `600` step on a `50` tint, which is
only 3.78:1 — they now use `700`.

## Project layout

```text
tilik/
├── src/                        # Astro + Solid frontend
│   ├── components/
│   │   ├── ui/                 # Button, Badge, Panel, Skeleton, InlineAlert
│   │   ├── map/                # MapLibre map + its loading state
│   │   ├── location/           # Search box, selected-location card
│   │   ├── report/             # Report sections, assessment, skeletons
│   │   └── LocationChecker.tsx # Island root that owns the flow
│   ├── layouts/                # Shared chrome: nav band, footer band
│   ├── pages/
│   │   ├── index.astro         # Landing
│   │   ├── explore.astro       # The tool: input, map, report
│   │   ├── guideline.astro     # How to use it, and what it can't tell you
│   │   └── 404.astro
│   ├── styles/global.css       # Design tokens + MapLibre overrides
│   └── lib/                    # api client, store, types, config, formatters
│
├── api/                        # FastAPI backend
│   ├── index.py                # App wiring only — the Vercel entry point
│   ├── routes/                 # health, location, elevation, disaster, report
│   ├── services/               # One module per external concern
│   ├── schemas/                # Pydantic request/response models
│   ├── models/                 # SQLAlchemy + PostGIS tables
│   ├── db/                     # Engine, spatial queries, schema.sql
│   └── core/                   # Config, errors, HTTP, cache, rate limit, geo
│
├── scripts/
│   ├── import_inarisk.py       # Sample BNPB InaRISK rasters into PostGIS
│   ├── import_gdacs.py         # Load GDACS multi-hazard history into PostGIS
│   ├── import_disasters.py     # Load a DIBI/BNPB CSV export into PostGIS
│   └── import_desinventar.py   # Load the DesInventar mirror of DIBI (1815-2020)
├── tests/
├── public/
├── vercel.json
├── requirements.txt            # Runtime deps (what Vercel installs)
├── requirements-dev.txt        # + uvicorn for local development
└── .env.example
```

The frontend never talks to a provider directly. It calls `/api/*`, and the
service layer decides where the data comes from.

---

## Local development

You need **Node 20+** and **Python 3.11+**. Two processes run side by side; the
Astro dev server proxies `/api/*` to FastAPI, so the frontend uses the same
same-origin paths it will use in production.

```bash
# 1. Install
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configure (optional — the defaults work)
cp .env.example .env

# 3. Run the API                     → http://127.0.0.1:8000
python -m uvicorn api.index:app --reload --port 8000

# 4. Run the frontend in a second terminal → http://localhost:4321
npm run dev
```

Useful endpoints while developing:

- <http://127.0.0.1:8000/api/docs> — generated OpenAPI docs
- <http://127.0.0.1:8000/api/health> — provider and database status

Checks:

```bash
npm run typecheck      # Astro + TypeScript
npm test               # Frontend tests (Vitest + jsdom)
ruff check api scripts # Python lint
pytest                 # Python tests
```

### Changing the map

The basemap is a plain style URL, so switching it is a one-line env change and
a refresh — no code involved:

```env
PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

| Style      | Look                                          |
| ---------- | --------------------------------------------- |
| `liberty`  | Colourful, warm off-white base — **default**   |
| `bright`   | Softer palette, more label detail              |
| `positron` | Near-greyscale, very minimal                   |
| `fiord`    | Dark                                           |

Any key-less MapLibre style works. If your provider needs a key, proxy it
through the API — never put it in a `PUBLIC_*` variable. If the configured
style fails to load, the map falls back to MapLibre's demo tiles and says so.

### Working offline

Set `ENABLE_EXTERNAL_APIS=false` and the API answers from a small built-in
gazetteer and clearly-labelled placeholder elevation. Every response marks
itself with `quality: "estimate"` and a low confidence level, and the UI shows
which data was unavailable — nothing pretends to be real.

---

## Pages

| Route | Contents | JS shipped |
| ----- | -------- | ---------- |
| `/` | Landing — what a check covers, links in | **0 KB** |
| `/explore` | The tool: location input, map, report | 1002 KB |
| `/guideline` | Tutorial: the flow, coordinate formats, how to read each section, data sources, limits | **0 KB** |

### The selection card

The card between the map and the report answers one question — "is this the right
spot?" — before asking you to commit to a check, so it carries a terracotta top
edge in the same colour as the map pin. Card and marker then read as one thing
instead of two.

- **How the point was picked** is a chip with an icon (`From the map`, `Typed in`,
  `Your location`, `From search`) rather than a line of small caps.
- **The coordinates get their own readout**, with the `DD / DDM / DMS` switch and
  the copy button attached to the number they act on.
- **A map click has no name yet**, so while the store resolves one in the
  background the card says "Looking up the name…" instead of leaving a gap.
- **The button states what it will do**: "Terrain, flood, hazards, past disasters
  and what's nearby" sits under it, so pressing it isn't a leap of faith.

Order at every width:

```text
Location input
↓
Map
↓
Selected location + Check
↓
Report
```

One column rather than the map-beside-report grid it used to be, so the page reads
straight down: pick a point, confirm it, read the result. The report scrolls itself
into view when it arrives, since it lands below the fold.

The nav carries two items, `Explore` and `Guideline`; the logo returns to the
landing. Active state is derived from `Astro.url.pathname` inside the nav
component rather than passed in per page, so a page can't forget to declare it.

Splitting the tool onto its own route is what makes the other two pages ship
nothing: MapLibre is a megabyte, and it used to load for everyone who hit the
landing page. Now it loads only where the map is.

The guideline page is also where the app's caveats become discoverable — the four
hazard states, what confidence levels mean, and a plain list of what Tilik cannot
tell you (legal ownership, survey-precision claims, anything outside Indonesia, a
complete disaster history). Those were only in this README before.

## Choosing a location

Four ways in, all landing on the same `lat`/`lng`:

| Way | Notes |
| --- | ----- |
| Search a place | Nominatim, debounced, keyboard-navigable |
| **Coordinates** | Free-text field; parsed client-side, no round trip |
| Use my location | Browser geolocation |
| Tap the map | MapLibre click |

### Three notations, converted both ways

The same point gets written three ways depending on who wants it — so all three
are read on input and offered on output:

| | Notation | Typical source |
| --- | -------- | -------------- |
| **DD** | `6.91750° S · 107.61910° E` | web maps, APIs |
| **DDM** | `6° 55.0500' S · 107° 37.1460' E` | handheld GPS units |
| **DMS** | `6° 55' 3.00" S · 107° 37' 8.76" E` | land certificates, legal documents |

**The notation is chosen before typing, and the form reshapes to match:**

**Pasting is the default.** Most coordinates arrive as a string from somewhere
else, so the box that accepts one is what opens first; `Type in fields` switches to
structured entry for typing a value by hand, and `Paste instead` switches back.

Latitude, longitude and the action sit on **one row**. Each axis is a group that
wraps as a unit on narrow screens, so a number never gets separated from its
hemisphere toggle.

| Format | Fields per axis | Paste hint |
| ------ | --------------- | ---------- |
| DD | `-6.91750` **signed** | `-6.91750, 107.61910` |
| DDM | `6°` `55.0500'` + `N/S` | `6° 55.0500' S · 107° 37.1460' E` |
| DMS | `6°` `55'` `3.00"` + `N/S` | `6° 55' 3.00" S · 107° 37' 8.76" E` |

**DD is typed signed**, because that's how decimal degrees are written everywhere
they come from — Google Maps, GeoJSON, most APIs. Requiring a hemisphere toggle
there would fight the convention, so `-6.9175` on its own is sufficient and the
field accepts down to `-90` / `-180`. The N/S toggle stays visible and stays in
sync: typing a minus moves it, clicking it flips the sign. It reflects the number
rather than holding separate state that could disagree with what's on screen.

DDM and DMS keep magnitude-plus-marker, since those notations always spell the
hemisphere out. A minus and an `S`/`W` marker are treated as the same instruction
and never double-negate — the same rule the string parser uses, so both entry
paths agree.

Every placeholder — per field and for the paste box — is **generated by the same
formatters the app renders with**, from one example point, rather than written out
by hand. So a hint can never show a form the parser would reject; a test asserts
each example parses back to that point. Placeholders change as soon as the
notation does, and the inline `e.g.` steps aside once there's a real value, so the
same string is never on screen twice.

Hemisphere is a toggle rather than a minus sign — every notation writes it as a
letter, and it removes the "did I forget the sign?" mistake that silently moves a
plot to the wrong side of the equator. Switching notation mid-entry re-expresses
the value rather than clearing it, and out-of-range parts (minutes ≥ 60, degrees
> 90) disable the button instead of resolving to a plausible wrong point.

**Switching notation converts what's already entered.** Type `-6.9175` in DD, click
DMS, and the boxes become `6° 55' 3.00"` with `S` selected; click back and you get
`-6.9175` again, with no drift across a full DD → DDM → DMS → DD round trip. In
paste mode the text itself is rewritten, so the form works as a converter.

The conversion reacts to the format *signal* rather than to a button press,
because the selected-location card carries its own picker — handling it only in
the form's own button left a decimal degree sitting in a whole-degrees box whose
`min` was `0`.

A **Paste instead** toggle swaps the fields for a single free-text box, for when a
coordinate arrives as a string from somewhere else. Either way the result is shown
in **all three notations at once**, each with a copy button, so the form doubles as
a converter. The selected-location card carries the same `DD / DDM / DMS` switch;
the choice sticks for the session, since someone working from DMS certificates
shouldn't reselect it on every check.

Input is deliberately forgiving: decimal (`-6.9175, 107.6191`), hemisphere
letters before or after the number (`N 3.83359, E 96.85162`), DMS
(`6°55'3"S 107°37'9"E`), degrees with decimal minutes, and the app's own readout
— so a value copied out of a report pastes straight back in. A longitude-first
pair (as GeoJSON and WKT give) is reordered with a note rather than rejected.
Pasting coordinates into the *place* field is recognised too and skips the
geocoder entirely.

**Indonesian notation** is handled as a first-class case: `LU`/`LS`/`BT`/`BB`
(and the spelled-out *Lintang Utara*, *Bujur Timur*…) plus comma decimals, so
`6,9175° LS, 107,6191° BT` reads correctly. This mattered more than it looks —
before it was supported, `35° LS` parsed as **+35**, silently placing the point
in the wrong hemisphere. Comma-versus-dot is resolved by trying the comma-decimal
reading only when no dot is acting as a decimal point, and falling back if it
fails to yield a pair, so a guess can never beat an interpretation that works.

Precision is chosen so a value survives a round trip through text at ~0.2 m, and
rounding carries properly — `6.99999992°` prints as `7° 0' 0.00"`, not
`6° 59' 60.00"`. Every format is round-trip tested in
`src/__tests__/coordinates.test.ts`; the UI in `location-input.test.tsx`.

## API

All responses are camelCase JSON. Coordinates are WGS 84 decimal degrees.

| Endpoint                     | Query                | Returns                                     |
| ---------------------------- | -------------------- | ------------------------------------------- |
| `GET /api/health`            | —                    | Service, database and provider status        |
| `GET /api/location/search`   | `q`, `limit`         | Matching places                              |
| `GET /api/location/reverse`  | `lat`, `lng`         | A place name for a coordinate                |
| `GET /api/location/elevation`| `lat`, `lng`         | Elevation + terrain classification           |
| `GET /api/location/flood-risk`| `lat`, `lng`        | Flood risk + nearest waterway                |
| `GET /api/location/disasters`| `lat`, `lng`         | Multi-hazard events in range                 |
| `GET /api/location/hazards`  | `lat`, `lng`         | BNPB InaRISK indices for five hazards        |
| `GET /api/location/news`     | `lat`, `lng`         | Recent local reporting for the area          |
| `GET /api/location/places`   | `lat`, `lng`         | Nearby facilities, grouped by category       |
| `GET /api/location/report`   | `lat`, `lng`         | Everything above plus an overall assessment  |

```bash
curl "http://127.0.0.1:8000/api/location/report?lat=-6.9175&lng=107.6191"
```

```jsonc
{
  "location": { "latitude": -6.9175, "longitude": 107.6191, "name": "Kebon Pisang", "...": "" },
  "terrain":  { "elevation": 698, "unit": "meters", "terrain": "highland", "confidence": "high" },
  "flood":    { "risk": "medium", "basis": "inarisk", "hazardIndex": 0.49, "nearestRiver": { "name": "Ci Bunut", "distanceMeters": 12.7 } },
  "hazards":  { "source": "BNPB InaRISK", "readings": [{ "key": "earthquake", "index": 0.87, "level": "high", "status": "ok" }] },
  "disasters":{ "radiusMeters": 50000, "events": [], "searchedYears": 25 },
  "places":   { "radiusMeters": 1500, "total": 305, "categories": [] },
  "area":     { "administrativeArea": "Kota Bandung, Jawa Barat", "country": "Indonesia" },
  "assessment": { "level": "moderate", "confidence": "high", "factors": [], "disclaimer": "..." },
  "meta":     { "generatedAt": "...", "sources": [], "degraded": [] }
}
```

### Honesty by construction

Two fields exist so the UI never over-claims:

- **`confidence`** on each section — `high` (measured), `medium` (modelled),
  `low` (rough estimate), `none` (no data).
- **`meta.sources`** — provenance per field, with `quality` of `live`,
  `database`, `estimate` or `unavailable`. Anything `unavailable` also lands in
  `meta.degraded`, which the frontend surfaces as a notice.

The overall assessment is a coarse three-step rule set (`low` / `moderate` /
`higher`), not a model. Every point that moves the level also produces a visible
factor, and the level drops to `unknown` when the inputs are too thin.

### Errors

Every non-2xx response has the same shape, and Python tracebacks never reach the
client:

```json
{ "error": { "code": "upstream_timeout", "message": "A data provider took too long to answer.", "detail": null } }
```

| Status | When                                                       |
| ------ | ---------------------------------------------------------- |
| 400    | Coordinates off-planet, unusable search query               |
| 404    | No place matches                                            |
| 422    | Missing or malformed query parameters                       |
| 429    | Client rate limit, or a provider rate-limiting us           |
| 502    | A provider is unreachable or answered with an error         |
| 503    | The database is configured but unreachable                  |
| 504    | A provider timed out                                        |

Provider failures inside a report degrade one section instead of failing the
request — a dead elevation API still gives you disaster history.

---

## Database (optional)

Tilik runs without a database. Adding PostGIS lets it answer from local data
first: mapped flood zones become authoritative, and waterway/disaster lookups
stop depending on a third party.

On [Supabase](https://supabase.com): create a project, enable PostGIS, then

```bash
psql "$DATABASE_URL" -f api/db/schema.sql
```

Set `DATABASE_URL` to the **connection pooler** URI. `postgres://` and
`postgresql://` are both accepted and rewritten to the async driver
automatically.

Five tables, all with GiST indexes:

| Table              | Geometry                        | Role                                    |
| ------------------ | ------------------------------- | --------------------------------------- |
| `locations`        | `geometry(Point, 4326)`         | Geocoding cache                          |
| `disaster_events`  | `geometry(Point, 4326)`         | Historical events                        |
| `flood_zones`      | `geometry(MultiPolygon, 4326)`  | Mapped hazard polygons (authoritative)   |
| `waterways`        | `geometry(MultiLineString, 4326)` | Rivers, streams, canals                |
| `elevation_points` | `geometry(Point, 4326)`         | Sampled elevations                       |
| `hazard_cells`     | `geometry(Polygon, 4326)`       | Ingested InaRISK hazard grid              |
| `hazard_coverage`  | `geometry(Polygon, 4326)`       | Which areas were sampled, per hazard      |

Because engine creation is lazy and every query is wrapped, an unreachable
database degrades the report rather than breaking it.

Then load the data you want served locally:

```bash
python scripts/import_inarisk.py --bbox <west,south,east,north>  # BNPB hazards
python scripts/import_gdacs.py --years 25                         # Event history
python scripts/import_disasters.py path/to/dibi-export.csv        # DIBI CSV export
python scripts/import_desinventar.py DI_export_idn.zip            # DIBI full archive
```

---

## Deploying to Vercel

The frontend and API share one domain:

```text
https://your-domain.com/
https://your-domain.com/api/health
https://your-domain.com/api/location/report?lat=-6.9175&lng=107.6191
```

```bash
npm i -g vercel
vercel          # preview
vercel --prod   # production
```

Clean URLs for `/explore` and `/guideline` rely on Vercel's `handle: filesystem`
step resolving `explore/index.html`, which is its standard behaviour but is worth
confirming on the first deploy — it cannot be exercised locally.

`vercel.json` declares both builds explicitly — `@vercel/static-build` for
Astro's `dist/`, and `@vercel/python` for `api/index.py`. Declaring builds
rather than relying on auto-detection is deliberate: it keeps `api/routes/*.py`
and friends as ordinary imported modules instead of turning each one into its
own serverless function.

Add your environment variables in **Project → Settings → Environment
Variables**. At minimum consider `NOMINATIM_USER_AGENT` (the public instance's
policy requires an identifying value) and `DATABASE_URL` if you're using PostGIS.

### Serverless notes

- The database engine uses `NullPool` and disables prepared-statement caching,
  which is what pgbouncer-style poolers need.
- The in-process cache and rate limiter are per-instance. They protect upstream
  providers from one runaway client; put a real limiter at the edge if you need
  hard guarantees.

---

## Data sources

Each feature is backed by one service module that owns exactly one concern and
reads its endpoint from settings, so replacing a provider is a one-file change.

| Feature | Provider | Key? | Module | Env |
| --- | --- | --- | --- | --- |
| 🗺️ Map | MapLibre GL JS | no | `src/components/map/` | `PUBLIC_MAP_STYLE_URL` |
| 📍 Search | Nominatim / OSM | no | `services/geocoding.py` | `NOMINATIM_BASE_URL` |
| ⛰️ Elevation | **OpenTopography** | free key | `services/opentopography.py` | `OPENTOPOGRAPHY_API_KEY` |
| 🌊 Flood risk | **BNPB InaRISK** | no | `services/inarisk.py` | `INARISK_BASE_URL` |
| 📜 Disaster history | USGS (felt-filtered) + **GDACS** + DesInventar import | no | `services/disasters.py` | `EARTHQUAKE_API_URL`, `GDACS_API_URL` |
| 📰 Local news | Google News RSS | no | `services/news.py` | `GOOGLE_NEWS_RSS_URL`, `NEWS_MONTHS` |
| 🏥 Nearby places | OSM / Overpass | no | `services/places.py` | `OVERPASS_API_URL` |
| 🧮 Analysis | PostGIS + rules | no | `services/assessment.py` | `DATABASE_URL` |

### Administrative levels

Nominatim's Indonesian addresses are not consistent about which key holds which
level, so the hierarchy is read from the **order** of the address object — which
lists the most specific component first — rather than from key names:

| Point | kecamatan arrives as | kabupaten/kota as | province as |
| ----- | -------------------- | ----------------- | ----------- |
| Pagedangan, Tangerang | `municipality` | `county` | `state` |
| Bandung | `district` | `city` | `state` |
| Blangpidie, Aceh | `municipality` | `county` | `state` |
| Pluit, Jakarta | `suburb` | `city_district` | **`city`** — no `state` at all |

Reading those by name inverted two levels and produced *"Kabupaten Tangerang,
Pagedangan, Banten"*.

There was a second, worse bug alongside it: `zoom=14`. At that detail level
Nominatim matches the **largest polygon containing the point**, so a plot inside
the "BSD City" relation inherited that relation's hierarchy — *Pagedangan,
Kabupaten Tangerang* — when the point is actually in Serpong, **Kota Tangerang
Selatan**. A different regency means a different local government and different
rules, so being wrong there is worse than being vague. Reverse geocoding now uses
Nominatim's default `zoom=18`, which matches the feature at the point. It corrected
Merapi too, which had been reporting "Boyolali, Selo" and now reads "Musuk,
Boyolali, Jawa Tengah". Levels are now taken positionally from the largest inward,
duplicates dropped (a kecamatan is often repeated under two keys), so the area
reads kecamatan → kabupaten → province. `tests/test_geocoding_admin.py` pins this
against payloads captured from the live service, including the Jakarta case where
the province has to be recovered from the last level.

### ⛰️ Elevation — OpenTopography

OpenTopography serves DEM *rasters*, so a point lookup requests the smallest
possible bounding box in ESRI ASCII Grid format and reads the covering cell —
a few hundred bytes per query.

Get a free key at [portal.opentopography.org](https://portal.opentopography.org)
and set `OPENTOPOGRAPHY_API_KEY`. Without a key — or if the key is over quota —
Tilik falls through to the key-less OpenTopoData endpoint automatically, so
elevation never simply disappears. The grid parser is covered by
`tests/test_opentopography.py`, since the live endpoint can't run unkeyed.

### 🌊 Flood risk — BNPB InaRISK, ingested into PostGIS

InaRISK publishes Indonesia's national hazard models as ArcGIS ImageServers
where each pixel holds a 0–1 hazard index at 100 m resolution. Tilik reads
eleven layers — flood, flash flood, landslide, earthquake, liquefaction, tsunami,
waves & erosion, volcanic eruption, extreme weather, drought and forest fire —
classified into BNPB's own equal thirds: *rendah* / *sedang* / *tinggi*. That is
InaRISK's full hazard set apart from COVID-19, which isn't a property concern.

#### This is not the same number as InaRISK's website

InaRISK's own "Bencana" panel reports **Jiwa Terpapar** — the percentage of a
whole regency's *population* living inside each hazard zone. Tilik reports the
**hazard index at one plot**. Both come from the same models, but they answer
different questions, so they will never read the same. Checked at Blang Pidie,
Aceh Barat Daya:

| Hazard | InaRISK (% of regency exposed) | Tilik (this plot) |
| ------ | ------------------------------ | ----------------- |
| Gempabumi | 98% exposed | 0.786 high |
| Cuaca ekstrim | 93% exposed | 0.918 high |
| Likuefaksi | 71% exposed | 0.635 medium |
| Banjir | 46% exposed | 0.389 medium |
| Banjir bandang | 14% exposed | 0.951 high |
| Tanah longsor | 97% *not* exposed | no data at point |
| Tsunami | 91% *not* exposed | no data at point |

The pattern holds: where the regency is broadly exposed, the plot scores high;
where most of the regency is clear, the plot has no modelled hazard. Flash flood
shows the difference most sharply — only 14% of the regency is exposed, and this
particular plot sits inside that 14%. For "should I buy *this* land", the plot
value is the question worth asking; the regency percentage describes the regency.

#### Reading a blank row

Six of eleven layers reading blank is normal, not a failure — the section shows
three distinct states and they mean different things:

| Shown | Meaning |
| ----- | ------- |
| `0.00`–`1.00` | BNPB's index here. `0.00` is a real value: modelled, no hazard. The raster declares `minValues: [0]` and no nodata value, and ~17% of sampled land cells are exactly zero. |
| `No hazard mapped` | The model covers Indonesia but maps nothing of this kind nearby — expected for tsunami well inland, or flood on a steep slope. Not a guarantee of safety. |
| `No answer` | BNPB's server didn't respond for that layer. Re-run to retry. |
| `Outside coverage` | The point is beyond InaRISK's modelled extent — BNPB maps Indonesia only. Checked from the ImageServer's own bounds *before* any request, so an out-of-area point answers in ~0.02 s instead of returning eleven empty layers that would read as "safe". |

A steep inland plot legitimately reads landslide `1.00` with flood, liquefaction
and tsunami all unmapped — verified against a raw single-pixel `identify` on the
Merapi slope, which returns landslide `1`, drought `0.683`, and `NoData` for
flood and extreme weather. The header states the count (`4 of 11 layers map a
hazard`) so blanks read as an answer rather than an error.

#### Search radius is per hazard

The eleven layers are geographically different, so one radius can't serve them
all. Sampling a transect out from Blang Pidie found the missing data sitting just
beyond a flat 500 m search:

```
Tsunami         nearest data 1000 m   strongest 1.000 at 4750 m
Landslide       nearest data 1500 m   strongest 1.000 at 4750 m
Waves/abrasion  nearest data 2750 m   index 0.708
```

Those hazards are *offset* from a town centre, not absent — so each now has its
own radius (`HAZARD_RADIUS_M` in `services/inarisk.py`):

| Radius | Hazards | Why |
| ------ | ------- | --- |
| 1 km | flood, flash flood, liquefaction, earthquake, extreme weather, drought | broad surfaces; the plot's own pixel is the answer |
| 2.5 km | landslide, forest fire | follows hillslopes and land cover |
| 5 km | tsunami, waves & erosion | thin bands at the shoreline |
| 10 km | volcanic eruption | rings a mountain |

Each layer is still **one request**: sampled at native 100 m resolution within
500 m, then along 16 radial spokes at 250 m steps to the hazard's radius, which
keeps every layer under the provider's 1000-point cap (113–689 points).

Distance decides how a reading is used. Within `AT_PLOT_METERS` (500 m) it
affects the concern level; beyond that it's reported with its distance as
context, because a hazard band 2.7 km away describes the surroundings, not the
plot. The flood section words itself accordingly — "maps a high flood-hazard area
1000 m from this point … the plot itself is outside the mapped zone" rather than
claiming the point is inside it.

#### Thin-band hazards

Some layers are modelled as a narrow strip rather than a surface. Sampling a
transect across the Padang shoreline found tsunami hazard in **1 of 22 points
over 9 km**; at Palu, 1 of 20 over 16 km. So a single-pixel lookup returns
"no data" for a plot 400 m from the sea, which reads as "no tsunami risk" — the
opposite of the truth.

Hazards are therefore sampled across a neighbourhood
(`INARISK_NEIGHBOURHOOD_METERS`, default 500 m) at the native 100 m spacing, in
one request per layer. The rule:

- the point's own pixel wins wherever it has a value (`withinMeters: 0`)
- otherwise the strongest value in range is reported, with its distance

So `withinMeters` distinguishes "this plot is in the hazard area" from "the
hazard area is 300 m away", and neither is inflated into the other. Checked
against known geophysics: Padang reports tsunami 0.90 (faces the Sunda Trench)
while North Jakarta reports 0.013 (shallow Java Sea).

**BNPB's server is slow and frequently unavailable**, which is a bad thing to
put in the critical path of every location check. So the intended setup is to
sample it once into PostGIS and query locally after that:

```bash
# Greater Bandung at native 100 m resolution
python scripts/import_inarisk.py --bbox 107.5,-7.0,107.8,-6.8

# Coarser and faster, specific hazards only
python scripts/import_inarisk.py --bbox 106.6,-6.4,107.0,-6.0 \
    --cell-size 250 --hazards flood,landslide

# Cost check before you pay it
python scripts/import_inarisk.py --bbox 106.6,-6.4,107.0,-6.0 --dry-run
```

Each sampled cell is stored as a polygon in `hazard_cells`, so a lookup becomes
`ST_Intersects` against a GiST index. The script uses InaRISK's `getSamples`
operation, which returns up to 1000 points per request, and paces itself because
BNPB refuses connections when pushed.

Ingest only the area you actually serve — Indonesia at 100 m is billions of
cells. Re-running an overlapping box is safe: rows upsert on
`(hazard_type, cell_key)`, and the grid is anchored globally so the same ground
always lands in the same cell.

Reads are **PostGIS-first**: any hazard with ingested coverage is answered
locally, and only the rest fall through to the live ImageServers. Every reading
carries its `source` (`postgis` or `inarisk`) and, when ingested, the
`resolutionMeters` it was sampled at.

#### Why coverage is tracked separately

A missing `hazard_cells` row is ambiguous — it could mean "the model says no
hazard here" or "we never sampled this area". The first is an answer; the second
needs a live call. Without the distinction, every point in an already-ingested
area still pays for BNPB on the hazards that legitimately have nothing there,
which is most of them.

So `import_inarisk.py` records one `hazard_coverage` row per hazard per ingested
box, and **only when every batch for that hazard succeeded** — a partial sample
must not claim coverage, or it would answer "no hazard" on incomplete evidence.
The script says which hazards were recorded and which need a re-run.

Measured on a Bandung box, all eight hazards at 200 m:

| Coverage | Hazard lookup | BNPB calls |
| -------- | ------------- | ---------- |
| All eight ingested | **0.35 s** | 0 |
| None | 10.1 s | 3 answered, 5 timed out |

Flood risk resolves in strict order of authority, and `basis` says which won:

1. `postgis` — a mapped `flood_zones` polygon you imported
2. `inarisk` — the hazard index, ingested or live
3. `heuristic` — elevation plus distance to water

Each reading also carries a `status`, so "InaRISK models no hazard here" is
never rendered as "InaRISK didn't answer".

### 📜 Disaster history — USGS + GDACS, and DIBI by import

Two live catalogues, because no single free one covers everything:

| Source | Covers | Location precision |
| ------ | ------ | ------------------ |
| **USGS** | earthquakes | measured epicentre (`scope: "point"`) |
| **GDACS** | flood, volcanic eruption, wildfire, cyclone, drought | area centroid (`scope: "regional"`) |
| **DIBI/DesInventar** (import) | 32,447 Indonesian events, 1815–2020, with death and displacement counts | regency or district centroid (`regional`) |

#### What counts as a disaster, and what is only a tremor

A seismic catalogue answers a different question from the one this section asks.
USGS reports what its instruments detected; a disaster history should report
what reached people. Those diverge sharply over Java, which sits above a
subducting slab that produces a steady stream of magnitude 4–5 earthquakes
130–190 km down, felt by nobody.

Within 50 km of Serpong the catalogue holds 16 events at magnitude 4.5 or more.
Thirteen sit between 95 and 175 km deep with no intensity reading and no felt
report — among them `0 km NE of Serpong, 4.5 mb` from March 2018, an epicentre
named after the town but 139 km beneath it. Listing those as the disaster
history of a plot of land is noise, and worse, it crowds out the floods.

So USGS results are filtered (`_was_felt`), in order of how much each signal
knows:

1. **An intensity reading decides, either way.** It is USGS's own aggregate
   judgement, so `mmi` of 1 — "not felt" — rules an event out even where a
   couple of reports exist, and an intensity of II or more rules one in at any
   depth.
2. **Otherwise any felt report counts as evidence.**
3. **Otherwise depth decides** (`DISASTER_MAX_DEPTH_KM`, default 70). USGS
   computes intensity for anything significant, so silence plus great depth is
   the signature of an event nobody noticed.

**The intensity ladder reads as one scale.** USGS's own words mix registers —
`weak, light, moderate` leaves a reader guessing whether light is milder than
weak, and `severe, violent, extreme` is three near-synonyms in a row. The
wording stays on one "strong" family with modifiers instead:

```
I  not felt   IV moderate           VII  very strong      X-XII extreme
II weak       V  moderately strong  VIII extremely strong
III weak      VI strong             IX   violent
```

The *degrees* are untouched. MMI VI officially means Strong, so moving that word
down to V would have the report overstate what the ground did — the wording is
replaced, never repositioned.

**Intensity leads the readout, not magnitude.** Magnitude is energy at the
source, which is why 4.5 is a non-event at 194 km and damaging at 10 km.
Modified Mercalli intensity describes what the ground did at a place, on a scale
defined by observable effects, so the UI prints `shaking VIII (severe)` first
and the magnitude second.

**The magnitude scale is stored explicitly.** `magnitude_unit` used to be a
free-form string holding USGS scale codes, whatever a custom feed sent, and
NULL from GDACS — so the column was not comparable between rows. It is now
`magnitude_scale` (normalised to `mb`/`mw`/`ms`/`ml`/`md`/`m`/`other`) plus
`magnitude_scale_source` for the provider's own wording. This matters in
Indonesia specifically: USGS computes `mb` for 94% of moderate events here and
switches to `mw` above ~6.5 because `mb` saturates, while BMKG publishes a bare
number and names no scale at all — the `m` case. The same earthquake is `4.4 mb`
to one agency and `4.4` to the other, and neither is wrong.

Both live sources are free and need no key. Earthquakes are excluded from the
GDACS request on purpose: USGS already publishes real epicentres, and GDACS's
quake stream would otherwise consume its whole per-request record cap — that cap
is exactly why this section used to show nothing but earthquakes.

**And honest about reach.** The section is captioned with the radius it
searched, but GDACS is searched wider than the rest, so a plain "within 50 km"
was contradicted by its own list — Krakatau appeared at 140 km under it. The
caption now widens only when something shown actually came from beyond the main
radius: *"12 events within 50 km (regional feeds to 150 km), last 25 years"*.

| Source | Radius | Also filtered by |
| ------ | ------ | ---------------- |
| PostGIS `disaster_events` (BNPB DIBI) | `DISASTER_RADIUS_METERS`, 50 km | 25 years, max 3 rows per district |
| USGS earthquakes | 50 km | 25 years, M ≥ 4.5, felt-plausible (see depth rule) |
| GDACS multi-hazard | `GDACS_RADIUS_METERS`, **150 km** | 25 years |
| Configured GeoJSON feed | 50 km | — |

**Distances are honest about precision.** A GDACS coordinate is the centroid of
an affected region, so those events are tagged `regional`, given a wider search
radius (`GDACS_RADIUS_METERS`, default 150 km), rendered with a `~` prefix, and
excluded from the assessment's "significant events nearby" test — a centroid
that lands within 15 km is a coincidence of geometry, not a finding.

**Type diversity is guaranteed.** Seismic networks log far more events than any
other catalogue, so a plain nearest-first cut filled all twelve slots with
earthquakes and hid every flood — in Jakarta, the one hazard that actually
matters there. Selection now takes each type's nearest event first
(`DISASTER_EVENTS_PER_TYPE`) before filling remaining slots by distance:

```
Jakarta      flood 16.7 km ~ · 9 earthquakes · flood 43.2 km ~ · flood 43.2 km ~
Yogyakarta   6 earthquakes (incl. the 2006 M6.3 at 9 km) · Merapi ×3 at 29.5 km ~
```

#### Deeper history

One live GDACS request returns only the ~100 most recent events for a country,
which reaches back about four years. The API does honour a date window, so
`import_gdacs.py` walks it year by year to load the full record into PostGIS:

```bash
python scripts/import_gdacs.py --years 25      # Indonesia
python scripts/import_gdacs.py --dry-run       # see the cost first
```

Measured over 8 years: 176 events — 95 floods, 47 eruptions, 23 wildfires,
7 cyclones, 4 droughts. Rows upsert on `external_id`, so re-running refreshes.

#### One district can't take the list

Imported records carry their district's centroid, so every row in a district
ties on distance. Whichever district's centre happens to be nearest then wins
outright. Around Serpong that was Kota Jakarta Selatan — 105 rows at 16 km,
against Kota Tangerang Selatan, the district the pin actually sits in, at 18 km:

```
all 72 candidate rows  ->  Kota Jakarta Selatan
```

The whole candidate pool, so the selection step never saw another district. A
land check in Serpong showed Jakarta's history while Serpong's own five recorded
floods — and Tangerang's 100-death flood of March 2009 — were invisible. Two
kilometres of centroid arithmetic decided it.

Events therefore carry `area_name`, and the query caps rows per area with a
window function before the row limit applies (`MAX_EVENTS_PER_AREA`, default 3).
The cap has to be in the query: a client-side cap can shrink a monopolised list
but cannot diversify it. Measured epicentres have no `area_name` and key their
partition on their own id, so they are never capped — each is its own location.

```
before: 1 district,  8 of 12 rows Jakarta Selatan, own district absent
after:  6 districts, own district present, Tangerang's 100-death flood shown
```

Ranking inside each partition is by harm, so what survives a cap is the worst of
that district rather than an arbitrary three.

#### Setting up the database

Everything above works with an empty `.env`, but the imports need Postgres with
PostGIS. Any instance will do — Tilik reads one variable.

Locally, via Docker:

```bash
docker run -d --name tilik-db \
  -e POSTGRES_USER=tilik -e POSTGRES_PASSWORD=tilik -e POSTGRES_DB=tilik \
  -p 55432:5432 postgis/postgis:16-3.4

echo 'DATABASE_URL=postgresql://tilik:tilik@127.0.0.1:55432/tilik' >> .env
psql "postgresql://tilik:tilik@127.0.0.1:55432/tilik" -f api/db/schema.sql
```

On hosted **Supabase**, create a project, then take Project Settings → Database
→ Connection string → URI and put it in `.env` as `DATABASE_URL`. Nothing else
changes: `config.py` normalises a plain `postgres://` URL to
`postgresql+asyncpg://`, and PostGIS is already enabled on Supabase. Run
`schema.sql` against it the same way — it is re-runnable, and its
forward-compatibility section adds columns to a database created by an earlier
version rather than failing.

Then load the data:

```bash
python scripts/import_desinventar.py DI_export_idn.zip     # 32,447 events, ~12 s
python scripts/import_inarisk.py --bbox 95.28,5.50,95.38,5.60 --cell-size 250
```

#### DIBI, via DesInventar

**DIBI has no public API** — `dibi.bnpb.go.id` is an authenticated Apache
Superset dashboard, not a data service. But BNPB's records are mirrored in
Indonesia's DesInventar profile, which does publish a bulk export, and that is
the whole archive:

```bash
curl -LO https://www.desinventar.net/DesInventar/download/DI_export_idn.zip
python scripts/import_desinventar.py DI_export_idn.zip --dry-run   # see it first
python scripts/import_desinventar.py DI_export_idn.zip
```

32,447 importable events, 1815–2020, sourced `DIBI` — and unlike any seismic
catalogue, each one carries what happened to people:

```
flood             10,421      earthquake                648
extreme weather    8,096      coastal erosion           376
landslide          6,049      volcanic eruption         245
fire               2,531      tsunami                    47
drought            2,124      earthquake and tsunami     27
wildfire           1,883      recorded deaths       258,844
```

That distribution is the argument for importing it. Around Tangerang the archive
holds 91 events: 46 floods, 16 droughts, 12 windstorms — and exactly one
earthquake. Flooding is what has actually harmed people there, and it is the one
hazard the live earthquake catalogue can never report.

**A compound event belongs to both its hazards.** `event_type` is a display
label and may read `earthquake and tsunami`; a separate `hazard_types` array
carries the atomic memberships, indexed with GIN. This matters because
`covered_types` — the list whose whole job is to stop "no flood recorded" being
read as "no flood happened" — is built from what events claim to be. Under a
compound label alone, Palu and Aceh appeared under neither `earthquake` nor
`tsunami`, so a 128,728-death tsunami would have rendered as "no tsunami data
for this area". Now the per-hazard coverage adds up correctly:

```
earthquake  675  =  648 pure  +  27 compound
tsunami      74  =   47 pure  +  27 compound
```

The row is never split, so no death is counted twice.

**Earthquake-plus-tsunami keeps a compound type.** Folding `GEMPA BUMI DAN
TSUNAMI` into `tsunami` looked like rounding — 27 records against 649 pure
earthquakes — until those 27 turned out to be Aceh 2004 and Palu 2018, holding
**170,791 of the archive's 188,621 combined earthquake deaths**. It would have
moved 91% of them out of `earthquake`. It also misdescribes Palu, where the
shaking and the liquefaction at Petobo, Balaroa and Jono Oge killed far more
people than the wave; splitting the row in two instead would double-count every
death. Small record counts are not small events.

**Magnitude is always NULL, and that is correct.** `magnitud2` is empty in all
33,010 records — Palu 2018 and Aceh 2004 included. DIBI is a loss database, not
a seismic one: it counts what happened to people and leaves the instrument
reading to BMKG. These events are shown by their impact instead, which is the
more useful figure anyway.

Three things the importer does deliberately:

- **Zero and unknown are kept apart.** DesInventar pairs each count with an
  availability flag (`hay_muertos` and friends): `-1` means a real figure, `1` a
  reported zero, `0` nothing recorded. `damnificados` never uses `1`, so 29,208
  of 33,010 events carry a displacement count of `0` that means "unknown".
  Storing those as zero would invent an all-clear, so they become NULL.
- **Location is administrative, and says so.** Every coordinate in the export is
  literally `0`; position comes from joining the record's area code to the
  boundary shapefiles shipped with it, taking a representative point inside the
  largest ring (regencies are often archipelagos, and averaging their islands
  lands in open water). Spot-checked against known towns: 2–15 km out, all
  inside Indonesia. Those rows are `scope: "regional"`.
- **A third precision tier, because 6.6% of rows are much coarser.** The bundled
  boundaries hold **428 regencies against today's ~514** — Indonesia kept
  splitting them (*pemekaran*). Events in a regency created after the shapefile
  have no polygon and fall back to the province centroid: 2,133 rows, up to
  ~130 km off. Palu's 289 deaths in **Sigi** (split from Donggala in 2008) land
  in empty mountains 130 km east, which would surface them for a pin near that
  arbitrary point and hide them from Sigi itself. **Kota Tangerang Selatan —
  Serpong — is one of the missing ones.** These get `scope: "provincial"`;
  `assessment.py` already ignores anything that isn't `point`, and the UI prints
  "Province" in place of a distance rather than a number implying precision the
  data lacks.
- **Non-ground categories are dropped, and counted.** DIBI also tracks transport
  accidents, social conflict, terrorism and epidemics — 507 records that say
  nothing about the ground under a plot of land. The run reports what it skipped
  rather than quietly shrinking the archive.

**The archive stops in 2020**, so it fills in deep history rather than replacing
the live feeds; GDACS and USGS still cover recent years.

**Until it is imported, tsunami history does not exist.** No live source has it:
USGS is a seismic network publishing earthquakes, and GDACS has no tsunami event
type at all — it answers HTTP 204 for `eventlist=TS` and only ever emits EQ, FL,
TC, WF, DR, VO. A report for a beach in Banda Aceh lists a dozen earthquakes and
nothing else. That is why the section names what it did *not* search, computed
from `IMPORTABLE_TYPES` rather than hardcoded:

```
covered: cyclone, drought, earthquake, flood, volcanic eruption, wildfire
note:    Not searched here: coastal erosion, extreme weather, fire, landslide,
         tsunami. Indonesia's full record lives in BNPB's DIBI …
```

The old wording was a fixed sentence about "floods, landslides and windstorms",
which on that beach omitted the one hazard the reader most needed flagged.

Other feeds were evaluated and rejected: NASA's landslide catalogue host is
unreachable, Smithsonian GVP is a volcano inventory rather than an eruption
history, and BNPB's own `Kejadian_Bencana_Mingguan` ArcGIS layer has the right
schema but holds only the current week.

The response always states its own scope, so an empty list can't be mistaken
for an all-clear:

```json
"searchedSources": ["USGS earthquake catalogue", "GDACS multi-hazard feed"],
"coveredTypes": ["cyclone", "drought", "earthquake", "flood", "volcanic eruption", "wildfire"]
```

Landslide is absent from that list unless DIBI is imported, and the UI says so.

### 📰 Local news — Google News RSS

Every other section is measured or modelled. This one is *reported*, and the
difference is the whole design constraint.

**Why Google News and not GDELT.** GDELT was the obvious pick and was rejected
after testing: its DOC API rate-limits to **one request every five seconds per
IP**, which serverless functions sharing an egress address cannot honour, and
its GEO endpoint now 404s. Google News RSS needs no key, answers in about a
second, and its `hl=id&gl=ID` edition surfaces the outlets that actually cover
this — detik, Kompas, ANTARA, and BPBD and pemkot newsrooms.

**One request, not eleven.** Google accepts an OR-group, so all eleven hazard
topics are asked for in a single query, keyed to the same names as the hazard
index so a story lines up with its row.

**Two things that look like features but are bugs:**

* `when:12m` does **not** mean twelve months. Google reads `m` as *minutes*, so
  it returns a valid, empty feed for every location on earth. The window is
  built in days (`NEWS_MONTHS × 30`).
* Search terms need boundaries on *both* sides. Matching `rob` (tidal flooding)
  without a trailing boundary matched inside `roboh` ("collapsed"), filing a
  landslide story under coastal erosion.

**Relevance is ranked, not filtered.** A query for Surabaya also returns national
wires that merely mention it. Dropping those would also drop the genuinely local
story whose headline says "di Simo Gunung" and nothing more — so headlines that
name the area sort first, then by recency.

**The honesty rule.** Results are matched on a *place name*, not a coordinate, so
`matchedArea` always travels with them and the UI says which name was searched.
It is the weakest claim in the report and is labelled as such.

```jsonc
"news": {
  "matchedArea": "Surabaya",
  "monthsSearched": 12,
  "status": "ok",            // ok | no_area | no_results | unavailable
  "topics": ["wildfire", "flood"],
  "items": [{ "title": "…", "topic": "wildfire", "topicLabel": "Forest & land fire", … }]
}
```

`no_area` (no place name resolved) and `no_results` (searched, found nothing)
are deliberately distinct — neither is an all-clear, and they fail for opposite
reasons. Set `ENABLE_NEWS=false` to drop the section without touching any other
provider.

### 🏥 Nearby places — Overpass

One Overpass query returns everything mapped within `PLACES_RADIUS_METERS`,
grouped into health, education, shops, transport, safety, services and worship.
Categories are declared as data in `services/places.py` — adding one is a single
entry. Unnamed features are dropped, since they're noise in a list a human reads.

### 🧮 Analysis — PostGIS

When a database is configured, every spatial question a report asks is answered
by **one** PostGIS statement (`_ANALYSE_LOCATION` in `api/db/repository.py`)
rather than five round trips. Independent CTEs resolve, for the same point:

| CTE  | Question                                     | Operator        |
| ---- | -------------------------------------------- | --------------- |
| `hz` | Strongest ingested InaRISK cell in range     | `ST_DWithin` + `DISTINCT ON` |
| `cov`| Which hazards have been sampled here         | `ST_Intersects` |
| `fz` | Which mapped flood zone contains it          | `ST_Intersects` |
| `ww` | Nearest waterway and its distance            | `ST_DWithin` + `ST_Distance` |
| `el` | Nearest sampled elevation                    | `ST_DWithin` |
| `ev` | Disaster events in range, nearest first      | `ST_DWithin` |

`hz` and `ev` aggregate to JSON so they always yield one row; the rest are
`LEFT JOIN`ed onto that, so a miss produces `NULL` instead of no result. All
distance work casts to `geography`, so radii are real metres.

The result is passed down into the services, which use it instead of running
their own queries. Anything PostGIS can't answer — no coverage, no database, or
a query failure — falls through to the external provider for that field alone.
That means adding a database makes reports faster and more reliable without
changing what they contain.

The verdict rules stay in `services/assessment.py`. Every rule that moves the
level also emits a visible factor, and access to amenities can only add context
or credit — poor access is a liveability issue, not a hazard, so it never raises
the concern level on its own.

All defaults are shared community services — respect their usage policies, and
self-host or pay for a provider before sending real traffic.

## Not included, on purpose

No authentication, no user accounts, no admin dashboard, no payments, no CRUD.
Tilik does one thing: search a location, check it, understand the result.
