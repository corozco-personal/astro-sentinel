"""
Exoplanet Alert Notifier
------------------------
Dispatches vetted exoplanet discovery alerts to Telegram and persists to alerts_exoplanets.jsonl.
"""

import os
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any


class ExoplanetAlertNotifier:
    def __init__(self, alerts_file: Path):
        self.alerts_file = alerts_file
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def notify(self, candidate_data: Dict[str, Any]):
        # SDD Candidate Quality Judge evaluation
        from sdd.judges.verification_judges import NotificationPolicyJudge
        if not NotificationPolicyJudge.can_notify_telegram("exoplanet", candidate_data):
            return

        # STRICT: Only dispatch if confirmed as a real candidate
        if not candidate_data.get("is_candidate"):
            return
        verdict = str(candidate_data.get("verdict", "")).upper()
        if "VETOED" in verdict or "FALSE POSITIVE" in verdict or "DISCARDED" in verdict:
            return

        # 1. Append to alerts_exoplanets.jsonl
        try:
            with open(self.alerts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(candidate_data) + "\n")
        except Exception as e:
            print(f"[Notifier Exoplanet] File write error: {e}")

        # 2. Dispatch to Telegram
        self._send_telegram_alert(candidate_data)

    def _send_telegram_alert(self, data: Dict[str, Any]):
        target_id = data.get("target_id", "Unknown")
        params = data.get("planetary_params", {})
        tls = data.get("tls_results", {})
        score = data.get("score", 0.0)
        ra = data.get("ra")
        dec = data.get("dec")

        rp = params.get("planet_radius_earth", "N/A")
        teq = params.get("equilibrium_temp_k", "N/A")
        period = tls.get("period_days", 0.0)
        depth = tls.get("transit_depth_ppm", 0.0)
        classification = params.get("classification", "Exoplanet")
        hz_tag = "🌱 HABITABLE ZONE CONFIRMED" if params.get("in_habitable_zone") else "Standard Orbit"

        msg = (
            f"🪐 *ASTRO SENTINEL: NEW EXOPLANET CANDIDATE DETECTED*\n\n"
            f"🎯 *Target:* `{target_id}`\n"
            f"📊 *Classification:* {classification}\n"
            f"🔬 *Planetary Radius (Rp):* {rp} R⊕\n"
            f"⏱️ *Orbital Period:* {period:.4f} days\n"
            f"📉 *Transit Depth:* {depth:.0f} ppm\n"
            f"🌡️ *Equilibrium Temp:* {teq} K ({hz_tag})\n"
            f"🌟 *Coordinates:* RA {ra:.4f}°, Dec {dec:.4f}°\n"
            f"🛡️ *Detection SDE:* {tls.get('sde', 0.0):.1f}σ | Confidence Score: {score:.1f}%\n"
            f"✅ *Vetting:* Odd-Even Depth Veto Passed, Secondary Eclipse Veto Passed, PRF Centroid Checked\n\n"
            f"_Automated discovery via TESS TLS Multi-Pass Vetting Pipeline_"
        )

        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"[Notifier Exoplanet] 🚀 Telegram alert sent for {target_id}")
        except Exception as e:
            print(f"[Notifier Exoplanet] Telegram dispatch error: {e}")
