import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "services" / "agent-api"))

from app.main import app
import uvicorn
from app.config import Settings

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level)
