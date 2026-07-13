"""Central configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "fixza-verify-token")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fixza.db")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "claude-haiku-4-5-20251001")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

# When no WhatsApp token is configured we run in "dry-run" mode: outbound
# messages are logged instead of sent, so the whole flow is testable locally.
DRY_RUN = not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID)
