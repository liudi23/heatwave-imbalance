# Heatwave stress on the GB balancing system — Phase 1 scope

*Working title: "How extreme heat stresses the GB balancing system, and what it means for a decarbonising grid."*

**Status:** Phase 1 — driver analysis (self-contained). **Owner:** Di Liu. **Last updated:** 2026-06-26.

---

## 1. One-line framing

Extreme heat is becoming more frequent in GB and NW Europe. This project characterises **how heatwaves stress the GB electricity balancing system** — how that stress shows up in net imbalance volume and the imbalance (cash-out) price, and what it implies for system resilience as the grid decarbonises. The recurring **~18:00 price spikes** observed during the current heatwave are the concrete entry point.

This is framed as **energy-systems understanding and climate resilience**, not price prediction or trading alpha. The deliverable is an interpretable, reproducible analysis of *drivers*, published openly with a readable writeup.

## 2. Why this is the right question for this audience

The driver/feature investigation isn't a prelude to the "real" model — for a research lab it *is* the work. The aim is to **explain why spikes happen physically**, decompose the contributing mechanisms, and quantify them, rather than fit a black-box predictor. That matches a remit centred on resilience to extreme weather, open data/open source, and published research.

## 3. Terminology note (and a deliberate correction of my own pipeline's framing)

My existing pipeline calls the target **SSP** (System Sell Price) — legacy language from the **dual cash-out** regime. GB moved to a **single imbalance price** under P305 (effective Nov 2018): there is now one **imbalance price** per settlement period, applied to both short and long imbalance positions. So Phase 1 standardises on:

- **Imbalance price** — single cash-out price, £/MWh, per settlement period (SP).
- **NIV** — Net Imbalance Volume (MWh): the aggregate system length/shortness the balancing actions resolved. Sign and magnitude of NIV is the volume story behind the price.
- **Settlement period (SP)** — 48 half-hours per day. SP1 = 00:00–00:30; the **18:00 spike sits around SP36–37** (17:30–18:30).

Using the current terminology correctly is itself a small signal of energy-systems literacy and "researching unfamiliar topics."

## 4. The 18:00 spike — physical story (the core thesis)

The evening spike is, at baseline, the **duck-curve neck**: demand ramps up as people get home while **solar generation collapses at sunset**, so *net demand* (demand − wind − solar) ramps hard into the evening peak. A heatwave layers several compounding mechanisms on top. Phase 1 treats each as a **testable hypothesis**:

- **H1 — Net-demand ramp.** The steep SP30→SP37 ramp in net demand is the primary driver of evening tightness; heatwaves raise the *level* (cooling/behavioural demand) and may steepen the ramp.
- **H2 — Solar drop-off timing.** Loss of solar into the evening peak removes supply exactly when demand peaks; the effect is larger on clear-sky heatwave days with high midday solar to lose.
- **H3 — Low wind (anticyclonic heat).** Heat domes are typically high-pressure/low-wind, so wind is unusually low precisely during the stressed evenings, thinning margin.
- **H4 — Thermal derating.** High ambient (and river/sea) temperatures reduce thermal/CCGT efficiency and can trigger cooling-water constraints, shaving available capacity at peak.
- **H5 — Interconnector tightness.** Heat is regional; when neighbours (FR/BE/NL) are simultaneously stressed, import availability tightens, reducing a key margin buffer.

**Composite hypothesis:** the heatwave 18:00 spikes are **tight de-rated margin at the evening peak**, produced by the *coincidence* of high net demand + solar drop-off + low wind + thermal derating + constrained imports — not any single factor. Phase 1's job is to **disentangle and rank** these.

## 5. Data sources

All GB system data via **Elexon BMRS / Insights** (key available). Candidate datasets:

- **Imbalance price** (system/cash-out price) and **NIV** — the targets.
- **Demand** — initial/transmission demand outturn (INDO / ITSDO) and forecast.
- **Generation by fuel type** (half-hourly outturn) — to build wind, solar, CCGT, nuclear, etc.
- **Wind & solar** — forecast vs outturn (to separate *forecast error* from *level*).
- **Interconnector flows** — net import/export by link.
- **Margin signals** — de-rated margin / LOLP / loss-of-load indicators where available; MEL vs demand as a derived margin proxy.
- **Balancing actions** — bid-offer acceptance volumes/prices (BOALF / system actions) to see *how* the system was balanced on spike evenings.

