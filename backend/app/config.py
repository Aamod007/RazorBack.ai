import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

# Razorpay Test Mode Credentials
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dg_webhook_secret_razorpay_2026").strip()

# Mode: Live Test API if both keys present, else Sandbox Mode
IS_LIVE_API_MODE = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

# Bounded Decision Gate Thresholds
AMOUNT_CEILING_INR = float(os.getenv("AMOUNT_CEILING_INR", "2000.0"))
AUTO_CONTEST_CONFIDENCE_FLOOR = float(os.getenv("AUTO_CONTEST_CONFIDENCE_FLOOR", "0.65"))
AUTO_CONTEST_MIN_COMPLETENESS = float(os.getenv("AUTO_CONTEST_MIN_COMPLETENESS", "0.70"))
AUTO_ACCEPT_THRESHOLD_INR = float(os.getenv("AUTO_ACCEPT_THRESHOLD_INR", "500.0"))
AUTO_ACCEPT_CONFIDENCE_CEILING = float(os.getenv("AUTO_ACCEPT_CONFIDENCE_CEILING", "0.25"))

# SLA Failsafes (hours)
DEADLINE_URGENT_HOURS = float(os.getenv("DEADLINE_URGENT_HOURS", "48.0"))
DEADLINE_FAILSAFE_HOURS = float(os.getenv("DEADLINE_FAILSAFE_HOURS", "12.0"))

# Database
DB_PATH = DATA_DIR / "disputeguard.db"
MODEL_PATH = DATA_DIR / "risk_model.json"
EVAL_METRICS_PATH = DATA_DIR / "eval_metrics.json"

# Server
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Logistics & Alert Integrations
SHIPROCKET_TOKEN = os.getenv("SHIPROCKET_TOKEN", "").strip()
DELHIVERY_TOKEN = os.getenv("DELHIVERY_TOKEN", "").strip()
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()
