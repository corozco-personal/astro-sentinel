"""
ASTRO SENTINEL - SDD (Specification-Driven Development) Data Contracts
Defines strictly-typed schemas for Candidates, Alerts, Veto Audits, and Engine Outputs.
"""
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


class Coordinates(BaseModel):
    ra: float = Field(..., ge=0.0, le=360.0, description="Right Ascension in degrees J2000")
    dec: float = Field(..., ge=-90.0, le=90.0, description="Declination in degrees J2000")


class ExoplanetTLSResults(BaseModel):
    tls_detected: bool = Field(..., description="Whether a transit signal was detected by TLS")
    sde: float = Field(..., ge=0.0, description="Signal Detection Efficiency")
    period_days: float = Field(..., gt=0.0, description="Orbital period in days")
    t0_bjd: float = Field(..., description="Reference epoch of mid-transit in BJD")
    transit_depth_ppm: float = Field(..., ge=0.0, description="Transit depth in parts per million")
    duration_hours: float = Field(..., gt=0.0, description="Transit duration in hours")


class ExoplanetPlanetaryParams(BaseModel):
    planet_radius_earth: float = Field(..., gt=0.0, description="Derived planetary radius in Earth radii")
    semi_major_axis_au: float = Field(..., gt=0.0, description="Orbital semi-major axis in Astronomical Units")
    equilibrium_temp_k: float = Field(..., gt=0.0, description="Planetary equilibrium temperature in Kelvin")
    classification: str = Field(..., description="Astrophysical planet classification")
    in_habitable_zone: bool = Field(..., description="Habitable Zone occupancy flag")


class ExoplanetVetoAudit(BaseModel):
    odd_even_eb_veto: bool = Field(..., description="True if passed EB veto (delta < 3 sigma)")
    secondary_eclipse_veto: bool = Field(..., description="True if passed secondary occultation veto (SNR < 3.5 sigma)")
    catalog_crossmatch_veto: bool = Field(..., description="True if no prior false positive or confirmed record in NASA/TOI")
    centroid_prf_veto: bool = Field(..., description="True if centroid shift during event is consistent with target star")


class ExoplanetCandidateContract(BaseModel):
    target_id: str = Field(..., pattern=r"^TIC\s+\d+$", description="TESS Input Catalog Identifier")
    ra: float = Field(..., ge=0.0, le=360.0)
    dec: float = Field(..., ge=-90.0, le=90.0)
    tls_results: ExoplanetTLSResults
    planetary_params: ExoplanetPlanetaryParams
    veto_audit: ExoplanetVetoAudit
    score: float = Field(..., ge=0.0, le=100.0)
    is_candidate: Literal[True] = True
    verdict: str = Field(..., description="Physical summary of the high-confidence candidate")

    @model_validator(mode="after")
    def verify_all_vetoes_passed(self):
        # RULE: A candidate cannot have is_candidate=True if any veto test failed or SDE < 7.0
        if not (self.veto_audit.odd_even_eb_veto and 
                self.veto_audit.secondary_eclipse_veto and 
                self.veto_audit.catalog_crossmatch_veto and 
                self.veto_audit.centroid_prf_veto):
            raise ValueError("SDD VIOLATION: Cannot produce CandidateContract when any veto audit failed.")
        if self.tls_results.sde < 7.0:
            raise ValueError(f"SDD VIOLATION: Candidate SDE {self.tls_results.sde} is below threshold 7.0 sigma.")
        return self


class BlackHoleCandidateContract(BaseModel):
    target_id: str = Field(..., pattern=r"^TIC\s+\d+$")
    ra: float = Field(..., ge=0.0, le=360.0)
    dec: float = Field(..., ge=-90.0, le=90.0)
    detection_type: Literal[
        "Microlensing (Paczynski)",
        "Ellipsoidal (Morris Tidal)",
        "Self-Lensing (Maeder/Agol)",
        "Doppler Beaming (Relativistic)",
        "Aperiodic Flickering"
    ]
    confidence: Literal["Moderate", "High", "Critical"]
    verdict: str
    is_candidate: Literal[True] = True
    criteria_list: List[str] = Field(..., min_length=1)
    auto_verification_score: float = Field(..., ge=50.0, le=100.0)


class TransientCandidateContract(BaseModel):
    target_id: str = Field(..., pattern=r"^TIC\s+\d+$")
    ra: float = Field(..., ge=0.0, le=360.0)
    dec: float = Field(..., ge=-90.0, le=90.0)
    event_type: Literal["Shock Breakout", "Superflare", "Cataclysmic Variable Outburst"]
    peak_sigma: float = Field(..., ge=5.0)
    peak_flux_amplitude: float = Field(..., gt=0.0)
    confidence_score: float = Field(..., ge=50.0, le=100.0)
    is_transient: Literal[True] = True