**Weather:** ambient temperature (and ideally clear-sky/cloud and wind speed) from an open source — e.g. Open-Meteo / ERA5 reanalysis — aggregated to a **population-weighted GB temperature** and a **demand-region** series. Optionally river/sea temperature proxies for H4.

**Period:** several recent summers for a heatwave-vs-normal contrast, plus the **current (June 2026) heatwave** as the topical focal event.

## 6. Features for the decomposition

Engineered, interpretable features (no opaque embeddings):

- **Net demand** = demand − wind − solar; and its **ramp** (Δ over SP windows into the peak).
- **Solar drop-off** — solar outturn gradient across SP30–SP40.
- **Wind level & wind anomaly** vs seasonal-diurnal norm.
- **Margin proxy** — available capacity − demand; and **interconnector net import**.
- **Temperature features** — level, anomaly vs climatology, lagged temperature (heat builds over multi-day domes), and a cooling-degree proxy.
- **Wind/solar forecast error** — to test whether spikes are *level* events or *surprise* events.
- **Regime flags** — heatwave day (threshold on temp anomaly / consecutive hot days), weekday/weekend, SP-of-day.

## 7. Analytical approach (interpretability-first)

1. **Descriptive / event study.** Diurnal profiles of price, NIV and net demand on heatwave days vs **matched non-heatwave days** (same SP, similar weekday/season). Superposed-epoch view around heatwave onset.
2. **Driver decomposition.** Attribute evening tightness across the H1–H5 mechanisms — correlation/conditioning, then a **transparent model** (interpretable regression / GAM, with SHAP only as a cross-check) predicting price/NIV from the physical features. Emphasis on *explained drivers and their ranking*, not predictive score.
3. **Counterfactual sketch.** Rough "what would the 18:00 price have been at typical wind/solar/margin?" to size each mechanism's contribution.
4. **Resilience read-across.** Brief, qualitative: as solar/wind share grows and thermal retires, which of H1–H5 intensify? This is the decarbonisation-relevance payoff.

## 8. Scope boundaries (what Phase 1 is *not*)

- **In:** characterising and ranking the physical drivers of heatwave evening spikes; one clean topical case study (current heatwave); reproducible pipeline + writeup.
- **Out (later phases):** a tuned forecasting model; full nowcasting of physical parameters; cross-border modelling of neighbours; trading/P&L framing of any kind.

## 9. Deliverables & success criteria

- **Public repo** — reproducible pulls (BMRS + open weather), tidy notebooks/scripts, environment pinned.
- **Short writeup / blog** — the physical story, the decomposition, ranked drivers, and the resilience read-across, with a handful of clean figures (diurnal profiles, heatwave-vs-normal, driver attribution).
- **Success = a reader understands *why* the 18:00 spikes happen in a heatwave and which mechanisms dominate** — defensible, reproducible, and clearly communicated. (A good predictive score is explicitly *not* the success metric.)

## 10. Thursday talking points (Octopus / CfNZ)

- Connects directly to the team's mention of **estimating physical parameters for short-term forecasting** — this characterises the physical drivers those parameters must capture.
- Demonstrates **proactive curiosity** (topical heatwave, self-initiated), **research on unfamiliar topics**, and **clear communication** — all named traits.
- **Re-narrate both projects around energy-systems understanding, not markets:** the existing pipeline shows *deploying/monitoring models in production* (a listed nice-to-have); this project shows *research, analysis, and communication*. Together they cover the engineering and research sides of the role.
- Honest caveat to pre-empt: the pipeline was originally built for a markets role, so its current framing leans trading — this project is the deliberate re-framing toward climate-stress analysis.

## 11. Immediate next steps

1. Confirm the BMRS dataset IDs/endpoints for each item in §5 and write the data-pull module.
2. Pull the current heatwave window + 2–3 prior summers; build the feature table in §6.
3. First exploratory figure: **diurnal price/NIV/net-demand profile, heatwave days vs matched normal days** — the visual that anchors the whole writeup.
