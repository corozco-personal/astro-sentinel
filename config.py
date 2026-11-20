"""
Global configuration for the Astro Sentinel detection pipeline.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
CANDIDATES_DIR = OUTPUT_DIR / "candidates"
PLOTS_DIR = OUTPUT_DIR / "plots"

OUTPUT_DIR.mkdir(exist_ok=True)
CANDIDATES_DIR.mkdir(exist_ok=True)
PLOTS_DIR.mkdir(exist_ok=True)

@dataclass
class MicrolensingConfig:
    min_magnification: float = 1.40
    min_tE_days: float = 25.0
    max_tE_days: float = 300.0
    min_chi2_improvement: float = 200.0

@dataclass
class EllipsoidalConfig:
    min_period_days: float = 0.8
    max_period_days: float = 30.0
    min_power_snr: float = 18.0
    harmonic_ratio_min: float = 0.50
    min_amplitude_percent: float = 1.0

@dataclass
class NotificationConfig:
    recipient_phone: str = field(default_factory=lambda: os.environ.get("BHS_RECIPIENT_PHONE", ""))
    webhook_url: str = field(default_factory=lambda: os.environ.get("BHS_WEBHOOK_URL", ""))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    enable_imessage_sms: bool = True

@dataclass
class PipelineConfig:
    microlensing: MicrolensingConfig = field(default_factory=MicrolensingConfig)
    ellipsoidal: EllipsoidalConfig = field(default_factory=EllipsoidalConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    outlier_sigma: float = 4.0
    query_timeout: int = 45
    max_workers: int = 4
