import os

from flask import Flask

from web import register_routes

app = Flask(__name__, static_folder="static", template_folder="templates")
register_routes(app)

if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
