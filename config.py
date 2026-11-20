"""
Configuración global del pipeline de detección de agujeros negros en TESS.
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
    # Umbral de magnificación mínima para considerar evento (A_max > 1.4)
    min_magnification: float = 1.40
    # Duración mínima de cruce de Einstein (días) - Agujeros negros estelares M > 5 M_sun
    min_tE_days: float = 25.0
    # Duración máxima para ventana local
    max_tE_days: float = 300.0
    # Reducción drástica de chi-cuadrado para descartar fluctuaciones o tránsitos
    min_chi2_improvement: float = 200.0

@dataclass
class EllipsoidalConfig:
    # Período orbital mínimo y máximo (días)
    min_period_days: float = 0.8
    max_period_days: float = 30.0
    # SNR muy estricto para Lomb-Scargle para evitar capturar rotación estelar o manchas solares
    min_power_snr: float = 18.0
    # Ratio mínimo de potencia entre armónico 2f y 1f (doble abultamiento de marea marcado)
    harmonic_ratio_min: float = 0.50
    # Mínima amplitud de variación de marea (requiere compañero masivo M_comp > 3 M_sun)
    min_amplitude_percent: float = 1.0

@dataclass
class NotificationConfig:
    # Número de destino para alertas SMS / iMessage / WhatsApp (env: BHS_RECIPIENT_PHONE)
    recipient_phone: str = field(default_factory=lambda: os.environ.get("BHS_RECIPIENT_PHONE", ""))
    # Webhook opcional (Discord / Slack)
    webhook_url: str = field(default_factory=lambda: os.environ.get("BHS_WEBHOOK_URL", ""))
    # Telegram Bot Token y Chat ID (env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    # Activar notificación SMS nativa en macOS (iMessage / SMS Relay)
    enable_imessage_sms: bool = True

@dataclass
class PipelineConfig:
    microlensing: MicrolensingConfig = field(default_factory=MicrolensingConfig)
    ellipsoidal: EllipsoidalConfig = field(default_factory=EllipsoidalConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    # Nivel de significancia (sigma) para detección de anomalías
    outlier_sigma: float = 4.0
    # Timeout de consultas MAST / SIMBAD en segundos
    query_timeout: int = 45
    # Número de hilos de análisis concurrente en segundo plano
    max_workers: int = 4
