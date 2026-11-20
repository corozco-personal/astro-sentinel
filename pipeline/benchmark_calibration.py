"""
Calibration and Benchmark Module with Confirmed Black Hole Catalog.
Evaluates and calibrates detection method sensitivity:
1. Ellipsoidal modulation and Morris (1985) gravitational model
2. Relativistic gravitational microlensing (Paczyński 1986)
3. Gravitational self-lensing pulses
"""
from typing import Dict, Any, List
from pipeline.official_catalogs import OFFICIAL_BLACK_HOLE_REGISTRY

# Benchmark ground-truth catalog with physical parameters and TIC mappings
CONFIRMED_BLACK_HOLES_BENCHMARK = [
    {
        "id": "CYG_X1",
        "name": "Cygnus X-1 (HDE 226868)",
        "tic_id": "TIC 102604645",
        "system_type": "HMXB Black Hole",
        "primary_mass_msun": 25.0,
        "bh_mass_msun": 21.2,
        "orbital_period_days": 5.60,
        "expected_signature": "Ellipsoidal Binary Modulation",
        "ra": 299.5903,
        "dec": 35.2016,
        "literature_reference": "Miller-Jones et al. 2021 (Science)"
    },
    {
        "id": "GAIA_BH1",
        "name": "Gaia BH1",
        "tic_id": "TIC 59397594",
        "system_type": "Dormant Astrometric Black Hole",
        "primary_mass_msun": 0.93,
        "bh_mass_msun": 9.62,
        "orbital_period_days": 185.6,
        "expected_signature": "Gaia Astrometric Wobble + Dormant Radial Velocity",
        "ra": 260.6725,
        "dec": -0.6022,
        "literature_reference": "El-Badry et al. 2023 (MNRAS)"
    },
    {
        "id": "GAIA_BH3",
        "name": "Gaia BH3",
        "tic_id": "TIC 95032068",
        "system_type": "Dormant Massive Black Hole",
        "primary_mass_msun": 0.76,
        "bh_mass_msun": 32.7,
        "orbital_period_days": 4250.0,
        "expected_signature": "Ultra-Massive Astrometric Binary",
        "ra": 294.1350,
        "dec": 14.9753,
        "literature_reference": "Gaia Collaboration 2024 (A&A)"
    },
    {
        "id": "V404_CYG",
        "name": "V404 Cygni (GS 2023+338)",
        "tic_id": "TIC 136874944",
        "system_type": "LMXB Microquasar",
        "primary_mass_msun": 0.7,
        "bh_mass_msun": 9.0,
        "orbital_period_days": 6.47,
        "expected_signature": "Ellipsoidal Modulation + Accretion Outbursts",
        "ra": 306.0159,
        "dec": 33.8673,
        "literature_reference": "Casares et al. 1992 (Nature)"
    },
    {
        "id": "MAXI_J1820",
        "name": "MAXI J1820+070 (ASASSN-18ey)",
        "tic_id": "TIC 317984780",
        "system_type": "LMXB Transient",
        "primary_mass_msun": 0.5,
        "bh_mass_msun": 8.5,
        "orbital_period_days": 0.68,
        "expected_signature": "Short-Period Ellipsoidal & Fast Optical Variations",
        "ra": 275.0913,
        "dec": 7.1853,
        "literature_reference": "Torres et al. 2019 (ApJL)"
    },
    {
        "id": "OGLE_2011_BLG_0462",
        "name": "OGLE-2011-BLG-0462 / MOA-2011-BLG-191",
        "tic_id": "OGLE-2011-BLG-0462",
        "system_type": "Isolated Microlensed Black Hole",
        "primary_mass_msun": 0.0,
        "bh_mass_msun": 7.1,
        "orbital_period_days": 0.0,
        "expected_signature": "Long-Duration Relativistic Microlensing (tE ~ 270d)",
        "ra": 268.0583,
        "dec": -29.8319,
        "literature_reference": "Sahu et al. 2022 (ApJ) / Lam et al. 2022 (ApJL)"
    },
    {
        "id": "VFTS_243",
        "name": "VFTS 243",
        "tic_id": "TIC 728273142",
        "system_type": "Dormant Black Hole in LMC",
        "primary_mass_msun": 25.0,
        "bh_mass_msun": 10.1,
        "orbital_period_days": 10.4,
        "expected_signature": "Tidal Modulation & Silent Direct Collapse",
        "ra": 84.5367,
        "dec": -69.1764,
        "literature_reference": "Shenar et al. 2022 (Nature Astronomy)"
    }
]

def get_benchmark_catalog() -> List[Dict[str, Any]]:
    """Return curated list of confirmed black holes with metadata for calibration."""
    return CONFIRMED_BLACK_HOLES_BENCHMARK


def calibrate_target(target_id: str, sector: int = 14) -> Dict[str, Any]:
    """
    Run detection method calibration on a confirmed black hole from the catalog.
    """
    from pipeline.pipeline import BlackHolePipeline
    import lightkurve as lk

    match = None
    for item in CONFIRMED_BLACK_HOLES_BENCHMARK:
        if item["id"] == target_id or item["tic_id"] == target_id or item["name"] == target_id:
            match = item
            break

    if not match:
        return {"success": False, "error": f"Target {target_id} not found in benchmark catalog."}

    tic = match["tic_id"]
    star_m = match.get("primary_mass_msun", 1.0)
    bh_m = match.get("bh_mass_msun", 10.0)
    expected_p = match.get("orbital_period_days", 0.0)

    results = {
        "benchmark_target": match["name"],
        "tic_id": tic,
        "system_type": match["system_type"],
        "known_bh_mass": bh_m,
        "known_period_days": expected_p,
        "tests": {}
    }

    try:
        search = lk.search_lightcurve(tic, sector=sector)
        if len(search) == 0:
            search = lk.search_lightcurve(tic)

        if len(search) > 0:
            lc = search[0].download().remove_nans().normalize()
            from pipeline.detectors.ellipsoidal import EllipsoidalDetector
            det = EllipsoidalDetector(min_snr=4.0)
            ellip_res = det.evaluate(lc, star_mass=star_m, star_rad=max(1.0, star_m * 0.8))
            results["tests"]["ellipsoidal"] = {
                "detected_period_days": ellip_res.get("detected_period_days"),
                "orbital_period_days": ellip_res.get("orbital_period_days"),
                "snr": ellip_res.get("snr"),
                "amplitude_percent": ellip_res.get("amplitude_percent"),
                "period_error_percent": abs(ellip_res.get("orbital_period_days", 0) - expected_p) / (expected_p + 1e-9) * 100 if expected_p > 0 else 0
            }
            results["success"] = True
        else:
            results["tests"]["ellipsoidal"] = {"status": "No TESS Sector data available"}
            results["success"] = True
    except Exception as e:
        results["tests"]["ellipsoidal"] = {"error": str(e)}
        results["success"] = False

    return results
