# How I used AI on this project

## Summary
I used Claude as the implementer and kept the engineering decisions for myself. Before any code was written, I put together a build brief covering the stack, the exact risk and load rules, edge cases, performance targets and a phased plan. Once the build was done, I had the repository reviewed against the assessment PDF, decided which problems were worth fixing, directed the fixes and checked the results.

That is how I work with AI tools in general. They are fast at writing code to a clear spec. The parts that decide whether a project is right, like reading the requirements closely, settling ambiguities and checking the output against reality, are still my job.

## How I used AI
- **My part:** requirements, architecture, the risk boundary convention, the ranking order, the heatmap performance approach, the test strategy, review, fix priorities and verification.
- **Claude's part:** writing the Django and React code and the tests to the brief, one phase at a time, and reporting after each phase what worked and how to verify it.
- **Review:** I commissioned an independent review that checked the repository against the PDF with the test suite, a live trip and a browser run. I picked which findings to fix.

## Pre-build research and decisions
- **Free, key-less APIs** (Photon geocoding, public OSRM routing, Open-Meteo weather). A grader can run the app without signing up for anything, and no secrets touch the repo. OSRM also returns per-segment durations, which I needed for ETAs.
- **Risk boundaries.** The PDF's ranges share endpoints, so rain at 0.25 in/hr sits in both Moderate and High. I decided that a shared edge belongs to the higher band. Rain and snow No Travel is strictly above 1.00 and 3.0, as written, and the load rules use a strict `>` on weight.
- **No Travel ranked first.** The PDF ranks by Severe miles, then High miles, and doesn't mention No Travel. A route with No Travel miles should never beat one with only Severe miles, so No Travel miles lead the sort key. This is documented in the README.
- **Weather at the ETA.** ETAs come from OSRM's per-segment durations, interpolated inside a segment, with a 65 mph cap because the public profile is built for cars. Each checkpoint uses the forecast hour nearest its ETA.
- **Batching.** All checkpoints and heatmap grid points go to the weather API in batched calls of 100 locations each, sent in parallel. The browser makes one request per plan.
- **Heatmap precompute.** UI smoothness is 40% of the grade, so the backend classifies every grid point for all 49 hours and sends small integers. The slider only re-colours a canvas and makes no network calls.
- **Provider abstraction and fallback.** Base URLs live in settings. When OSRM returns fewer than three routes, a via point offset from the straight line forces a different road.
- **Testing.** Rules and ranking are pure Python with table-driven tests on every boundary and load threshold. External APIs are mocked.

The build differs from my brief in two places, and I accepted both. Route miles use the worse end of each stretch between checkpoints instead of midpoint ownership, which is more cautious and is documented. The heatmap is a custom Leaflet canvas layer instead of deck.gl.

## The instructions I gave
I started with a master prompt containing the full spec, then sent seven phase prompts one at a time: scaffold, risk engine, routing and geometry, weather and the plan endpoint, map UI, heatmap and slider, and docs and deploy. Each phase had to pass its tests before I sent the next one. I set the quality bar up front: pure functions for rules and ranking, a test for every boundary, mocked APIs, clear error states, no dead code, every assumption written in the README, and no new dependency without asking me first.

## Review and improvements
| Before | Directed fix | After |
|---|---|---|
| Denver → Salt Lake City recommended a 13.3 h via-point detour (Route C) over the 9.0 h Route A, on average risk 0.00 vs 0.10 | Drop via-point routes over 1.25× the fastest route's time; add a test | Detour removed |
| Green "Recommended" banner even when the best route had Severe or No Travel miles | Orange or red warning | Done |
| Checkpoints classified on rounded values, heatmap on raw | Classify raw, round only for display | Done |
| `interval_mi: null` returned 500 | Return 400 with a message | Done |
| About 250 Open-Meteo locations per plan; rate-limit risk on a shared host IP | Heatmap grid cut from about 220 to 109 points, deduped weather coordinates, 45-minute cache, one worker on Render's free plan | Done |
| ETAs shown without a time zone | Time zone labels | Done |
| No hosted app; template text in docs | Render deploy, docs cleanup, README notes on rest breaks and the car profile | Done |
| On the hosted app, requests from Render's shared IP failed | Free, key-less fallbacks: address search runs from the browser against Photon, with a server fallback to Open-Meteo Geocoding; weather falls back from Open-Meteo to MET Norway Locationforecast | Done |

The first row is the one I care about most. The tests passed and the code did what it was told, but the recommendation was wrong for a driver. That kind of problem only shows up when you run a real trip and ask whether the answer makes sense.

For the ranking itself, I chose to follow the spec literally: No Travel miles, then Severe, then High, then average risk (rounded to 3 decimals), then travel time. An earlier version had a tie tolerance on average risk, and I removed it. Denver → Salt Lake City at 42,000 lb now recommends Route B (9.71 h, all low risk) over Route A (8.98 h, 50 moderate miles). B is 44 minutes slower, but the spec ranks weather risk ahead of time, and I'd rather the app do what the rules say than make its own trade-offs.

## Results
- Backend tests: 53 passed on the pre-fix commit `a6fb8c5`. After the fixes: 77 passed, with lint and the frontend build clean.
- From the review (pre-fix, live APIs, Denver → Salt Lake City): plan 3.6 s cold and 0.14 s cached; 4.4 s end to end in the browser; 48 slider steps in 0.68 s with zero network requests; 60 fps idle.
- Hosted app: https://truck-routing-7za4.onrender.com on Render's free tier. The first request after it sleeps takes about 50 seconds while the instance wakes up.
- Live Denver → Salt Lake City on the hosted app after the redeploy: Route B recommended; about 36 s for the first plan and about 24 s for a repeat on the free instance.

## What I verified myself
- The `test_risk.py` boundary cases against the PDF table, value by value, including the strict `>` cases.
- Units in a live Open-Meteo response: mph for wind, and inches for rain, showers and snowfall.
- A live Denver → Salt Lake City trip at 42,000 lb, which is where the slow-detour recommendation showed up.
- The Network tab while dragging the slider, to confirm there were no requests.

## Limitations and next steps
- **Car profile:** the 65 mph cap is a rough correction. Next, I'd move to OpenRouteService `driving-hgv` or HERE truck routing, which also give real alternatives.
- **Hours of service:** ETAs assume continuous driving. Next, I'd add 30-minute and 10-hour rest breaks to checkpoint ETAs.
- **Forecast window:** departures must be within 10 days, and there's no separate "no forecast" state yet.
- **Rate limits:** the app runs on free public APIs with fallbacks. Real use needs a shared cache (Redis) and a paid or self-hosted provider.
- **Frontend tests:** none yet. Next, I'd add Vitest, React Testing Library and a Playwright smoke test.
