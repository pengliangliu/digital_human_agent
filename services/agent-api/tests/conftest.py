import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
SERVICE_ROOT = APP_ROOT.parent

sys.path.insert(0, str(SERVICE_ROOT))
