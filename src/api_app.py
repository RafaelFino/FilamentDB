"""Entry point for the isolated public FilamentDB ingestion service."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from flask import Flask

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src import config  # noqa: E402
from src.api import register_public_api  # noqa: E402

config.load()

app = Flask(__name__)
register_public_api(app)


if __name__ == "__main__":
    host = os.environ.get("FILAMENTDB_API_HOST", "0.0.0.0")
    port = int(os.environ.get("FILAMENTDB_API_PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
