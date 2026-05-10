import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parent / "services" / "agent-api"
sys.path.insert(0, str(SERVICE_ROOT))

from app.main import app  # noqa: E402
