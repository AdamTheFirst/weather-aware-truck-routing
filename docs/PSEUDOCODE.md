# Plan / pseudocode

> Written before coding, to think the problem through. The `> Notes:` lines are my reasoning.

## 1. Understand the problem

> Notes: _TODO (your own words): what is the real question here? ("which road, given weather at the time I'll be on it")_

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

    grid = points around all routes (for heatmap), limited to ~200

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

> Notes: _TODO: why get all the weather in one go? (one round trip, and the slider then needs no server calls)_

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

> Notes: _TODO: the table has shared edges (0.25 is in two bands). I decided ______ because ______._

## 4. From points to miles

```
for each pair of consecutive checkpoints (a, b):
    length = b.mile - a.mile
    level  = max(a.level, b.level)       # cautious: worse end wins
    miles[level] += length
avg_risk = sum(level * length) / total length
```

> Notes: _TODO: why "worse end" and not "nearest checkpoint"?_

## 5. Recommendation

```
sort routes by (no_travel_miles, severe_miles, high_miles, avg_risk, duration)
pick first
```

> Notes: _TODO: No Travel isn't in the brief's list. Why I put it first._

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

> Notes: _TODO: why a custom canvas layer instead of a heatmap plugin?_

## 7. Edge cases I thought about

- Same origin and destination -> 400
- Departure in the past / beyond the forecast range -> 400
- Routing or weather API down -> 502 with a readable message
- Trip longer than 48 h -> fetch weather for the whole trip, not just 48 h
- Last stretch shorter than the interval -> still add the destination checkpoint
- Missing (null) hours from the weather API -> treated as calm/dry
- _TODO: add any you think of_
