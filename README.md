# Astro Sentinel

Autonomous astronomical detection pipeline that analyzes TESS (Transiting Exoplanet Survey Satellite) photometry to identify **stellar-mass black holes**, **exoplanets**, and **optical transients** (supernovae, stellar flares, GRB afterglows). It cross-validates candidates against Gaia DR3, SIMBAD, MAST, and the NASA Exoplanet Archive, then ranks them through physics-based vetting, Bayesian MCMC mass estimation, and false-positive rejection.

## Detection Modalities

### 1. Black Hole Candidates

Six complementary detectors target isolated and binary stellar-mass black holes:

| Detector | Signature | Key References |
|---|---|---|
| **Gravitational Microlensing** | Paczyński curve fit, long Einstein time (tE > 50 d), achromatic | Paczyński 1986, Sahu et al. 2022 |
| **Ellipsoidal Modulation** | Tidal distortion at 2f_orb, Morris mass function > 3 M☉ (TOV limit) | Morris 1985, Gomel et al. 2021 |
| **Self-Lensing** | Periodic magnification pulses when compact object transits companion | Agol 2002, Kruse & Agol 2014 |
| **Doppler Beaming** | Relativistic flux modulation at 1f_orb, 90° phase offset from ellipsoidal | Mazeh & Faigler 2010, Loeb & Gaudi 2003 |
| **Accretion Flickering** | Linear RMS–flux relation in turbulent accretion disks | Uttley et al. 2005 |
| **BLS Eclipse** | Box-shaped periodic eclipses from accretion disks | Kovács et al. 2002 |

Strong candidates proceed through eccentric-harmonics filtering, Roche geometry analysis, centroid PRF veto (to reject background blends), and MCMC posterior sampling (emcee) for companion mass.

### 2. Exoplanet Candidates

A full transit detection and vetting pipeline:

1. **Transit Least Squares (TLS)** with Mandel & Agol (2002) limb-darkening profiles.
2. **Odd-Even Depth Veto** — rejects 2× period eclipsing binaries.
3. **Secondary Eclipse Veto** — rejects self-luminous companions.
4. **Centroid PRF Veto** — rejects blended background eclipsing binaries.
5. **Transit Duration Ratio (TDR) Veto** — checks physical ingress/egress limits.
6. **Transit Timing Variations (TTV)** analysis for multi-planet perturbations.
7. Planetary parameter derivation: Rp, semi-major axis, Teq, density, Habitable Zone classification.
8. **False Alarm Probability (FAP)** and FDR statistical correction.
9. Cross-match against SIMBAD and NASA Exoplanet Archive to confirm novelty.

### 3. Optical Transients & Supernovae

Non-periodic high-energy events detected by the transient engine:

- **Early supernova shock breakouts** — rapid exponential flux rise in 2–12 hours.
- **Stellar superflares** (M/K dwarfs) — impulsive rise + exponential reconnection decay.
- **GRB optical afterglows** — power-law fading t^−α.
- **Cataclysmic variables / dwarf nova outbursts** — 3–6 magnitude brightening.

## Architecture

