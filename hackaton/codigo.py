"""
Puul Hackathon - Motor de matching geoespacial
Genera resultado_hackathon.html de forma completamente dinamica.

CORRECCIONES APLICADAS:
1. get_closest_segment_index: proyeccion sobre segmento en vez de waypoint mas cercano
2. cobertura calculada sobre el trayecto del pasajero, no del conductor
3. fecha y hora leidas del CSV (con fallback si no existen)
4. direction_score gradual basado en cobertura
5. doble penalizacion en utility eliminada (proximidad removida)
6. mapa: marcadores de inicio/fin del conductor
7. rechazados: score parcial calculado y mostrado
"""

import pandas as pd
import os
import json
from math import radians, cos, sin, asin, sqrt, atan2, degrees
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# HELPERS GEOESPACIALES
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2.0 * R * asin(sqrt(a))


def project_point_onto_segment(px, py, ax, ay, bx, by):
    """
    Proyecta el punto P sobre el segmento AB.
    Retorna (t, dist_km) donde t in [0,1] es la fraccion sobre el segmento
    y dist_km es la distancia del punto a la proyeccion.
    Usa aproximacion plana local (suficiente para distancias < 50 km).
    """
    # Convertir a coordenadas locales en km (aproximacion plana)
    lat_ref = (px + ax + bx) / 3.0
    cos_lat = cos(radians(lat_ref))
    R = 6371.0

    def to_xy(lat, lon):
        x = radians(lon) * R * cos_lat
        y = radians(lat) * R
        return x, y

    px2, py2 = to_xy(px, py)
    ax2, ay2 = to_xy(ax, ay)
    bx2, by2 = to_xy(bx, by)

    dx = bx2 - ax2
    dy = by2 - ay2
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-12:
        # Segmento degenerado (A == B)
        dist = haversine(px, py, ax, ay)
        return 0.0, dist

    t = ((px2 - ax2) * dx + (py2 - ay2) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    proj_x = ax2 + t * dx
    proj_y = ay2 + t * dy

    dist_km = sqrt((px2 - proj_x) ** 2 + (py2 - proj_y) ** 2)
    return t, dist_km


def get_closest_segment_index(point, waypoints):
    """
    CORRECCIÓN 1: Busca el segmento mas cercano (no el waypoint mas cercano).
    Retorna (idx_fraccionario, dist_km) donde idx_fraccionario puede ser e.g. 3.7
    lo que significa 70% del camino entre wp[3] y wp[4].
    """
    if len(waypoints) == 1:
        dist = haversine(point[0], point[1], waypoints[0][0], waypoints[0][1])
        return 0.0, dist

    best_idx = 0.0
    best_dist = float("inf")

    for i in range(len(waypoints) - 1):
        ax, ay = waypoints[i][0], waypoints[i][1]
        bx, by = waypoints[i + 1][0], waypoints[i + 1][1]
        t, dist = project_point_onto_segment(point[0], point[1], ax, ay, bx, by)
        if dist < best_dist:
            best_dist = dist
            best_idx = i + t

    return best_idx, best_dist


def get_time_diff_minutes(t1_str, t2_str):
    fmt = "%H:%M"
    t1 = datetime.strptime(t1_str, fmt)
    t2 = datetime.strptime(t2_str, fmt)
    return abs((t1 - t2).total_seconds() / 60.0)


def estimate_pickup_eta(departure_time_str, arrival_time_str, idx_pickup_frac, total_wps):
    fmt = "%H:%M"
    t_dep = datetime.strptime(departure_time_str, fmt)
    t_arr = datetime.strptime(arrival_time_str, fmt)
    total_min = (t_arr - t_dep).total_seconds() / 60.0
    if total_wps <= 1:
        return departure_time_str
    fraction = idx_pickup_frac / float(total_wps - 1)
    fraction = max(0.0, min(1.0, fraction))
    pickup_dt = t_dep + timedelta(minutes=fraction * total_min)
    return pickup_dt.strftime(fmt)


def calculate_utility_index(coverage):
    """
    CORRECCIÓN 5: Se elimina la proximidad de utility para evitar doble penalizacion.
    La proximidad ya penaliza en detour_score.
    Utility ahora solo refleja cobertura del trayecto del pasajero.
    """
    coverage_penalty = 1.0 if coverage >= 0.3 else (coverage / 0.3)
    utility = coverage * coverage_penalty
    return round(utility, 4)


def route_segment_length_km(waypoints, idx_start_frac, idx_end_frac):
    """
    Calcula la distancia en km de la ruta entre dos indices fraccionarios.
    Util para calcular cobertura en km reales.
    """
    if not waypoints or idx_start_frac >= idx_end_frac:
        return 0.0

    total = 0.0
    n = len(waypoints)

    i_start = int(idx_start_frac)
    i_end = int(idx_end_frac)

    # Primer segmento parcial
    if i_start < n - 1:
        t0 = idx_start_frac - i_start
        lat_s = waypoints[i_start][0] + t0 * (waypoints[i_start + 1][0] - waypoints[i_start][0])
        lon_s = waypoints[i_start][1] + t0 * (waypoints[i_start + 1][1] - waypoints[i_start][1])
    else:
        lat_s = waypoints[min(i_start, n - 1)][0]
        lon_s = waypoints[min(i_start, n - 1)][1]

    # Sumar segmentos enteros intermedios
    for i in range(i_start, min(i_end, n - 1)):
        lat_a = waypoints[i][0] if i == i_start else waypoints[i][0]
        lon_a = waypoints[i][1] if i == i_start else waypoints[i][1]
        if i == i_start:
            lat_a = lat_s
            lon_a = lon_s
        lat_b = waypoints[i + 1][0]
        lon_b = waypoints[i + 1][1]
        total += haversine(lat_a, lon_a, lat_b, lon_b)

    # Ultimo segmento parcial
    if i_end < n - 1 and i_end > i_start:
        t1 = idx_end_frac - i_end
        lat_e = waypoints[i_end][0] + t1 * (waypoints[i_end + 1][0] - waypoints[i_end][0])
        lon_e = waypoints[i_end][1] + t1 * (waypoints[i_end + 1][1] - waypoints[i_end][1])
        # Restar el ultimo segmento completo que ya sumamos y agregar el parcial
        total -= haversine(waypoints[i_end][0], waypoints[i_end][1],
                           waypoints[i_end + 1][0], waypoints[i_end + 1][1])
        total += haversine(waypoints[i_end][0], waypoints[i_end][1], lat_e, lon_e)

    return max(0.0, total)


def passenger_trip_distance(rider_pickup, rider_dropoff):
    return haversine(rider_pickup[0], rider_pickup[1], rider_dropoff[0], rider_dropoff[1])


# ---------------------------------------------------------------------------
# LOGICA DE NEGOCIO
# ---------------------------------------------------------------------------

def validate_route(rider_pickup, rider_dropoff, driver_waypoints):
    """
    CORRECCIÓN 1: Usa proyeccion sobre segmento en vez de waypoint mas cercano.
    CORRECCIÓN 2: Cobertura calculada sobre trayecto del pasajero.
    """
    idx_p, dist_p = get_closest_segment_index(rider_pickup, driver_waypoints)
    idx_d, dist_d = get_closest_segment_index(rider_dropoff, driver_waypoints)

    if dist_p > 2.5 or dist_d > 2.5:
        return False, 0, idx_p, idx_d, dist_p, dist_d, "proximity"

    if idx_p >= idx_d:
        return False, 0, idx_p, idx_d, dist_p, dist_d, "backtrack"

    # CORRECCIÓN 2: cobertura = km del trayecto del pasajero cubiertos por el conductor
    # relativo al trayecto directo del pasajero
    covered_km = route_segment_length_km(driver_waypoints, idx_p, idx_d)
    rider_km = passenger_trip_distance(rider_pickup, rider_dropoff)

    if rider_km < 0.01:
        coverage = 1.0
    else:
        coverage = min(1.0, covered_km / rider_km)

    return True, coverage, idx_p, idx_d, dist_p, dist_d, None


def calculate_partial_score(route, rider, coverage, idx_p, idx_d, dist_p, dist_d):
    """
    Calcula el score parcial para una ruta (usada tambien en rechazados).

    FIX:
    - Si es backtracking (idx_p >= idx_d) => score = 0
    """

    if idx_p >= idx_d:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    # Direction (gradual)
    direction_score = coverage

    # Time
    t_diff = get_time_diff_minutes(route["departure_time"], rider["requested_time"])
    t_score = max(0.0, 1.0 - (t_diff / 60.0))

    # Detour
    detour_km = dist_p + dist_d
    detour_score = max(0.0, 1.0 - (detour_km / 5.0))

    # Utility (solo coverage)
    utility = calculate_utility_index(coverage)

    final_score = (
        direction_score * 0.25
        + coverage * 0.20
        + t_score * 0.20
        + detour_score * 0.20
        + utility * 0.15
    )

    return (
        round(final_score, 4),
        round(t_diff, 1),
        round(t_score, 3),
        round(detour_km, 3),
        round(detour_score, 3),
        round(utility, 4),
    )

def get_final_score(route, rider):
    if route["date"] != rider["date"]:
        return 0, None

    p = (rider["pickup_lat"], rider["pickup_lng"])
    d = (rider["dropoff_lat"], rider["dropoff_lng"])

    is_valid, coverage, idx_p, idx_d, dist_p, dist_d, _ = validate_route(
        p, d, route["waypoints"]
    )

    if not is_valid:
        return 0, None

    final_score, t_diff, t_score, detour_km, detour_score, utility = calculate_partial_score(
        route, rider, coverage, idx_p, idx_d, dist_p, dist_d
    )

    pickup_eta = estimate_pickup_eta(
        route["departure_time"],
        route["arrival_time"],
        idx_p,
        len(route["waypoints"]),
    )

    details = {
        "coverage": round(coverage * 100.0, 1),
        "time_diff_min": t_diff,
        "t_score": t_score,
        "detour_km": detour_km,
        "detour_score": detour_score,
        "dist_pickup_km": round(dist_p, 3),
        "dist_dropoff_km": round(dist_d, 3),
        "idx_pickup": round(idx_p, 2),
        "idx_dropoff": round(idx_d, 2),
        "utility_index": round(utility * 100.0, 1),
        "pickup_eta": pickup_eta,
    }

    return final_score, details


# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

base_path = os.path.dirname(os.path.abspath(__file__))
routes_df = pd.read_csv(os.path.join(base_path, "routes.csv"))
searches_df = pd.read_csv(os.path.join(base_path, "sample_searches.csv"))

routes_df["waypoints"] = routes_df["waypoints"].apply(json.loads)

# CORRECCIÓN 3: Usar datos del CSV; fallback solo si no existen las columnas
if "date" not in searches_df.columns:
    searches_df["date"] = "2026-04-30"
if "requested_time" not in searches_df.columns:
    searches_df["requested_time"] = "07:30"

# ---------------------------------------------------------------------------
# PROCESAMIENTO PRINCIPAL
# ---------------------------------------------------------------------------

all_results = []

for i, (_, rider) in enumerate(searches_df.iterrows()):
    matches = []
    rejected_list = []

    potential = routes_df[routes_df["date"] == rider["date"]]
    rejected_date_count = len(routes_df) - len(potential)

    p = (rider["pickup_lat"], rider["pickup_lng"])
    d = (rider["dropoff_lat"], rider["dropoff_lng"])

    bt_total = 0
    prox_total = 0

    for _, route in potential.iterrows():
        is_valid, coverage, idx_p, idx_d, dist_p, dist_d, reason = validate_route(
            p, d, route["waypoints"]
        )

        if not is_valid:
            if reason == "backtrack":
                bt_total += 1
                reason_label = "Backtracking: Punto B queda ANTES que Punto A en la ruta del conductor"
            else:
                prox_total += 1
                if dist_p > 2.5 and dist_d > 2.5:
                    reason_label = "Punto A y B fuera de rango (A=" + str(round(dist_p, 2)) + " km, B=" + str(round(dist_d, 2)) + " km)"
                elif dist_p > 2.5:
                    reason_label = "Punto A (subida) muy lejos de la ruta: " + str(round(dist_p, 2)) + " km"
                else:
                    reason_label = "Punto B (bajada) muy lejos de la ruta: " + str(round(dist_d, 2)) + " km"

            bucket = "backtrack" if reason == "backtrack" else "proximity"
            same_bucket = sum(1 for r in rejected_list if r["reject_type"] == bucket)

            # CORRECCIÓN 7: calcular score parcial para rechazados
            partial_score, _, _, _, _, _ = calculate_partial_score(
                route, rider, max(coverage, 0.0), idx_p, idx_d, dist_p, dist_d
            )

            if same_bucket < 30:
                wps = route["waypoints"]
                rejected_list.append({
                    "route_id": int(route["route_id"]),
                    "driver": route["driver_name"],
                    "departure_time": route["departure_time"],
                    "reject_type": bucket,
                    "reason_label": reason_label,
                    "dist_pickup_km": round(dist_p, 3),
                    "dist_dropoff_km": round(dist_d, 3),
                    "idx_pickup": round(idx_p, 2),
                    "idx_dropoff": round(idx_d, 2),
                    "partial_score": partial_score,
                    "waypoints": wps,
                    "driver_start": wps[0] if wps else None,
                    "driver_end": wps[-1] if wps else None,
                })
            continue

        score, details = get_final_score(route, rider)
        if score > 0:
            wps = route["waypoints"]
            matches.append({
                "route_id": int(route["route_id"]),
                "driver": route["driver_name"],
                "departure_time": route["departure_time"],
                "arrival_time": route["arrival_time"],
                "seats_available": int(route["seats_available"]),
                "vehicle_type": route["vehicle_type"],
                "score": score,
                "details": details,
                "waypoints": wps,
                "driver_start": wps[0] if wps else None,
                "driver_end": wps[-1] if wps else None,
            })

    matches = sorted(matches, key=lambda x: x["score"], reverse=True)

    if len(matches) == 0:
        badge = "badge-err"
    elif bt_total > 50 or len(matches) <= 3:
        badge = "badge-warn"
    else:
        badge = "badge-ok"

    badge_text = "Sin coincidencias" if len(matches) == 0 else (str(len(matches)) + " matches")

    all_results.append({
        "case_num": i + 1,
        "description": rider["description"],
        "pickup_lat": float(rider["pickup_lat"]),
        "pickup_lng": float(rider["pickup_lng"]),
        "pickup_address": str(rider.get("pickup_address", "")),
        "dropoff_lat": float(rider["dropoff_lat"]),
        "dropoff_lng": float(rider["dropoff_lng"]),
        "dropoff_address": str(rider.get("dropoff_address", "")),
        "matches": matches[:5],
        "total_valid": len(matches),
        "rejected_backtrack": bt_total,
        "rejected_proximity": prox_total,
        "rejected_date": rejected_date_count,
        "rejected_list": rejected_list,
        "badge": badge,
        "badge_text": badge_text,
    })

    print("Caso " + str(i + 1) + ": " + str(len(matches)) + " matches | " + str(bt_total) + " backtrack | " + str(prox_total) + " proximidad")


# ---------------------------------------------------------------------------
# CONSTRUCCION DEL HTML
# ---------------------------------------------------------------------------

def build_html(all_results):

    cases_data = []
    for r in all_results:
        cases_data.append({
            "case_num": r["case_num"],
            "description": r["description"],
            "pickup_lat": r["pickup_lat"],
            "pickup_lng": r["pickup_lng"],
            "pickup_address": r["pickup_address"],
            "dropoff_lat": r["dropoff_lat"],
            "dropoff_lng": r["dropoff_lng"],
            "dropoff_address": r["dropoff_address"],
            "badge": r["badge"],
            "badge_text": r["badge_text"],
            "total_valid": r["total_valid"],
            "rejected_backtrack": r["rejected_backtrack"],
            "rejected_proximity": r["rejected_proximity"],
            "rejected_date": r["rejected_date"],
            "matches": [
                {
                    "rank": j + 1,
                    "route_id": m["route_id"],
                    "driver": m["driver"],
                    "departure_time": m["departure_time"],
                    "seats": m["seats_available"],
                    "vehicle": m["vehicle_type"],
                    "score": m["score"],
                    "coverage": m["details"]["coverage"],
                    "detour_km": m["details"]["detour_km"],
                    "dist_pickup_km": m["details"]["dist_pickup_km"],
                    "dist_dropoff_km": m["details"]["dist_dropoff_km"],
                    "time_diff_min": m["details"]["time_diff_min"],
                    "utility_index": m["details"]["utility_index"],
                    "pickup_eta": m["details"]["pickup_eta"],
                    "waypoints": m["waypoints"],
                    "driver_start": m["driver_start"],
                    "driver_end": m["driver_end"],
                }
                for j, m in enumerate(r["matches"])
            ],
            "rejected_list": r["rejected_list"],
        })

    cases_json = json.dumps(cases_data, ensure_ascii=False)

    # -----------------------------------------------------------------------
    # CSS string
    # -----------------------------------------------------------------------
    css_parts = []
    css_parts.append(":root {")
    css_parts.append("  --bg:#0b0d11; --surface:#13161d; --surface2:#1a1f2b;")
    css_parts.append("  --surface3:#202636; --border:#252d3d; --text:#dde2f0;")
    css_parts.append("  --text2:#8892aa; --accent:#00dda0; --accent2:#4d8fff;")
    css_parts.append("  --accent3:#ff6b52; --warn:#f6a72a; --purple:#a975ff;")
    css_parts.append("  --radius:8px; --shadow:0 4px 24px rgba(0,0,0,.5);")
    css_parts.append("  --header-h:48px; --t:.18s ease;")
    css_parts.append("}")
    css_parts.append("body.light {")
    css_parts.append("  --bg:#f0f2f7; --surface:#fff; --surface2:#f5f6fb;")
    css_parts.append("  --surface3:#eaecf5; --border:#d8dce8; --text:#1a2035;")
    css_parts.append("  --text2:#5a6380; --shadow:0 4px 24px rgba(0,0,0,.1);")
    css_parts.append("}")
    css_parts.append("*{box-sizing:border-box;margin:0;padding:0}")
    css_parts.append("html,body{height:100%;overflow:hidden}")
    css_parts.append("body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);display:flex;flex-direction:column;transition:background var(--t),color var(--t)}")
    css_parts.append("#header{height:var(--header-h);background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 16px;gap:14px;flex-shrink:0;z-index:100}")
    css_parts.append(".logo{font-family:'Syne',sans-serif;font-weight:800;font-size:17px;color:var(--accent);letter-spacing:-.5px}")
    css_parts.append(".logo em{color:var(--text);font-style:normal}")
    css_parts.append("#header h1{font-size:12px;color:var(--text2);font-weight:400;flex:1}")
    css_parts.append(".hpill{font-family:'DM Mono',monospace;font-size:10px;padding:3px 9px;border-radius:20px;border:1px solid var(--border);color:var(--text2)}")
    css_parts.append("#theme-btn{width:32px;height:32px;border-radius:50%;border:1px solid var(--border);background:var(--surface2);color:var(--text);cursor:pointer;font-size:15px;display:flex;align-items:center;justify-content:center;transition:all var(--t)}")
    css_parts.append("#theme-btn:hover{background:var(--surface3)}")
    css_parts.append("#layout{display:flex;flex:1;overflow:hidden;position:relative}")
    css_parts.append("#sidebar{width:270px;min-width:180px;max-width:420px;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;transition:width var(--t);position:relative;flex-shrink:0}")
    css_parts.append("#sidebar.collapsed{width:42px!important;min-width:42px}")
    css_parts.append("#sidebar-head{display:flex;align-items:center;padding:0 10px 0 14px;height:36px;border-bottom:1px solid var(--border);flex-shrink:0;gap:6px}")
    css_parts.append("#sidebar-head span{font-family:'DM Mono',monospace;font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text2);flex:1;white-space:nowrap;overflow:hidden}")
    css_parts.append(".cbtn{width:22px;height:22px;border-radius:5px;border:1px solid var(--border);background:transparent;color:var(--text2);cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0}")
    css_parts.append(".cbtn:hover{background:var(--surface2);color:var(--text)}")
    css_parts.append("#case-list{flex:1;overflow-y:auto}")
    css_parts.append("#case-list::-webkit-scrollbar{width:3px}")
    css_parts.append("#case-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}")
    css_parts.append("#sidebar.collapsed #sidebar-head span,#sidebar.collapsed #case-list{opacity:0;pointer-events:none}")
    css_parts.append(".case-btn{display:flex;align-items:flex-start;gap:10px;width:100%;padding:11px 14px;border:none;background:transparent;cursor:pointer;text-align:left;border-bottom:1px solid var(--border);transition:background var(--t)}")
    css_parts.append(".case-btn:hover{background:var(--surface2)}")
    css_parts.append(".case-btn.active{background:rgba(0,221,160,.07);border-left:2px solid var(--accent);padding-left:12px}")
    css_parts.append(".cnum{font-family:'DM Mono',monospace;font-size:11px;color:var(--text2);margin-top:2px;min-width:18px}")
    css_parts.append(".case-btn.active .cnum{color:var(--accent)}")
    css_parts.append(".ctitle{font-size:12px;font-weight:500;color:var(--text);line-height:1.4;margin-bottom:5px;display:block}")
    css_parts.append(".case-btn.active .ctitle{color:var(--accent)}")
    css_parts.append(".csub{display:flex;gap:6px;flex-wrap:wrap;align-items:center}")
    css_parts.append(".badge{font-family:'DM Mono',monospace;font-size:9px;font-weight:500;padding:2px 7px;border-radius:4px}")
    css_parts.append(".badge-ok{background:rgba(0,221,160,.12);color:var(--accent);border:1px solid rgba(0,221,160,.2)}")
    css_parts.append(".badge-warn{background:rgba(246,167,42,.12);color:var(--warn);border:1px solid rgba(246,167,42,.2)}")
    css_parts.append(".badge-err{background:rgba(255,107,82,.12);color:var(--accent3);border:1px solid rgba(255,107,82,.2)}")
    css_parts.append(".rhandle{width:5px;cursor:col-resize;position:absolute;right:0;top:0;bottom:0;z-index:10;background:transparent}")
    css_parts.append(".rhandle:hover{background:var(--accent);opacity:.3}")
    css_parts.append("#right{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}")
    css_parts.append("#map-wrap{flex:0 0 52%;min-height:120px;position:relative;overflow:hidden}")
    css_parts.append("#leaflet-map{width:100%;height:100%}")
    css_parts.append("#map-ov{position:absolute;top:12px;left:12px;z-index:999;background:rgba(11,13,17,.88);backdrop-filter:blur(14px);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;max-width:280px;pointer-events:none;transition:background var(--t)}")
    css_parts.append("body.light #map-ov{background:rgba(255,255,255,.92)}")
    css_parts.append(".ov-case{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--accent);margin-bottom:3px}")
    css_parts.append(".ov-desc{font-size:11px;color:var(--text2);line-height:1.5}")
    css_parts.append(".ov-chips{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}")
    css_parts.append(".ov-chip{font-family:'DM Mono',monospace;font-size:10px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);color:var(--text2)}")
    css_parts.append("#map-leg{position:absolute;bottom:12px;left:12px;z-index:999;background:rgba(11,13,17,.85);backdrop-filter:blur(10px);border:1px solid var(--border);border-radius:var(--radius);padding:8px 12px;display:flex;gap:10px;flex-wrap:wrap}")
    css_parts.append("body.light #map-leg{background:rgba(255,255,255,.92)}")
    css_parts.append(".leg-item{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2)}")
    css_parts.append(".leg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}")
    css_parts.append(".leg-line{width:18px;height:3px;border-radius:2px;flex-shrink:0}")
    css_parts.append("#map-rz{height:6px;cursor:row-resize;background:var(--border);flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:background var(--t)}")
    css_parts.append("#map-rz:hover{background:var(--accent)}")
    css_parts.append("#map-rz::after{content:'\\22EF';color:var(--text2);font-size:12px;line-height:1}")
    css_parts.append("#bot{flex:1;overflow:hidden;display:flex;flex-direction:column;background:var(--bg)}")
    css_parts.append("#stats-strip{display:flex;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}")
    css_parts.append(".st-it{flex:1;text-align:center;padding:7px 6px;border-right:1px solid var(--border)}")
    css_parts.append(".st-it:last-child{border-right:none}")
    css_parts.append(".st-v{font-family:'Syne',sans-serif;font-size:19px;font-weight:700;line-height:1}")
    css_parts.append(".st-l{font-family:'DM Mono',monospace;font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text2);margin-top:2px}")
    css_parts.append(".cg{color:var(--accent)} .cr{color:var(--accent3)} .ca{color:var(--warn)} .cb{color:var(--accent2)}")
    css_parts.append("#tabs-bar{display:flex;align-items:center;background:var(--surface);border-bottom:1px solid var(--border);padding:0 16px;flex-shrink:0}")
    css_parts.append(".tab-btn{font-family:'DM Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:.07em;padding:10px 14px;border:none;background:transparent;color:var(--text2);cursor:pointer;border-bottom:2px solid transparent;transition:all var(--t);white-space:nowrap}")
    css_parts.append(".tab-btn:hover{color:var(--text)}")
    css_parts.append(".tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}")
    css_parts.append(".tcnt{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;margin-left:5px;background:var(--surface2);color:var(--text2)}")
    css_parts.append(".tab-btn.active .tcnt{background:rgba(0,221,160,.15);color:var(--accent)}")
    css_parts.append("#wb{display:flex;background:var(--surface);border-bottom:1px solid var(--border);padding:6px 16px;flex-wrap:wrap;gap:12px;flex-shrink:0}")
    css_parts.append(".wl{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2)}")
    css_parts.append(".wdot{width:7px;height:7px;border-radius:50%}")
    css_parts.append(".tab-pane{display:none;flex:1;overflow-y:auto;padding:14px 16px}")
    css_parts.append(".tab-pane.visible{display:block}")
    css_parts.append(".tab-pane::-webkit-scrollbar{width:3px}")
    css_parts.append(".tab-pane::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}")
    css_parts.append(".dtable{width:100%;border-collapse:collapse;font-size:11px}")
    css_parts.append(".dtable th{font-family:'DM Mono',monospace;font-size:8px;text-transform:uppercase;letter-spacing:.07em;color:var(--text2);padding:6px 10px;border-bottom:1px solid var(--border);text-align:left;white-space:nowrap}")
    css_parts.append(".dtable td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:middle;color:var(--text)}")
    css_parts.append(".dtable tr:last-child td{border-bottom:none}")
    css_parts.append(".dr{cursor:pointer;transition:background var(--t)}")
    css_parts.append(".dr:hover td{background:var(--surface2)}")
    css_parts.append(".dr.sel td{background:rgba(0,221,160,.06)}")
    css_parts.append(".dr.sel td:first-child{border-left:2px solid var(--accent);padding-left:8px}")
    css_parts.append(".rr{cursor:pointer;transition:background var(--t)}")
    css_parts.append(".rr:hover td{background:var(--surface2)}")
    css_parts.append(".rr.sel td{background:rgba(255,107,82,.05)}")
    css_parts.append(".rr.sel td:first-child{border-left:2px solid var(--accent3);padding-left:8px}")
    css_parts.append(".rbg{font-family:'DM Mono',monospace;font-size:10px;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:var(--surface2);color:var(--text2)}")
    css_parts.append(".r1 .rbg{background:rgba(0,221,160,.15);color:var(--accent)}")
    css_parts.append(".sc{display:flex;align-items:center;gap:7px}")
    css_parts.append(".sn{font-family:'DM Mono',monospace;font-size:11px;min-width:40px}")
    css_parts.append(".bb{flex:1;height:4px;border-radius:2px;background:var(--surface2);overflow:hidden;min-width:40px}")
    css_parts.append(".bf{height:100%;border-radius:2px}")
    css_parts.append(".uch{font-family:'DM Mono',monospace;font-size:9px;padding:2px 7px;border-radius:4px}")
    css_parts.append(".uh{background:rgba(0,221,160,.1);color:var(--accent)}")
    css_parts.append(".um{background:rgba(246,167,42,.1);color:var(--warn)}")
    css_parts.append(".ul{background:rgba(255,107,82,.1);color:var(--accent3)}")
    css_parts.append(".rch{font-family:'DM Mono',monospace;font-size:9px;padding:2px 7px;border-radius:4px}")
    css_parts.append(".rbt{background:rgba(255,107,82,.1);color:var(--accent3)}")
    css_parts.append(".rpr{background:rgba(246,167,42,.1);color:var(--warn)}")
    css_parts.append(".cb2{display:flex;flex-direction:column;gap:2px}")
    css_parts.append(".cb3{height:3px;border-radius:2px;background:var(--accent2);max-width:60px}")
    css_parts.append(".eta{font-family:'DM Mono',monospace;font-size:11px;color:var(--accent2)}")
    css_parts.append(".empty{display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text2);font-size:12px;gap:8px;padding:40px;text-align:center}")
    css_parts.append(".ei{font-size:28px;opacity:.5}")
    css_parts.append(".sec{font-family:'DM Mono',monospace;font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--text2);margin-bottom:10px}")
    css_parts.append(".rbox{background:rgba(255,107,82,.07);border:1px solid rgba(255,107,82,.2);border-radius:6px;padding:10px 13px;font-size:11px;color:var(--accent3);margin-bottom:10px;display:flex;align-items:flex-start;gap:8px;line-height:1.5}")
    css_parts.append(".rbox.pr{background:rgba(246,167,42,.07);border-color:rgba(246,167,42,.2);color:var(--warn)}")
    css_parts.append(".ptleg{font-size:11px;display:flex;align-items:center;gap:6px;color:var(--text2)}")
    css_parts.append(".ptd{width:10px;height:10px;border-radius:50%;flex-shrink:0}")
    css_parts.append(".nomatch{background:rgba(0,221,160,.05);border:1px solid rgba(0,221,160,.15);border-radius:var(--radius);padding:16px;font-size:12px;color:var(--accent);text-align:center;margin-top:8px}")
    css = "\n".join(css_parts)

    # -----------------------------------------------------------------------
    # JS string
    # -----------------------------------------------------------------------
    js_parts = []
    js_parts.append("const CASES = " + cases_json + ";")
    js_parts.append("const RCOLS = ['#00dda0','#4d8fff','#ff6b52','#f6a72a','#a975ff'];")
    js_parts.append("const VCLS = {sedan:'🚗',suv:'🚙',hatchback:'🚗',pickup:'🛻'};")

    js_parts.append("const map = L.map('leaflet-map',{zoomControl:false}).setView([25.69,-100.32],11);")
    js_parts.append("L.control.zoom({position:'bottomright'}).addTo(map);")
    js_parts.append("const darkT = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'CartoDB',maxZoom:19});")
    js_parts.append("const lightT = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'CartoDB',maxZoom:19});")
    js_parts.append("darkT.addTo(map);")
    js_parts.append("let curTiles = darkT, isDark = true;")
    js_parts.append("let mapL = [], activeCase = null, activeCBtn = null, activeM = null, activeR = null;")

    js_parts.append("function clearML(){mapL.forEach(l=>map.removeLayer(l));mapL=[];}")

    js_parts.append("""function mkMarker(color, line1, line2){
  return L.divIcon({
    html:'<div style="background:'+color+';color:#0b0d11;font-family:DM Mono,monospace;font-size:10px;font-weight:600;padding:5px 10px;border-radius:6px;white-space:nowrap;box-shadow:0 3px 12px rgba(0,0,0,.45);line-height:1.3">'
      +line1+(line2?'<br><span style="font-size:9px;opacity:.7">'+line2+'</span>':'')+'</div>',
    className:'', iconAnchor:[0,0]
  });
}""")

    # CORRECCIÓN 6: marcadores de inicio/fin del conductor
    js_parts.append("""function mkDriverMarker(color, label){
  return L.divIcon({
    html:'<div style="background:'+color+';color:#fff;font-family:DM Mono,monospace;font-size:9px;font-weight:700;padding:3px 8px;border-radius:4px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.5);opacity:.92;border:1px solid rgba(255,255,255,.2)">'+label+'</div>',
    className:'', iconAnchor:[0,0]
  });
}""")

    js_parts.append("""document.getElementById('theme-btn').addEventListener('click',function(){
  isDark=!isDark;
  document.body.classList.toggle('light',!isDark);
  this.textContent=isDark?'☀️':'🌙';
  map.removeLayer(curTiles);
  curTiles = isDark ? darkT : lightT;
  curTiles.addTo(map);
});""")

    js_parts.append("""(function(){
  const sb=document.getElementById('sidebar');
  document.getElementById('sb-col').addEventListener('click',function(){
    const c=sb.classList.toggle('collapsed');
    this.textContent=c?'▶':'◀';
  });
  const h=document.getElementById('sb-rz');
  let drag=false,sx=0,sw=0;
  h.addEventListener('mousedown',function(e){drag=true;sx=e.clientX;sw=sb.offsetWidth;document.body.style.cursor='col-resize';document.body.style.userSelect='none';});
  document.addEventListener('mousemove',function(e){if(!drag)return;sb.style.width=Math.max(180,Math.min(460,sw+e.clientX-sx))+'px';});
  document.addEventListener('mouseup',function(){drag=false;document.body.style.cursor='';document.body.style.userSelect='';});
})();""")

    js_parts.append("""(function(){
  const mw=document.getElementById('map-wrap');
  const h=document.getElementById('map-rz');
  let drag=false,sy=0,sh=0;
  h.addEventListener('mousedown',function(e){drag=true;sy=e.clientY;sh=mw.offsetHeight;document.body.style.cursor='row-resize';document.body.style.userSelect='none';});
  document.addEventListener('mousemove',function(e){
    if(!drag)return;
    const right=document.getElementById('right');
    const maxH=right.offsetHeight-120;
    mw.style.flex='none';
    mw.style.height=Math.max(80,Math.min(maxH,sh+e.clientY-sy))+'px';
    map.invalidateSize();
  });
  document.addEventListener('mouseup',function(){drag=false;document.body.style.cursor='';document.body.style.userSelect='';});
})();""")

    js_parts.append("""document.querySelectorAll('.tab-btn').forEach(function(btn){
  btn.addEventListener('click',function(){
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    this.classList.add('active');
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('visible'));
    document.getElementById('pane-'+this.dataset.tab).classList.add('visible');
  });
});""")

    # CORRECCIÓN 6: showMap actualizado para mostrar inicio/fin del conductor
    js_parts.append("""function showMap(c, idx, isRej){
  clearML();
  const i = idx||0;
  if(!isRej){
    c.matches.forEach(function(m,j){
      if(!m.waypoints||!m.waypoints.length)return;
      const act=j===i;
      const poly=L.polyline(m.waypoints,{
        color:act?RCOLS[j%RCOLS.length]:(isDark?'#1e2840':'#c8d0e0'),
        weight:act?5:2, opacity:act?.95:.45
      }).addTo(map);
      mapL.push(poly);
    });
    const m=c.matches[i];
    if(m){
      document.getElementById('map-ov').innerHTML='<div class="ov-case">Caso '+c.case_num+' — '+m.driver+'</div>'
        +'<div class="ov-desc">'+c.description+'</div>'
        +'<div class="ov-chips">'
        +'<span class="ov-chip" style="color:var(--accent)">Score '+m.score.toFixed(3)+'</span>'
        +'<span class="ov-chip" style="color:var(--accent2)">ETA en A: '+m.pickup_eta+'</span>'
        +'<span class="ov-chip">'+m.coverage.toFixed(0)+'% cobertura</span>'
        +'</div>';
      // Marcadores inicio/fin del conductor (ruta activa)
      if(m.driver_start){
        const ds=L.marker(m.driver_start,{icon:mkDriverMarker('#4d8fff','Inicio conductor')}).addTo(map);
        ds.bindTooltip('<b>Inicio del conductor</b><br>'+m.driver,{direction:'right'});
        mapL.push(ds);
      }
      if(m.driver_end){
        const de=L.marker(m.driver_end,{icon:mkDriverMarker('#a975ff','Fin conductor')}).addTo(map);
        de.bindTooltip('<b>Destino del conductor</b><br>'+m.driver,{direction:'right'});
        mapL.push(de);
      }
    }
  } else {
    const r=c.rejected_list[i];
    if(r&&r.waypoints&&r.waypoints.length){
      const col=r.reject_type==='backtrack'?'#ff6b52':'#f6a72a';
      const poly=L.polyline(r.waypoints,{color:col,weight:4,opacity:.8,dashArray:'8,6'}).addTo(map);
      mapL.push(poly);
      map.fitBounds(L.latLngBounds(r.waypoints),{padding:[40,40]});
      // Marcadores inicio/fin del conductor rechazado
      if(r.driver_start){
        const ds=L.marker(r.driver_start,{icon:mkDriverMarker('#4d8fff','🚗 Inicio conductor')}).addTo(map);
        ds.bindTooltip('<b>Inicio del conductor</b><br>'+r.driver,{direction:'right'});
        mapL.push(ds);
      }
      if(r.driver_end){
        const de=L.marker(r.driver_end,{icon:mkDriverMarker('#a975ff','🏁 Fin conductor')}).addTo(map);
        de.bindTooltip('<b>Destino del conductor</b><br>'+r.driver,{direction:'right'});
        mapL.push(de);
      }
    }
    // CORRECCIÓN 7: mostrar score parcial en rechazados
    const scoreStr = (r.partial_score!==undefined&&r.partial_score!==null)
      ? ' · Score hipotético: <span style="color:var(--warn);font-family:DM Mono,monospace">'+r.partial_score.toFixed(3)+'</span>' : '';
    document.getElementById('map-ov').innerHTML='<div class="ov-case" style="color:var(--accent3)">⛔ Ruta Rechazada — '+r.driver+'</div>'
      +'<div class="ov-desc">'+r.reason_label+scoreStr+'</div>';
  }
  const pA=L.marker([c.pickup_lat,c.pickup_lng],{icon:mkMarker('#00dda0','A — Pasajero sube',c.pickup_address?c.pickup_address.split(',')[0]:'')}).addTo(map);
  const pB=L.marker([c.dropoff_lat,c.dropoff_lng],{icon:mkMarker('#ff6b52','B — Pasajero baja',c.dropoff_address?c.dropoff_address.split(',')[0]:'')}).addTo(map);
  pA.bindTooltip('<b>Punto A — Sube el pasajero</b><br>'+c.pickup_address,{direction:'right'});
  pB.bindTooltip('<b>Punto B — Baja el pasajero</b><br>'+c.dropoff_address,{direction:'right'});
  mapL.push(pA,pB);
  if(!isRej){
    const pts=[[c.pickup_lat,c.pickup_lng],[c.dropoff_lat,c.dropoff_lng]];
    const m=c.matches[i];
    if(m&&m.waypoints&&m.waypoints.length)pts.push(...m.waypoints);
    map.fitBounds(L.latLngBounds(pts),{padding:[50,50]});
  }
}""")

    js_parts.append("""function renderMatches(c){
  const pane=document.getElementById('pane-matches');
  if(!c||!c.matches.length){
    pane.innerHTML='<div class="nomatch">✓ Sin coincidencias válidas — respuesta correcta para este caso de prueba</div>';
    return;
  }
  const ptleg='<div style="display:flex;gap:16px;margin-bottom:10px;flex-wrap:wrap">'
    +'<div class="ptleg"><div class="ptd" style="background:#00dda0"></div>A — Punto donde el pasajero sube</div>'
    +'<div class="ptleg"><div class="ptd" style="background:#ff6b52"></div>B — Punto donde el pasajero baja</div>'
    +'<div class="ptleg"><div style="width:18px;height:3px;border-radius:2px;background:#4d8fff"></div>Ruta del conductor (activa)</div>'
    +'<div class="ptleg"><div class="ptd" style="background:#4d8fff"></div>Inicio conductor</div>'
    +'<div class="ptleg"><div class="ptd" style="background:#a975ff"></div>Fin conductor</div>'
    +'</div>';
  const sec='<div class="sec">Top '+c.matches.length+' coincidencias · clic en conductor para ver su ruta</div>';
  let rows='';
  c.matches.forEach(function(m,i){
    const uc=m.utility_index>=60?'uh':m.utility_index>=35?'um':'ul';
    const ul=m.utility_index>=60?'▲ Alta':m.utility_index>=35?'◆ Media':'▼ Baja';
    const v=VCLS[m.vehicle]||'🚗';
    const col=RCOLS[i%RCOLS.length];
    rows+='<tr class="dr'+(i===0?' r1':'')+'" data-mi="'+i+'">'
      +'<td><span class="rbg">'+m.rank+'</span></td>'
      +'<td><div style="font-weight:500;font-size:12px">'+m.driver+'</div>'
        +'<div style="font-size:10px;color:var(--text2);margin-top:2px">'+v+' '+m.vehicle+' · '+m.seats+' asiento'+(m.seats>1?'s':'')+'</div></td>'
      +'<td><div style="font-family:DM Mono,monospace;font-size:11px">'+m.departure_time+'</div>'
      +'<td><span class="eta">'+m.pickup_eta+'</span></td>'
      +'<td><div class="sc">'
        +'<span class="sn" style="color:'+(i===0?'var(--accent)':'var(--text)')+'">'+m.score.toFixed(3)+'</span>'
        +'<div class="bb"><div class="bf" style="width:'+(m.score*100).toFixed(0)+'%;background:'+col+'"></div></div>'
        +'</div></td>'
      +'<td><div class="cb2"><span style="font-family:DM Mono,monospace;font-size:11px">'+m.coverage.toFixed(0)+'%</span>'
        +'<div class="cb3" style="width:'+Math.min(60,m.coverage*.6)+'px"></div></div></td>'
      +'<td><span class="uch '+uc+'">'+ul+' '+m.utility_index.toFixed(0)+'</span></td>'
      +'<td style="font-family:DM Mono,monospace;font-size:11px">'+(m.dist_pickup_km*1000).toFixed(0)+' m</td>'
      +'<td style="font-family:DM Mono,monospace;font-size:11px">'+(m.dist_dropoff_km*1000).toFixed(0)+' m</td>'
      +'<td style="font-family:DM Mono,monospace;font-size:11px">'+m.detour_km.toFixed(2)+' km</td>'
      +'</tr>';
  });
  const tbl='<table class="dtable"><thead><tr>'
    +'<th>#</th><th>Conductor</th><th>Salida</th><th>ETA en A</th>'
    +'<th>Score</th><th>Cobertura</th><th>Utilidad</th>'
    +'<th>A→Ruta</th><th>B→Ruta</th><th>Desvío</th>'
    +'</tr></thead><tbody>'+rows+'</tbody></table>';
  pane.innerHTML=sec+ptleg+tbl;
  pane.querySelectorAll('.dr').forEach(function(row){
    row.addEventListener('click',function(){
      if(activeM)activeM.classList.remove('sel');
      row.classList.add('sel'); activeM=row;
      showMap(c,parseInt(row.dataset.mi),false);
    });
  });
}""")

    # CORRECCIÓN 7: renderRejected muestra score parcial en tabla
    js_parts.append("""function renderRejected(c){
  const pane=document.getElementById('pane-rejected');
  const tot=c.rejected_backtrack+c.rejected_proximity;
  if(!tot){
    pane.innerHTML='<div class="empty"><div class="ei">✓</div><div>No hubo rechazos en este caso</div></div>';
    return;
  }
  const btl=c.rejected_list.filter(r=>r.reject_type==='backtrack');
  const prl=c.rejected_list.filter(r=>r.reject_type==='proximity');
  const sec='<div class="sec">Muestra de '+c.rejected_list.length+' rechazos de '+tot+' totales · clic para ver ruta (línea punteada)</div>';
  const ebt=btl.length?'<div class="rbox"><span>⛔</span><div>'
    +'<b>Backtracking ('+c.rejected_backtrack+' rutas):</b> El Punto B (bajada) aparece ANTES que el Punto A (subida) '
    +'en el sentido de la ruta del conductor. Aceptarlas obligaría a dar marcha atrás. Descartadas automáticamente.</div></div>':'';
  const epr=prl.length?'<div class="rbox pr"><span>📍</span><div>'
    +'<b>Fuera de rango ('+c.rejected_proximity+' rutas):</b> El Punto A o B del pasajero '
    +'está a más de 2.5 km de la polilínea del conductor. Demasiado lejos para compartir cómodamente.</div></div>':'';
  let rows='';
  c.rejected_list.forEach(function(r,i){
    const bt=r.reject_type==='backtrack';
    const ps=(r.partial_score!==undefined&&r.partial_score!==null)?r.partial_score.toFixed(3):'—';
    rows+='<tr class="rr" data-ri="'+i+'">'
      +'<td><span class="rch '+(bt?'rbt':'rpr')+'">'+(bt?'⛔ Backtrack':'📍 Proximidad')+'</span></td>'
      +'<td><div style="font-size:11px;font-weight:500">'+r.driver+'</div>'
        +'<div style="font-size:10px;color:var(--text2)">'+r.departure_time+'</div></td>'
      +'<td style="font-size:10px;color:var(--text2);max-width:200px">'+r.reason_label+'</td>'
      +'<td style="font-family:DM Mono,monospace;font-size:10px">'
        +(bt?'Idx A='+r.idx_pickup+' / Idx B='+r.idx_dropoff
           :(r.dist_pickup_km*1000).toFixed(0)+'m / '+(r.dist_dropoff_km*1000).toFixed(0)+'m')
      +'</td>'
      +'<td><div class="sc"><span class="sn" style="color:var(--warn);font-size:10px">'+ps+'</span>'
        +'<div class="bb"><div class="bf" style="width:'+(r.partial_score?(r.partial_score*100).toFixed(0):0)+'%;background:var(--warn)"></div></div>'
        +'</div><div style="font-size:9px;color:var(--text2);margin-top:2px">score hipotético</div></td>'
      +'</tr>';
  });
  const tbl='<table class="dtable"><thead><tr><th>Tipo</th><th>Conductor</th><th>Razón</th><th>Detalle</th><th>Score (si hubiera pasado)</th></tr></thead>'
    +'<tbody>'+rows+'</tbody></table>';
  pane.innerHTML=sec+ebt+epr+tbl;
  pane.querySelectorAll('.rr').forEach(function(row){
    row.addEventListener('click',function(){
      if(activeR)activeR.classList.remove('sel');
      row.classList.add('sel'); activeR=row;
      showMap(c,parseInt(row.dataset.ri),true);
    });
  });
}""")

    js_parts.append("""function renderStats(c){
  const pane=document.getElementById('pane-stats');
  function card(lbl,val,cc,desc){
    return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px">'
      +'<div class="st-v '+cc+'">'+val+'</div>'
      +'<div style="font-size:12px;font-weight:500;margin-top:2px">'+lbl+'</div>'
      +'<div style="font-size:10px;color:var(--text2);margin-top:3px">'+desc+'</div>'
      +'</div>';
  }
  const tot=c.rejected_backtrack+c.rejected_proximity+c.total_valid;
  const cards='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px">'
    +card('Rutas válidas',c.total_valid,'cg','Pasaron todos los filtros')
    +card('Backtracking',c.rejected_backtrack,'cr','Punto B antes de Punto A en ruta')
    +card('Fuera de rango',c.rejected_proximity,'ca','Distancia > 2.5 km')
    +card('Total evaluadas',tot,'cb','Rutas del mismo día')
    +'</div>';
  const ws=[
    {l:'Dirección',p:25,c:'#00dda0',d:'Gradual: mayor alineación = mayor score'},
    {l:'Cobertura',p:20,c:'#4d8fff',d:'% trayecto del pasajero cubierto'},
    {l:'Horario',p:20,c:'#f6a72a',d:'Ventana de tiempo ±60 min'},
    {l:'Desvío',p:20,c:'#ff6b52',d:'Km extra del conductor'},
    {l:'Utilidad',p:15,c:'#a975ff',d:'Cobertura sin doble penalización'},
  ];
  let wchart='<div style="display:flex;flex-direction:column;gap:8px">';
  ws.forEach(function(w){
    wchart+='<div style="display:flex;align-items:center;gap:10px">'
      +'<div style="min-width:80px;font-size:11px;font-weight:500">'+w.l+'</div>'
      +'<div style="flex:1;height:14px;background:var(--surface2);border-radius:4px;overflow:hidden">'
        +'<div style="height:100%;width:'+(w.p*4)+'px;background:'+w.c+';border-radius:4px"></div>'
      +'</div>'
      +'<div style="font-family:DM Mono,monospace;font-size:11px;min-width:30px;color:'+w.c+'">'+w.p+'%</div>'
      +'<div style="font-size:10px;color:var(--text2);min-width:180px">'+w.d+'</div>'
      +'</div>';
  });
  wchart+='</div>';
  pane.innerHTML=cards+'<div style="margin-top:16px"><div class="sec">Distribución de pesos del score</div>'+wchart+'</div>';
}""")

    js_parts.append("""function selCase(c, btn){
  activeCase=c;
  if(activeCBtn)activeCBtn.classList.remove('active');
  btn.classList.add('active'); activeCBtn=btn;
  activeM=null; activeR=null;
  document.getElementById('sv-val').textContent=c.total_valid;
  document.getElementById('sv-bt').textContent=c.rejected_backtrack;
  document.getElementById('sv-pr').textContent=c.rejected_proximity + c.rejected_date||0;
  document.querySelector('[data-tab="matches"] .tcnt').textContent=c.total_valid;
  document.querySelector('[data-tab="rejected"] .tcnt').textContent=c.rejected_backtrack+c.rejected_proximity;
  renderMatches(c);
  renderRejected(c);
  renderStats(c);
  showMap(c,0,false);
}""")

    js_parts.append("""const cl=document.getElementById('case-list');
CASES.forEach(function(c,i){
  const btn=document.createElement('button');
  btn.className='case-btn';
  btn.innerHTML='<span class="cnum">0'+c.case_num+'</span>'
    +'<span style="flex:1;min-width:0">'
      +'<span class="ctitle">'+c.description+'</span>'
      +'<span class="csub">'
        +'<span class="badge '+c.badge+'">'+c.badge_text+'</span>'
        +'<span style="font-size:10px;color:var(--text2)">'+c.rejected_backtrack+' BT</span>'
      +'</span>'
    +'</span>';
  btn.addEventListener('click',function(){selCase(c,btn);});
  cl.appendChild(btn);
  if(i===0)setTimeout(function(){btn.click();},350);
});""")

    js = "\n".join(js_parts)

    # -----------------------------------------------------------------------
    # Assemble HTML
    # -----------------------------------------------------------------------
    parts = []

    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="es">')
    parts.append("<head>")
    parts.append('<meta charset="UTF-8"/>')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1.0"/>')
    parts.append("<title>Puul Hackathon — Resultados</title>")
    parts.append('<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>')
    parts.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    parts.append('<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">')
    parts.append("<style>" + css + "</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Header
    parts.append('<div id="header">')
    parts.append('<div class="logo">PUUL<em>.</em></div>')
    parts.append("<h1>Hackathon FACPyA &mdash; Motor de matching geoespacial &mdash; Monterrey 2026</h1>")
    parts.append('<div style="display:flex;gap:8px;align-items:center">')
    parts.append('<span class="hpill">200 rutas</span>')
    parts.append('<span class="hpill">6 casos</span>')
    parts.append('<span class="hpill">WGS84</span>')
    parts.append('<button id="theme-btn" title="Cambiar tema">&#9728;&#65039;</button>')
    parts.append("</div>")
    parts.append("</div>")

    # Layout
    parts.append('<div id="layout">')

    # Sidebar
    parts.append('<div id="sidebar">')
    parts.append('<div id="sidebar-head">')
    parts.append("<span>Casos de prueba</span>")
    parts.append('<button class="cbtn" id="sb-col" title="Colapsar">&#9668;</button>')
    parts.append("</div>")
    parts.append('<div id="case-list"></div>')
    parts.append('<div class="rhandle" id="sb-rz"></div>')
    parts.append("</div>")

    # Right
    parts.append('<div id="right">')

    # Map
    parts.append('<div id="map-wrap">')
    parts.append('<div id="leaflet-map"></div>')
    parts.append('<div id="map-ov">')
    parts.append('<div class="ov-case">&#8592; Selecciona un caso</div>')
    parts.append('<div class="ov-desc">El mapa mostrará la ruta del conductor y los puntos A y B del pasajero</div>')
    parts.append("</div>")

    # Map legend
    parts.append('<div id="map-leg">')
    parts.append('<div class="leg-item"><div class="leg-dot" style="background:#00dda0"></div>A &mdash; Sube</div>')
    parts.append('<div class="leg-item"><div class="leg-dot" style="background:#ff6b52"></div>B &mdash; Baja</div>')
    parts.append('<div class="leg-item"><div class="leg-line" style="background:#4d8fff"></div>Conductor (match)</div>')
    parts.append('<div class="leg-item"><div class="leg-dot" style="background:#4d8fff"></div>Inicio conductor</div>')
    parts.append('<div class="leg-item"><div class="leg-dot" style="background:#a975ff"></div>Fin conductor</div>')
    parts.append('<div class="leg-item"><div class="leg-line" style="background:#ff6b52;opacity:.7"></div>Rechazado (---)</div>')
    parts.append("</div>")
    parts.append("</div>")

    # Map resize
    parts.append('<div id="map-rz"></div>')

    # Bottom
    parts.append('<div id="bot">')

    # Stats strip
    parts.append('<div id="stats-strip">')
    parts.append('<div class="st-it"><div class="st-v cg" id="sv-val">&mdash;</div><div class="st-l">Matches</div></div>')
    parts.append('<div class="st-it"><div class="st-v cr" id="sv-bt">&mdash;</div><div class="st-l">Backtrack</div></div>')
    parts.append('<div class="st-it"><div class="st-v ca" id="sv-pr">&mdash;</div><div class="st-l">Proximidad</div></div>')
    parts.append("</div>")

    # Tabs bar
    parts.append('<div id="tabs-bar">')
    parts.append('<button class="tab-btn active" data-tab="matches">Coincidencias <span class="tcnt">&mdash;</span></button>')
    parts.append('<button class="tab-btn" data-tab="rejected">Rechazados <span class="tcnt">&mdash;</span></button>')
    parts.append('<button class="tab-btn" data-tab="stats">An&aacute;lisis</button>')
    parts.append("</div>")

    # Weight bar
    parts.append('<div id="wb">')
    parts.append('<div class="wl"><div class="wdot" style="background:#00dda0"></div>Direcci&oacute;n 25%</div>')
    parts.append('<div class="wl"><div class="wdot" style="background:#4d8fff"></div>Cobertura 20%</div>')
    parts.append('<div class="wl"><div class="wdot" style="background:#f6a72a"></div>Horario 20%</div>')
    parts.append('<div class="wl"><div class="wdot" style="background:#ff6b52"></div>Desv&iacute;o 20%</div>')
    parts.append('<div class="wl"><div class="wdot" style="background:#a975ff"></div>Utilidad 15%</div>')
    parts.append("</div>")

    # Tab panes
    parts.append('<div style="flex:1;overflow:hidden;display:flex;flex-direction:column">')
    parts.append('<div id="pane-matches" class="tab-pane visible">')
    parts.append('<div class="empty"><div class="ei">&#128072;</div><div>Selecciona un caso para ver los matches</div></div>')
    parts.append("</div>")
    parts.append('<div id="pane-rejected" class="tab-pane">')
    parts.append('<div class="empty"><div class="ei">&#128072;</div><div>Selecciona un caso para ver rechazados</div></div>')
    parts.append("</div>")
    parts.append('<div id="pane-stats" class="tab-pane">')
    parts.append('<div class="empty"><div class="ei">&#128072;</div><div>Selecciona un caso para ver el an&aacute;lisis</div></div>')
    parts.append("</div>")
    parts.append("</div>")  # panes wrapper

    parts.append("</div>")  # bot
    parts.append("</div>")  # right
    parts.append("</div>")  # layout

    parts.append('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')
    parts.append("<script>")
    parts.append(js)
    parts.append("</script>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)

html_content = build_html(all_results)
output_path = os.path.join(base_path, "resultado_hackathon.html")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print("")
print("HTML generado: " + output_path)
print("Coloca este archivo junto a routes.csv y sample_searches.csv, ejecuta con:")
print("  python main.py")
print("Luego abre resultado_hackathon.html en tu navegador.")

print("\n=== OUTPUT MATCHES ===\n")

for r in all_results:
    print(f"\nCaso {r['case_num']}:")
    
    matches_out = []

    for i, m in enumerate(r["matches"]):
        matches_out.append({
            "rank": i + 1,
            "route_id": m["route_id"],
            "driver_name": m["driver"],
            "score": m["score"],
            "pickup_distance_to_route_m": int(m["details"]["dist_pickup_km"] * 1000),
            "dropoff_distance_to_route_m": int(m["details"]["dist_dropoff_km"] * 1000),
            "pickup_index_on_route": m["details"]["idx_pickup"],
            "dropoff_index_on_route": m["details"]["idx_dropoff"],
            "rider_trip_coverage_pct": m["details"]["coverage"],
            "driver_detour_m": int(m["details"]["detour_km"] * 1000)
        })

    output = {
        "matches": matches_out
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))

    json_output_path = os.path.join(base_path, "resultado_matches.json")

all_cases_output = []

print("\n=== OUTPUT MATCHES ===\n")

for r in all_results:
    print(f"\nCaso {r['case_num']}:")
    
    matches_out = []

    for i, m in enumerate(r["matches"]):
        matches_out.append({
            "rank": i + 1,
            "route_id": m["route_id"],
            "driver_name": m["driver"],
            "score": m["score"],
            "pickup_distance_to_route_m": int(m["details"]["dist_pickup_km"] * 1000),
            "dropoff_distance_to_route_m": int(m["details"]["dist_dropoff_km"] * 1000),
            "pickup_index_on_route": m["details"]["idx_pickup"],
            "dropoff_index_on_route": m["details"]["idx_dropoff"],
            "rider_trip_coverage_pct": m["details"]["coverage"],
            "driver_detour_m": int(m["details"]["detour_km"] * 1000)
        })

    case_output = {
        "case_num": r["case_num"],
        "matches": matches_out
    }

    all_cases_output.append(case_output)

    # Sigue imprimiendo en consola (opcional)
    print(json.dumps(case_output, indent=2, ensure_ascii=False))


# Guardar TODO en un solo archivo JSON
with open(json_output_path, "w", encoding="utf-8") as f:
    json.dump(all_cases_output, f, indent=2, ensure_ascii=False)

print("\nJSON generado en:", json_output_path)