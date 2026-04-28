# Sample Searches — Expected Algorithm Behavior

This document describes what a strong matching algorithm should output for the test cases in `sample_searches.csv`. Different teams will produce different exact numbers — what matters is the *shape* of the result.

---

## Recommended output format

For each rider request, return a ranked list of valid matches. **Only include routes that pass direction (no backtracking) and time matching.** Invalid routes simply don't appear in the list.

```json
{
  "matches": [
    {
      "rank": 1,
      "route_id": 1001,
      "driver_name": "Adrián M.",
      "score": 0.87,
      "pickup_distance_to_route_m": 350,
      "dropoff_distance_to_route_m": 180,
      "pickup_index_on_route": 4,
      "dropoff_index_on_route": 13,
      "rider_trip_coverage_pct": 92,
      "driver_detour_m": 1250
    },
    { "rank": 2, "route_id": 1019, "score": 0.71, "...": "..." },
    { "rank": 3, "route_id": 1023, "score": 0.65, "...": "..." }
  ]
}
```

If no route passes the filters, return an empty list. Honest "no match" is a valid answer.

---

## General considerations

**Direction is non-negotiable.**

**Time matching is necessary** Same date is required. Within N minutes (determined by the participants) of the rider's window is good.

**Coverage is measured against the rider's trip, not the route.** 

**Proximity matters but isn't everything.** 

**Detour is a tie-breaker.** Two routes can have similar proximity and coverage but very different detour costs. Use detour to differentiate.

**Distinguish similar matches.** When 5+ routes are all reasonable, your top scores should still be different from each other.

---
## Per-case notes

### Case 1 — Clear winner (Av. Universidad → UANL Ciudad Universitaria)
A common morning corridor — UANL is the most popular destination in the dataset (28+ routes converge there). Expect **10+ valid matches**, top score **> 0.85**, with pickup and dropoff both within ~300m of the polyline. This case is mostly a sanity check.

### Case 2 — Ambiguous (UANL cluster, several corridors)
Same destination as case 1, but pickup is offset to a point reachable via different corridors (Av. Universidad, Av. Adolfo López Mateos, Av. Manuel L. Barragán). Multiple routes are valid matches — the algorithm should rank them with **distinguishable scores** (gaps of at least 0.02–0.05 between top entries). All identical scores in the top 5 means your scoring is too coarse — use coverage and detour to break ties.

### Case 3 — Backtracking trap ⚠
This is the **killer test**. Pickup is at UANL (the END of many morning routes); dropoff is back along Av. Universidad (where those routes' middle segments are). A naïve proximity-only algorithm will score morning UANL-bound routes high because both points are close to the polyline. A correct algorithm filters them out for direction violation. Expect **140+ routes rejected for backtracking** and only a small handful of valid matches — these would be afternoon routes that legitimately START at UANL and head outward.

### Case 4 — Low coverage (Cumbres → Centro Government)
A ~12 km cross-metro morning trip. Some routes pass through both areas in their middle segments, but coverage varies. Expect **2–5 valid matches** with a clear score gradient (top around 0.6–0.7, then 0.4–0.5, then below). Algorithms that weight **coverage** properly will rank routes very differently than those using pure proximity.

### Case 5 — High detour (Pueblo Serena → Tec)
Pickup lies ~1.5–2 km off any active corridor heading to Tec. Expect **1–3 valid matches** with the top route showing a clearly visible **pickup detour of 1500–2000m**. The score should reflect this — top match around 0.6, lower than case 1 even though both end at major destinations. Algorithms using detour as a bonus criterion should clearly differentiate routes here.

### Case 6 — No valid match (reverse commute, UANL → Pueblo Serena)
This trip is the morning commute IN REVERSE — going FROM UANL outward to a peripheral residential area. Almost every route in the dataset goes the other way. Expect **zero or near-zero valid matches**. Returning an empty list is the correct answer.

---

## Summary

A strong submission:
- Filters out backtracking routes correctly (case 3)
- Distinguishes between similar matches with meaningful score differences (case 2)
- Returns moderate or empty results when no good match exists (cases 4 and 6)
- Differentiates routes using detour cost as a tie-breaker (case 5)

Numerical scores will vary between teams. What matters is that the ranking matches the case description and the team can justify their scoring formula.
