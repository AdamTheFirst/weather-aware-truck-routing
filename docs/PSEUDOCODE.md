# Plan / pseudocode

> Written before coding, to think the problem through. The `> Notes:` lines are my reasoning.

## 1. Understand the problem

> Notes: The question is which road to drive, given the weather at the time the truck will actually be there, the load, and how long the drive takes.

Inputs: origin, destination, departure time, load (lb), sample interval (10/25/50 mi)
Output: 3 routes, each with checkpoints + risk; one recommended route; heatmap for 0–48 h

## 2. Overall flow

```
plan_trip(origin, destination, departure, load, interval):
    routes = routing_api.get_routes(origin, destination, count = 3)
    if fewer than 3:
        add via-points left/right of the straight line and ask again
        drop near-duplicates and silly detours

    for each route:
        segments = route geometry with time per segment
        cap each segment's speed at truck speed (65 mph)
        checkpoints = walk along route, every `interval` miles:
                          position = interpolate inside segment
                          eta      = departure + time so far
        always add destination as last checkpoint

    grid = points around all routes (for heatmap), limited to ~120

    weather = weather_api.hourly(all checkpoints + grid, from departure to departure + max(48h, trip))
              (batch many locations per request, run in parallel)

    for each checkpoint:
        w = weather at hour closest to its eta
        risk = classify(w.wind, w.rain, w.snow, load)

    for each route:
        summary = miles per risk level + average risk

    best = recommend(routes)

    heatmap[point][hour] = classify(weather[point][hour], load) for hour 0..48

    return routes, best, reason, heatmap
```

> Notes: One batched weather call covers every checkpoint and every heatmap hour. The slider then only recolors data it already has, so scrubbing makes no further requests.

## 3. Risk for one checkpoint

```
classify(wind, rain, snow, load):
    wind_level = band(wind, [25, 35, 45, 55])
    rain_level = band(rain, [0.10, 0.25, 0.50]),  No Travel if rain > 1.00
    snow_level = band(snow, [0.5, 1.0, 2.0]),     No Travel if snow > 3.0

    # load rules (only wind is affected)
    if wind >= 55:                       wind_level = NO_TRAVEL
    elif 45 <= wind < 55 and load > 30k: wind_level = NO_TRAVEL
    elif 35 <= wind < 45 and load > 40k: wind_level = max(wind_level, SEVERE)

    return max(wind_level, rain_level, snow_level)   # worst condition wins
```

> Notes: Shared edges go to the higher band, so rain at 0.25 in/hr is High, not Moderate. A value sitting on a boundary should warn, not reassure. Rain and snow No Travel stay strictly greater-than, so 1.00 in/hr of rain is still Severe. Classification uses the raw forecast; rounding is display-only.

## 4. From points to miles

```
for each pair of consecutive checkpoints (a, b):
    length = b.mile - a.mile
    level  = max(a.level, b.level)       # cautious: worse end wins
    miles[level] += length
avg_risk = sum(level * length) / total length
```

> Notes: The rules talk about miles, and we only know the weather at points. If either end of a stretch is severe, the whole stretch counts as severe. Over-warning a driver is cheaper than missing a bad stretch.

## 5. Recommendation

```
sort routes by (no_travel_miles, severe_miles, high_miles, avg_risk, duration)
pick first
```

> Notes: The brief's order is Severe miles, then High miles, then average risk, then time. No Travel is worse than Severe, so it ranks first. Average risk is compared with a tolerance of 0.25 (levels are 0–4, and this step only runs once the higher bands are tied). A smaller gap falls through to travel time. Via routes slower than 1.25× the fastest route are dropped before ranking.

## 6. Frontend

```
form -> POST /api/plan -> store plan
map:
    draw 3 polylines (selected one on top)
    draw checkpoints coloured by risk, popup with eta + weather + why
    heatmap layer = canvas; on slider change -> recolour points for that hour
sidebar:
    route cards: distance, time, risk bar, "Recommended" badge + reason
```

> Notes: leaflet.heat draws density, so overlapping points add up. This map is a value at each point. A canvas layer recolors those points when the slider moves and does not call the server. The grid is capped at about 120 points.

## 7. Edge cases I thought about

- Same origin and destination -> 400
- Departure in the past / beyond the forecast range -> 400
- Routing or weather API down -> 502 with a readable message
- Trip longer than 48 h -> fetch weather for the whole trip, not just 48 h
- Last stretch shorter than the interval -> still add the destination checkpoint
- Missing (null) hours from the weather API -> treated as calm/dry
