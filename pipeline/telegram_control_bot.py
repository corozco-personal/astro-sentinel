"""
Telegram Bidirectional Control Bot for ASTRO SENTINEL (24/7)
-----------------------------------------------------------
Listens for commands from the authorized user via Telegram Long-Polling:
- /start or /help : Displays available commands and sentinel status
- /status        : Returns real-time observatory metrics (patches, targets, candidates)
- /pause         : Pauses the continuous sky scanner
- /resume        : Resumes the continuous sky scanner
- /target <TIC>  : Queues an immediate priority analysis of a specific star
- /report        : Generates and sends the PDF scientific report of the latest candidate
"""

import os
import time
import json
import sqlite3
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any


class TelegramSentinelBot:
    def __init__(self, db_path: Path, alerts_bh_path: Path, alerts_exo_path: Path, toggle_callback=None, priority_callback=None):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.authorized_chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
        self.db_path = db_path
        self.alerts_bh_path = alerts_bh_path
        self.alerts_exo_path = alerts_exo_path
        self.toggle_callback = toggle_callback
        self.priority_callback = priority_callback
        self.running = True
        self.last_update_id = 0

    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown"):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=8)
        except Exception as e:
            print(f"[Telegram Bot] Send message error: {e}")

    def send_document(self, chat_id: str, file_path: Path, caption: str = ""):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendDocument"
            # Multipart upload
            boundary = "----AstroSentinelBoundary" + str(int(time.time()))
            body = []
            body.append(f"--{boundary}".encode())
            body.append(f'Content-Disposition: form-data; name="chat_id"'.encode())
            body.append(b"")
            body.append(str(chat_id).encode())
            
            if caption:
                body.append(f"--{boundary}".encode())
                body.append(f'Content-Disposition: form-data; name="caption"'.encode())
                body.append(b"")
                body.append(caption.encode())

            body.append(f"--{boundary}".encode())
            body.append(f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"'.encode())
            body.append(b"Content-Type: application/pdf")
            body.append(b"")
            with open(file_path, "rb") as f:
                body.append(f.read())
            body.append(f"--{boundary}--".encode())
            body.append(b"")

            data = b"\r\n".join(body)
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
            )
            urllib.request.urlopen(req, timeout=25)
            print(f"[Telegram Bot] 📄 PDF report sent to {chat_id}")
        except Exception as e:
            print(f"[Telegram Bot] Send document error: {e}")

    def get_status_text(self) -> str:
        total_stars = 0
        total_bh = 0
        total_exo = 0
        completed_patches = 0

        if self.db_path.exists():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*), SUM(is_candidate) FROM processed_targets")
                    r = cur.fetchone()
                    if r:
                        total_stars = r[0] or 0
                    cur.execute("SELECT COUNT(*) FROM surveyed_sky_patches WHERE status = 'COMPLETED'")
                    r2 = cur.fetchone()
                    if r2:
                        completed_patches = r2[0] or 0
            except Exception:
                pass

        if self.alerts_bh_path.exists():
            try:
                with open(self.alerts_bh_path) as f:
                    total_bh = sum(1 for line in f if line.strip())
            except Exception:
                pass

        if self.alerts_exo_path.exists():
            try:
                with open(self.alerts_exo_path) as f:
                    total_exo = sum(1 for line in f if line.strip())
            except Exception:
                pass

        return (
            f"🔭 *ASTRO SENTINEL: OBSERVATORY STATUS (24/7)*\n\n"
            f"⚡ *System State:* ACTIVE (Dual Mode)\n"
            f"🗺️ *Surveyed Sky Patches:* `{completed_patches}` completed cones\n"
            f"⭐ *Total Stars Audited:* `{total_stars:,}` targets\n"
            f"🕳️ *Black Hole Candidates:* `{total_bh}`\n"
            f"🪐 *Exoplanet Candidates:* `{total_exo}`\n\n"
            f"Use /target `<TIC>` to analyze a star, or /pause and /resume to toggle scanning."
        )

    def handle_command(self, chat_id: str, text: str):
        parts = text.strip().split()
        if not parts:
            return
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        if cmd in ["/start", "/help"]:
            reply = (
                "👋 *Welcome to Astro Sentinel 24/7 Command Console*\n\n"
                "Available commands:\n"
                "• `/status` - Real-time statistics, patch count & candidates\n"
                "• `/target <TIC>` - Prioritize immediate analysis of a star\n"
                "• `/report` - Receive the scientific discovery PDF of latest candidate\n"
                "• `/pause` - Pause continuous sky survey\n"
                "• `/resume` - Resume continuous sky survey\n"
            )
            self.send_message(chat_id, reply)

        elif cmd == "/status":
            self.send_message(chat_id, self.get_status_text())

        elif cmd == "/pause":
            if self.toggle_callback:
                self.toggle_callback(False)
            self.send_message(chat_id, "⏸️ *Astro Sentinel survey has been PAUSED.*")

        elif cmd == "/resume":
            if self.toggle_callback:
                self.toggle_callback(True)
            self.send_message(chat_id, "▶️ *Astro Sentinel survey has been RESUMED.*")

        elif cmd == "/target":
            if not args:
                self.send_message(chat_id, "⚠️ *Usage:* `/target 261136679` or `/target TIC 261136679`")
                return
            t_id = "TIC " + args[0].replace("TIC", "").strip()
            self.send_message(chat_id, f"🎯 *Target queued for high-priority analysis:* `{t_id}`. Analyzing both BH and Exoplanet signatures...")
            if self.priority_callback:
                self.priority_callback(t_id)

        elif cmd == "/report":
            # Find latest generated PDF report in outputs/
            out_dir = self.db_path.parent
            pdf_files = list(out_dir.glob("*.pdf"))
            if not pdf_files:
                self.send_message(chat_id, "ℹ️ No PDF observational proposals generated yet in outputs directory.")
            else:
                pdf_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest_pdf = pdf_files[0]
                self.send_document(chat_id, latest_pdf, caption=f"📄 Scientific Proposal: {latest_pdf.name}")

        else:
            self.send_message(chat_id, f"❓ Unknown command: `{cmd}`. Type /help for assistance.")

    def run_polling(self):
        print("[Telegram Bot] 🤖 Long-polling thread started.")
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read().decode("utf-8"))

                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        self.last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        chat = msg.get("chat", {})
                        chat_id = str(chat.get("id"))
                        text = msg.get("text", "")

                        # Auth check
                        if chat_id == self.authorized_chat_id and text:
                            self.handle_command(chat_id, text)
                        elif text:
                            self.send_message(chat_id, "⛔ Access denied. Unauthorized operator.")
            except Exception as e:
                time.sleep(2)

    def start_in_background(self):
        t = threading.Thread(target=self.run_polling, daemon=True, name="TelegramSentinelBot")
        t.start()
        return t
