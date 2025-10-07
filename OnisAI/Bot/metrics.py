# Metrics: £/mi, £/min, hourly (nominal/adjusted), fuel costs, pay status

# Thresholds (unchanged)
GOOD_HOURLY_MIN = 28.0   # >= GOOD
BAD_HOURLY_MAX  = 22.0   # <  BAD
OVERHEAD_MINUTES = 2     # added to trip_min for conservative hourly

# Fuel math (unchanged)
PRICE_PER_KWH   = 17.83 / 44.57
MILES_PER_KWH   = 4.0
COST_PER_MILE   = PRICE_PER_KWH / MILES_PER_KWH

def calc_metrics(
    price: float,
    trip_mi: float,
    trip_min: int,
    pickup_mi: float,
    pickup_min: int,
    star: float,
    ocr_time: float,
    hourly_target: float = 30.0,   # <-- target for the adj padding sign
):
    # Unit rates
    per_mile = (price / trip_mi) if trip_mi else 0.0
    per_min  = (price / trip_min) if trip_min else 0.0

    # Hourly
    hourly_nominal = per_min * 60 if per_min else 0.0
    hourly_adj = (price / max(trip_min + OVERHEAD_MINUTES, 1) * 60.0) if trip_min > 0 else 0.0

    # Fuel
    fuel_pickup = pickup_mi * COST_PER_MILE
    fuel_trip   = trip_mi   * COST_PER_MILE
    fuel_total  = fuel_pickup + fuel_trip

    # Pay status by adjusted hourly
    if hourly_adj >= GOOD_HOURLY_MIN:
        status_str = "✅ GOOD"
    elif hourly_adj < BAD_HOURLY_MAX:
        status_str = "❌ BAD"
    else:
        status_str = "⚠️ LOW"

    # -------- PURE-MATH PADDING --------
    # Raw base = £/min (trip-only) + £/mi (trip-only)
    base_raw = per_min + per_mile

    # Adj base delta = (per_min including pickup) - (target £/min)
    #   Positive → you're AHEAD of the £/h target
    #   Negative → you’re SHORT of the £/h target
    total_min = trip_min + pickup_min
    total_mi  = trip_mi + pickup_mi
    per_min_adj  = (price / total_min) if total_min else 0.0
    per_mile_adj = (price / total_mi)  if total_mi  else 0.0
    target_per_min = hourly_target / 60.0  # e.g., £30/h → £0.50/min
    base_adj_delta = per_min_adj - target_per_min

    return {
        "per_mile": per_mile,
        "per_min": per_min,
        "hourly_nominal": hourly_nominal,
        "hourly_adj": hourly_adj,
        "OVERHEAD_MINUTES": OVERHEAD_MINUTES,
        "fuel_pickup": fuel_pickup,
        "fuel_trip": fuel_trip,
        "fuel_total": fuel_total,
        "status_str": status_str,
        "star": star,

        # New padding outputs
        "base_raw": base_raw,                 # trip-only £/min + £/mi
        "base_adj_delta": base_adj_delta,     # signed delta vs target (inc. pickup)
        "per_min_adj": per_min_adj,           # for reference if you want to display it
        "per_mile_adj": per_mile_adj,         # for reference
        "hourly_target": hourly_target,
    }
