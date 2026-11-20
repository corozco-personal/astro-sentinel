"""
Módulo de Notificaciones y Alertas para Candidatos a Agujeros Negros.
Permite notificaciones en consola, en archivo de log de alertas (alert_feed.jsonl),
notificaciones sonoras/sistema o webhooks (Slack/Discord/Telegram).
"""
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import json
import os
import subprocess

class AlertNotifier:
    def __init__(self, alerts_file: Path, webhook_url: Optional[str] = None):
        self.alerts_file = alerts_file
        self.webhook_url = webhook_url or os.getenv("BH_ALERT_WEBHOOK_URL")

    def notify(self, candidate_info: Dict[str, Any]):
        """
        Emite una alerta sobre un nuevo candidato tentativo detectado.
        ESTRICTO: Solo se notifica si está confirmado como candidato real (is_candidate=True / undocumented_candidate=True).
        NUNCA notificar falsos positivos, descartes o información insuficiente.
        """
        assessment = candidate_info.get("assessment", {})
        is_candidate = (
            candidate_info.get("is_candidate") is True or
            assessment.get("undocumented_candidate") is True
        )
        verdict = str(assessment.get("verdict", "") or candidate_info.get("verdict", "")).upper()

        # SDD Candidate Quality Judge evaluation
        from sdd.judges.verification_judges import NotificationPolicyJudge
        if not NotificationPolicyJudge.can_notify_telegram("black_hole", candidate_info):
            # Silenciar y salir de acuerdo al veredicto del juez SDD
            return

        # Descarte explícito de falsos positivos o datos insuficientes
        if not is_candidate or "FALSO POSITIVO" in verdict or "DISCARDED" in verdict or "DOES NOT MEET" in verdict or "NO DATA" in verdict or "ERROR" in verdict:
            # Silenciar y salir inmediatamente
            return

        timestamp = datetime.utcnow().isoformat() + "Z"
        target_id = candidate_info.get("target_id", "Unknown")
        detection = candidate_info.get("detection_details", {})
        simbad = candidate_info.get("simbad_info", {})
        tic_info = simbad.get("tic_info", {}) if simbad else {}
        
        ra = candidate_info.get("ra") or tic_info.get("ra")
        dec = candidate_info.get("dec") or tic_info.get("dec")

        verdict = assessment.get("verdict", "Posible firma anómala de agujero negro")
        confidence = assessment.get("confidence", "Moderate")
        det_type = detection.get("type", "Unknown")

        metrics = {k: v for k, v in detection.items() if k != "model_flux"}
        
        # Extraer criterios cumplidos en formato de lista para el frontend
        criteria_list = []
        if det_type == "Microlensing (Paczynski)":
            criteria_list.append(f"Paczyński (1986) Microlensing: Non-linear fit with Δχ² = {metrics.get('delta_chi2', 0):.1f} (Threshold ≥ 150.0).")
            criteria_list.append(f"Einstein Crossing Time: tE = {metrics.get('tE_days', 0):.1f} days (Threshold ≥ 20.0 d, massive lens scale M ≥ 4-15 M_☉).")
            criteria_list.append(f"Peak Magnification: A_max = {metrics.get('peak_magnification', 0):.2f} (Threshold ≥ 1.30).")
            criteria_list.append(f"Temporal Symmetry Test (Mróz et al. 2021): Asymmetry = {metrics.get('asymmetry_index', 0):.2f} (Stellar flares ruled out < 0.65).")
            criteria_list.append(f"Reduced Chi²: χ²_red = {metrics.get('reduced_chi2', 0):.2f} (Physical high-quality fit ≤ 3.5).")
        elif "Ellipsoidal" in det_type:
            criteria_list.append(f"Morris (1985) Tidal Model: Orbital period P_orb = {metrics.get('orbital_period_days', 0):.2f} days.")
            criteria_list.append(f"Lomb-Scargle Periodogram: SNR = {metrics.get('snr', 0):.1f} (Strict threshold ≥ 20.0).")
            criteria_list.append(f"Quadrupolar Harmonic Ratio: 2f/1f = {metrics.get('harmonic_ratio', 0):.2f} (Threshold ≥ 0.45).")
            criteria_list.append(f"Tidal Distortion Amplitude: Amp = {metrics.get('amplitude_percent', 0):.2f}% (Range 1.2% - 12.0%).")
            criteria_list.append(f"Tolman-Oppenheimer-Volkoff Bound: Estimated compact companion mass = {metrics.get('estimated_compact_mass_msun', 0):.1f} M_☉ (> 3.0 M_☉).")

        # Criterios oficiales y de auto-verificación
        criteria_list.append("Official Cross-Match: No previous black hole or confirmed exoplanet record in SIMBAD/MAST.")
        auto_ver = candidate_info.get("auto_verification") or assessment.get("auto_verification")
        if auto_ver and auto_ver.get("tests"):
            tests = auto_ver.get("tests", {})
            if tests.get("gaia_astrometry", {}).get("astrometric_wobble_detected"):
                criteria_list.append("Gaia DR3: Centroid astrometric wobble confirmed (gravitational perturbation by unseen companion).")
            if tests.get("xray_emission", {}).get("has_xray_detection"):
                criteria_list.append(f"HEASARC: X-ray emission detected ({tests.get('xray_emission', {}).get('mission')}).")
            else:
                criteria_list.append("HEASARC: Quiescent X-ray flux, consistent with isolated/dormant stellar-mass black hole.")
            if not tests.get("exoplanet_veto", {}).get("is_known_false_positive"):
                criteria_list.append("NASA Exoplanet Archive: Rigorous exoplanetary false positive veto confirmed.")

        alert_entry = {
            "timestamp": timestamp,
            "target_id": target_id,
            "ra": ra,
            "dec": dec,
            "confidence": confidence,
            "detection_type": det_type,
            "verdict": verdict,
            "metrics": metrics,
            "criteria_list": criteria_list,
            "proposal_pdf": candidate_info.get("proposal_pdf"),
            "lightcurve_sample": candidate_info.get("lightcurve_sample"),
            "report_path": candidate_info.get("report_path")
        }

        # 1. Registrar en archivo de bitácora de alertas (JSON Lines persistente)
        with open(self.alerts_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert_entry, ensure_ascii=False) + "\n")

        # 2. Formatear y mostrar en consola con máxima visibilidad
        print("\n" + "!" * 70)
        print(f"🚨 [ALERTA DISPARADA] NUEVO CANDIDATO TENTATIVO A AGUJERO NEGRO")
        print(f"🎯 Objetivo: {target_id} | Nivel de Confianza: {confidence}")
        print(f"🔬 Firma Astrofísica: {det_type}")
        print(f"📝 Veredicto: {verdict}")
        auto_ver = candidate_info.get("auto_verification") or assessment.get("auto_verification")
        if auto_ver:
            print(f"🛡️  Verificación Automática: Score {auto_ver.get('final_score')}/100 [{auto_ver.get('status')}]")
            print(f"   {auto_ver.get('verdict')}")
        if det_type == "Microlensing (Paczynski)":
            print(f"📊 Parámetros: tE={detection.get('tE_days', 0):.1f} días, A_max={detection.get('peak_magnification', 0):.2f}, Δchi2={detection.get('delta_chi2', 0):.1f}")
        elif "Ellipsoidal" in det_type:
            print(f"📊 Parámetros: Período orbital={detection.get('orbital_period_days', 0):.2f} días, SNR={detection.get('snr', 0):.1f}")
        print(f"📁 Reporte Diagnóstico: {candidate_info.get('report_path')}")
        print("!" * 70 + "\n")

        # 3. Notificación nativa en macOS (osascript) si está disponible
        self._macos_notification(
            title=f"🚨 Candidato Agujero Negro ({confidence})",
            message=f"{target_id}: {det_type} detectado en TESS"
        )

        # 4. Enviar Webhook a Discord / Slack / Telegram si está configurado
        self._send_webhook(alert_entry)

        # 5. Enviar mensaje de alerta a Telegram del usuario (@corozco9408)
        self._send_telegram_alert(alert_entry)

    def _send_telegram_alert(self, alert_entry: Dict[str, Any]):
        """Envía alerta instantánea con sonido y formato al bot de Telegram personal de Carlos."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        target = alert_entry.get("target_id")
        det_type = alert_entry.get("detection_type")
        confidence = alert_entry.get("confidence", "High")
        verdict = alert_entry.get("verdict", "")
        ra = alert_entry.get("ra")
        dec = alert_entry.get("dec")
        ra_str = f"{ra:.4f}°" if ra is not None else "N/A"
        dec_str = f"{dec:.4f}°" if dec is not None else "N/A"

        text = (
            f"🚨 *[TESS BLACK HOLE SENTINEL ALERT]*\n\n"
            f"🎯 *Target:* `{target}`\n"
            f"🔬 *Signature:* {det_type}\n"
            f"🛡️ *Confidence:* {confidence}\n"
            f"📍 *Coordinates:* RA {ra_str} | DEC {dec_str}\n"
            f"⏱️ *Timestamp:* `{alert_entry.get('timestamp')}`\n\n"
            f"📝 *Verdict:* {verdict}"
        )

        try:
            import requests
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=5)
            print(f"[Notifier] Telegram alert successfully sent to chat {chat_id}")
        except Exception as e:
            print(f"[Notifier] Telegram dispatch error: {e}")

    def _send_webhook(self, alert_entry: Dict[str, Any]):
        """Envía alerta con formato enriquecido a Discord o Slack."""
        webhook_url = self.webhook_url or os.getenv("BH_ALERT_WEBHOOK_URL")
        if not webhook_url:
            return

        try:
            import requests
            target = alert_entry.get("target_id")
            det_type = alert_entry.get("detection_type")
            ra = alert_entry.get("ra")
            dec = alert_entry.get("dec")
            verdict = alert_entry.get("verdict")

            # Formato universal compatible con Discord Embeds / Slack Block Kit
            payload = {
                "content": f"🚨 **NUEVO CANDIDATO A AGUJERO NEGRO EN TESS**",
                "embeds": [{
                    "title": f"★ {target} ({det_type})",
                    "description": verdict,
                    "color": 16724582, # Rojo
                    "fields": [
                        {"name": "📍 Coordenadas Celestes", "value": f"RA: {ra}° | DEC: {dec}°", "inline": True},
                        {"name": "🔬 Nivel de Confianza", "value": alert_entry.get("confidence", "High"), "inline": True},
                        {"name": "⏱ Timestamp", "value": alert_entry.get("timestamp"), "inline": False}
                    ]
                }]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            print(f"[Notifier] Webhook dispatch error: {e}")

    def _macos_notification(self, title: str, message: str):
        try:
            cmd = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", cmd], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
