# When the grid gets hot: how heatwaves stress the GB balancing system

*A climate-resilience look at the evening imbalance-price spike — what drives it, and what it means for a decarbonising grid.*

*Draft · analysis covers GB summers 2021–2026 · code and data: [github.com/liudi23/heatwave-imbalance](https://github.com/liudi23/heatwave-imbalance)*

---

As I write this, the UK and much of western Europe are under a heatwave, and GB electricity prices have been spiking sharply around 6pm each evening. That coincidence is a good excuse to ask a question that matters more every year: **when an extreme-heat event lands on the GB power system, how does it show up in the balancing mechanism — and what does that tell us about a grid that is decarbonising?**

This is deliberately *not* a "can we predict the spike and trade it" question. It's a resilience question. The interesting output is an *explanation* — which physical mechanisms turn a hot, still evening into a stressed one — because those are the mechanisms a low-carbon grid will lean on more, not less.

## The thing we're looking at

Every half-hour, GB settles the gap between what generators and suppliers contracted to do and what actually happened. The cost of closing that gap is the **single imbalance price** (the "cash-out" price, one price per settlement period since the 2018 reform), and the net volume the system had to resolve is the **Net Imbalance Volume (NIV)**. When the system is tight, the imbalance price is what marginal balancing actions cost — so it's a clean, market-based stress gauge.

The recurring **~18:00 spike** has a textbook physical story before you even add heat. As people come home, demand ramps up; at the same time solar generation collapses toward sunset. *Net demand* — demand minus wind minus solar — therefore ramps hard into the early evening. That's the "neck" of the duck curve, and it's when the system is tightest.

Layer a heatwave on top and several mechanisms can compound, which I set up as five testable hypotheses:

- **H1 — net-demand ramp:** heat lifts the level of demand (cooling, behaviour) and can steepen the evening ramp.
- **H2 — solar drop-off:** clear-sky heat days produce a lot of midday solar that then vanishes into the peak.
- **H3 — low wind:** heat domes are anticyclonic — high pressure, low wind — so wind is unusually weak exactly when the evening is tight.
- **H4 — thermal derating:** high ambient (and cooling-water) temperatures shave thermal-plant efficiency and available capacity.
- **H5 — interconnector tightness:** heat is regional, so when neighbours are stressed too, import availability thins.

The composite bet is that a hot evening spike is not one thing — it's the *coincidence* of high net demand, lost solar, low wind, derated thermal and tighter imports. The job is to disentangle and rank them.

## Finding 1 — hot evenings cost more, but not because of volume

Across five summers (2021–2026), I compared the average diurnal profile on the hottest 20% of summer days against mild summer days.

![Diurnal profile: hot vs mild summer days](../figures/heatwave_diurnal_profile.png)

Two things stand out. First, the evening-peak imbalance price on hot days sits about **£77/MWh above mild days** — a large, consistent premium concentrated in the 17:00–19:00 window. Second — and this is the interesting part — the **system imbalance volume barely moves**: average |NIV| in that window is essentially the same on hot and mild evenings.

So at the national level the heat-related evening premium looks like a **scarcity-pricing effect, not a volume effect**: the system isn't necessarily *more* out of balance on hot evenings, but the marginal actions used to balance it are more expensive, because margin is thin and the cheap flexible options are already used up. The same panels show the mechanism ingredients directly — hot days have visibly *lower* wind share and *higher* midday solar that falls away into the peak.

## Finding 2 — temperature and low wind dominate the drivers

To go from "hot days look different" to "*which* driver matters", I regressed each summer day's evening-peak price on standardised physical drivers. Because the drivers are standardised, each coefficient reads as the £/MWh change in the evening price per one-standard-deviation move in that driver, holding the others fixed — a directly rankable, interpretable attribution rather than a black box.

![Driver attribution of the evening spike](../figures/spike_decomposition.png)

| Driver | Hypothesis | £/MWh per +1 SD | Univariate (Spearman) |
|---|---|--:|--:|
| Daily max temperature | H1/H4 demand & derate | **+36** | +0.21 |
| Evening wind share | H3 low wind | **−31** | −0.36 |
| Midday solar | H2 solar drop-off | −20 | +0.01 |
| Evening \|NIV\| | volume | +17 | +0.05 |

The two robust, high-significance signals are **temperature (positive)** and **wind share (negative)**: the evening premium is largest on hot, low-wind evenings. That is precisely the anticyclonic-heat signature — the same high-pressure system that brings the heat also stills the wind, and the two stresses arrive together at the worst time of day. Wind share has the strongest simple relationship of any driver (−0.36).

## Being honest about what this does and doesn't show

Good research is upfront about its limits, so three caveats travel with these numbers.

The model explains only about **21% of the day-to-day variation** in the evening price. That's expected and not a failure: spikes are tail events driven by margin and the specific balancing actions taken, which these daily proxies don't fully capture. The goal here is to *rank drivers*, not to maximise fit.

The **"hot day" label is a national average**. Population-weighted across the country, even a 32 °C afternoon in London averages down, so the hottest summer quintile tops out near ~21 °C. This first cut therefore uses a percentile label rather than the strict Met Office heatwave definition (three-plus consecutive days over a regional absolute threshold) — the regional version is a natural refinement.

And the **midday-solar term flips sign** between its simple correlation (~0) and its partial coefficient (−). That's a genuine limitation of the proxy: irradiance measures how *sunny* it was, not how much generation was *lost into the peak*. Separating solar level from solar drop-off needs absolute solar generation, not sunshine.

All three point to the same next step: replacing the weather proxies with **absolute half-hourly quantities** — demand, wind and solar in MW, plus interconnector flows — so net demand and its evening ramp (H1), the true solar drop-off (H2) and imports (H5) enter the decomposition directly. The pipeline is built to do exactly this: it auto-upgrades from "proxy" to "full" mode the moment those datasets are present, swapping the irradiance proxy for the absolute solar drop-off and adding the net-demand ramp and interconnector terms.

## Why this matters for a decarbonising grid

The mechanisms that make a hot evening expensive today are the mechanisms that a low-carbon grid will depend on more heavily. As solar share grows, the evening drop-off (H2) gets steeper. As wind share grows, the anticyclonic low-wind coincidence (H3) removes a larger slice of supply just when it's needed. As dispatchable thermal retires, the buffer that currently absorbs these stresses (H4) shrinks, and cross-border imports (H5) — themselves weather-correlated across a warming continent — carry more of the load.

In other words, the heatwave evening is a small, present-day preview of a structural challenge: **the correlation between extreme heat, low wind, and a solar-heavy supply stack concentrates system stress into a narrow evening window.** Understanding and quantifying that coincidence — rather than just forecasting the price — is what helps plan the flexibility, storage and interconnection that keep a decarbonising grid resilient to the extreme-weather events that are becoming more common.

## Reproducing this

Everything here is open. GB market data comes from the **Elexon BMRS / Insights** API (imbalance price and NIV; and, for full mode, demand outturn and generation-by-fuel including interconnectors), embedded solar from **Sheffield Solar PV_Live**, and weather from the **Open-Meteo ERA5** archive — all free and keyless. The repository has the fetchers, the interpretable decomposition, a reproducible figure pipeline, and a small read-only results app; the analysis above regenerates from a single command.

*This is Phase 1 — characterising the drivers. It builds on a separate GB imbalance-price forecasting pipeline, and the two share data conventions so the physical-driver work can flow back into forecasting later. Feedback welcome.*