```
astro-sentinel/
├── config.py                          # Astrophysical thresholds and env-based credentials
├── main.py                            # CLI for single-target analysis
├── run_scanner.py                     # Continuous autonomous scan daemon
├── app/
│   ├── server.py                      # Flask API (port 5055) + real-time dashboard
│   └── templates/index.html           # Observatory dashboard (Aladin Lite, Plotly)
├── pipeline/
│   ├── pipeline.py                    # Black hole detection orchestrator
│   ├── tess_client.py                 # TESS/MAST download, cleanup, normalization
│   ├── continuous_scanner.py          # SQLite WAL queue, sector-by-sector scanning
│   ├── cross_match.py                 # SIMBAD, Gaia DR3, MAST, NASA Exoplanet Archive
│   ├── auto_verifier.py              # Automated multi-signal verification (SDD judge)
│   ├── bayesian_mcmc.py              # emcee MCMC posterior for companion mass
│   ├── notifier.py                    # BH alert system (Telegram, JSONL, macOS)
│   ├── notifier_exoplanet.py         # Exoplanet alert system
│   ├── report_generator.py           # Diagnostic plots and JSON reports
│   ├── sync_evaluator.py             # Parallel evaluation across all three modalities
│   ├── gaia_spectral.py              # Gaia DR3 spectral cross-reference
│   ├── roche_analyzer.py             # Roche lobe geometry analysis
│   ├── orbit_analyzer.py             # Orbital parameter estimation
│   ├── finder_chart.py               # High-resolution finder chart generation
│   ├── kinematic_kick.py             # Natal kick and runaway velocity analysis
│   ├── statistical_corrector.py      # Lightcurve quality and FAP correction
│   ├── multi_sector_stitcher.py      # Multi-sector lightcurve stitching
│   ├── telegram_control_bot.py       # Telegram bot for remote control
│   └── detectors/
│       ├── microlensing.py            # Paczyński model fitting
│       ├── ellipsoidal.py             # Lomb-Scargle + Morris tidal model
│       ├── self_lensing.py            # Gravitational self-lensing pulses
│       ├── doppler_beaming.py         # Relativistic Doppler modulation
│       ├── accretion_flickering.py    # RMS–flux accretion signature
│       ├── bls_detector.py            # Box Least Squares eclipse search
│       ├── centroid_veto.py           # Pixel-level PRF centroid shift
│       ├── eccentric_harmonics.py     # Orbital eccentricity harmonics filter
│       ├── exoplanet_detectors.py     # TLS engine and physics calculations
│       ├── exoplanet_full_pipeline.py # End-to-end exoplanet vetting pipeline
│       └── transients_detector.py     # Supernova / transient classifier
├── sdd/                               # Software Design Document verification
│   └── specs/                         # Contracts, judges, observatory rules
├── tests/                             # SDD spec tests and E2E server tests
├── docker-compose.yml                 # Docker deployment
└── outputs/                           # Scan DB, alerts, candidate reports, plots
```

## Dashboard

The web dashboard (Flask, port 5055) provides:

- **Three observatory tabs** — Black Holes, Exoplanets, Transients — each showing candidates filtered by category.
- **Aladin Lite** interactive sky map with candidate markers.
- **Plotly** transit / lightcurve charts rendered per candidate.
- **Live processed feed** with real-time scan progress per category.
- **Remote control** — start, stop, pause scans; prioritize specific TIC targets.

## Quick Start

### Requirements

- Python 3.10+
- Dependencies: `lightkurve`, `astropy`, `scipy`, `numpy`, `emcee`, `flask`, `flask-cors`, `transitleastsquares`

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install lightkurve astropy scipy numpy emcee flask flask-cors transitleastsquares corner requests
```

### Configuration

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

The `.env` file holds Telegram bot tokens and optional webhook URLs. All credentials are loaded from environment variables — nothing is hardcoded.

### Run

**Continuous autonomous scan:**
```bash
python run_scanner.py --delay 0.5
```

**Single-target analysis:**
```bash
python main.py
```

**Web dashboard:**
```bash
python -m app.server
```

Then open `http://localhost:5055`.

### Docker

```bash
docker-compose up -d
```

## Tests

```bash
python -m pytest test_pipeline.py tests/ -v
```

The test suite includes:
- **SDD contract verification** — validates that pipeline outputs conform to candidate data contracts.
- **Synthetic signal injection** — microlensing (Paczyński), ellipsoidal modulation, and transit signals injected into synthetic lightcurves to verify detector sensitivity and calibration.
- **E2E server tests** — validates API endpoints and dashboard data flow.

## How It Works

1. The continuous scanner queries MAST for TESS timeseries targets sector by sector.
2. For each target, the lightcurve is downloaded via `lightkurve`, cleaned, and normalized.
3. All three detection engines run in parallel via `SyncEvaluator`:
   - The **BH pipeline** chains six detectors → centroid veto → eccentric harmonics → Roche geometry → cross-match → auto-verification → MCMC mass estimation.
   - The **exoplanet pipeline** runs TLS → five vetting stages → parameter derivation → cross-match.
   - The **transient engine** classifies non-periodic high-energy events by temporal morphology.
4. Candidates passing all filters are logged to JSONL, plotted, and optionally pushed via Telegram alerts.
5. Progress is tracked in SQLite (WAL mode) so scans resume exactly where they left off.

## License

MIT
