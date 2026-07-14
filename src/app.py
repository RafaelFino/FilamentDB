"""
app.py — Entry point da aplicação Flask.
"""

import os
import sys
from pathlib import Path

from flask import Flask

# Adicionar o diretório raiz ao path para imports
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.web import register_routes

app = Flask(
    __name__,
    static_folder=str(ROOT_DIR / "static"),
    template_folder=str(ROOT_DIR / "templates"),
)
register_routes(app)


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
