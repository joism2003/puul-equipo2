# Puul Hackathon FACPyA — Dataset

**Hackathon FACPyA · Optimización de Movilidad**

This folder contains the dataset and reference materials for the Puul Hackathon FACPyA challenge: **Smart Rider–Route Matching**.

---

## Challenge summary

Given a set of driver routes, build a system that ranks the routes by how well they match the rider's trip.

The match must:

1. Respect direction (no backtracking — pickup must come before dropoff along the route)
2. Consider proximity of pickup/dropoff to the route
3. Consider trip coverage (how much of the rider's trip is covered by the route)
4. **Consider time matching** — the route's date and departure/arrival times must be compatible with the rider's requested time window
5. Consider the driver's detour

The challenge combines **geospatial reasoning with time-window matching**. 

---

## Files in this folder

| File | Description |
|---|---|
| `README.md` | This file — dataset documentation |
| `routes.csv` | 200 driver routes for Thursday Apr 30 and Friday May 1, 2026 |
| `sample_searches.csv` | 6 rider request test cases for evaluation |
| `sample_searches_expected.md` | Reference description of what a great algorithm should output for each test case |

---

## Dataset overview

- **Total routes:** 200
- **Days covered:** Thursday April 30, 2026 (100 routes) and Friday May 1, 2026 (100 routes)
- **Geographic area:** Monterrey Metropolitan Area (Monterrey, San Pedro Garza García, San Nicolás de los Garza, Apodaca, Escobedo, Santa Catarina, Guadalupe)
- **Minimum route length:** 5 km
- **Coordinate system:** WGS84 (SRID 4326), decimal degrees
- **Departure time distribution:**
  - Morning peak (06:30–09:00): ~60% of routes
  - Midday (12:00–15:00): ~15% of routes
  - Evening peak (17:00–19:30): ~25% of routes

### Distribution by destination zone

| Zone | Approx. routes |
|---|---|
| Tec de Monterrey / Distrito Tec | 40 |
| UANL Ciudad Universitaria | 35 |
| Centro / Macroplaza | 30 |
| UDEM Valle Alto | 20 |
| San Pedro / Valle Oriente offices | 20 |
| Parque Industrial Apodaca | 20 |
| Aeropuerto / Escobedo industrial | 15 |
| Reverse direction (evening, going home) | 20 |

Multiple drivers may share the same origin–destination corridor at overlapping times — this is realistic for production carpool data and creates non-trivial tie-breaking cases.

---

## `routes.csv` schema

| Column | Type | Description |
|---|---|---|
| `route_id` | integer | Synthetic route identifier (sequential, no relation to production IDs) |
| `driver_id` | integer | Synthetic driver identifier |
| `driver_name` | string | Synthetic driver name (random Mexican first name + last initial) |
| `date` | date (YYYY-MM-DD) | Date the route runs |
| `departure_time` | time (HH:MM, 24h) | Driver's departure from origin, local Monterrey time |
| `arrival_time` | time (HH:MM, 24h) | Estimated arrival at destination, **driving alone with no passenger detours** |
| `origin_address` | string | Full address (see privacy rule below) |
| `origin_lat` | float | Origin latitude (4–6 decimals) |
| `origin_lng` | float | Origin longitude (4–6 decimals) |
| `destination_address` | string | Full address (see privacy rule below) |
| `destination_lat` | float | Destination latitude |
| `destination_lng` | float | Destination longitude |
| `waypoints` | JSON string | Ordered array of `[lat, lng]` pairs from origin to destination. **Order encodes direction.** |
| `distance_km` | float | Total route distance in kilometers |
| `estimated_duration_min` | integer | Estimated duration in minutes (no passenger, no detours) |
| `seats_available` | integer | Seats the driver is offering (1–4) |
| `vehicle_type` | string | `sedan`, `suv`, `hatchback`, `pickup` |

### Important notes about the `waypoints` column

- The waypoints are **ordered** from origin to destination. Index `[0]` matches the route's `origin_lat`/`origin_lng` (within sub-meter precision); the last index matches `destination_lat`/`destination_lng`.
- **The order encodes direction.** This is what teams use to detect backtracking: if a rider's pickup point projects onto the route at a higher index than their dropoff point, the rider would need to go backwards along the route → invalid match.
- The column is a **JSON-stringified array**, wrapped in double quotes inside the CSV. Parse it with `JSON.parse()` (JavaScript), `json.loads()` (Python), or any CSV+JSON parser.
- The waypoints are the **full polyline** — simulated GPS traces for in-trip navigation.
- Because the polylines are dense, your projection logic should be efficient. Brute-force scanning every waypoint for every (route, rider) pair is fine for 200 routes but won't scale — consider spatial indexing (e.g., a bounding box pre-filter) if you have time.

---

## `sample_searches.csv` schema

This file contains **6 rider request test cases** that every team must process during their demo. The cases are chosen to test specific algorithmic behaviors (clear winner, ambiguous, backtracking trap, low coverage, high detour, no valid match).

| Column | Type | Description |
|---|---|---|
| `description` | string | Short label for the case |
| `pickup_address` | string | Rider pickup address |
| `pickup_lat` | float | Pickup latitude |
| `pickup_lng` | float | Pickup longitude |
| `dropoff_address` | string | Rider dropoff address |
| `dropoff_lat` | float | Dropoff latitude |
| `dropoff_lng` | float | Dropoff longitude |
| `expected_behavior` | string | Plain-English description of what a correct algorithm should do |

The `expected_behavior` column does **not** prescribe a specific ranking — it describes the kind of result an algorithm should produce. Teams must justify their actual output against this description.

See `sample_searches_expected.md` for a reference walkthrough of what a top-quality algorithm's output looks like for each case.

---

### Notes on time matching

- All times in the dataset are **local Monterrey time** (`America/Mexico_City`, UTC−6 year-round, no daylight saving).
- Use reasonable time matching windows.
- A route on a different `date` than the rider requests should be rejected outright (score = 0). Time matching is binary in date but graded in time-of-day.
- Consider that the rider's "requested time" may be either a **desired departure** or a **desired arrival** — your algorithm should handle both gracefully.

---

## What to deliver

Every team must produce:

1. **A working ranking system** that processes all 6 test cases in `sample_searches.csv` against the 200 routes in `routes.csv`
2. **A presentation** showing the algorithm's output for each test case, with at least one case visualized on a map
3. **Clear scoring justification** — why your formula weights the criteria the way it does (proximity, coverage, time matching, detour)

The judging rubric weights are:

| Criterion | Weight |
|---|---|
| Correct backtracking detection | 30% |
| Proximity and coverage logic | 20% |
| Detour calculation | 15% |
| Time matching (date + time-of-day window) | 10% |
| Route ranking quality | 10% |
| Realism + clarity of presentation | 10% |
| Code quality | 5% |
---

## How to submit

When your team finishes, push your work to the official hackathon repository:

**Repository:** https://github.com/TechPuul/puulHackathonApril2026

**Steps:**

1. Clone the repository
2. Create a **new branch** named exactly after your team — for example:
   ```bash
   git checkout -b puulers
   ```
3. Commit all your code, scripts, notebooks, and any demo assets to that branch
4. Push the branch to the remote:
   ```bash
   git push origin puulers
   ```
5. Make sure the branch contains a short `README.md` at the root explaining how to run your code

**Branch naming rules:**

- Use only lowercase letters, numbers, and hyphens
- Format: `<your-team-name>`
- Examples: `super-puulers`, `puul-hackers`, `puul-devs`

Only one branch per team. Do **not** push to `main` or `dev` — the organizers will merge winning solutions after the event.

---

## Questions during the hackathon

If anything in this dataset is unclear, ask the organizers immediately. Don't waste time guessing — assumptions about the data format are not part of the challenge.

Good luck and may the best team win!

— **Equipo @Puul**
