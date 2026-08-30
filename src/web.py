"""web.py — Rotas da API e páginas web."""

import time

from flask import jsonify, request, render_template, send_file

from src import auth, buildinfo, database, inventory, prices, services


def _probe(connect_fn, path, probe_sql):
    """Executa um probe de leitura contra um banco e mede latência.

    Retorna um dict no formato esperado pelos endpoints de health:
      {"status": "ok"|"error", "path": <str>, "latency_ms": <float>[, "error": <str>]}
    """
    start = time.perf_counter()
    conn = None
    try:
        conn = connect_fn()
        conn.execute(probe_sql).fetchone()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "path": str(path), "latency_ms": latency_ms}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "error", "path": str(path), "latency_ms": latency_ms, "error": str(exc)}
    finally:
        if conn is not None:
            conn.close()


def register_routes(app):
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/health/ready")
    def health_ready():
        checks = {
            "filament_db": _probe(
                database.get_db_connection,
                database.DB_PATH,
                "SELECT 1 FROM filament_profiles LIMIT 1",
            ),
            "inventory_db": _probe(
                inventory.get_connection,
                inventory.INVENTORY_DB_PATH,
                "SELECT 1 FROM inventory_items LIMIT 1",
            ),
        }
        healthy = all(c["status"] == "ok" for c in checks.values())
        body = {"status": "ok" if healthy else "error", "checks": checks}
        return jsonify(body), (200 if healthy else 503)

    @app.get("/manufacturers")
    def list_manufacturers():
        return jsonify(database.list_manufacturers())

    @app.get("/materials")
    def list_materials():
        return jsonify(database.list_materials())

    @app.get("/filaments")
    def list_filaments():
        return jsonify(database.list_filaments())

    @app.get("/filaments/<string:slug>")
    def get_filament(slug):
        filament = database.get_filament(slug)
        if filament is None:
            return jsonify({"error": "Filament not found"}), 404
        return jsonify(filament)

    @app.get("/prices")
    def list_prices():
        return jsonify(prices.list_prices(request.args))

    @app.get("/services")
    def list_services():
        return jsonify(services.list_services())

    @app.get("/api/inventory")
    def list_inventory():
        return jsonify(inventory.list_items())

    @app.get("/api/inventory/export")
    def export_inventory():
        return jsonify(inventory.export_inventory())

    @app.post("/api/inventory/import")
    def import_inventory():
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "JSON body required"}), 400
        try:
            result = inventory.import_inventory(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.get("/api/build-info")
    def api_build_info():
        return jsonify(buildinfo.get_build_info())

    @app.get("/api/price-history")
    def price_history():
        return jsonify(prices.price_history(request.args))

    @app.get("/api/price-sources")
    def price_sources():
        return jsonify(prices.price_sources())

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok"})

    @app.get("/api/health/ready")
    def api_health_ready():
        return health_ready()

    @app.get("/api/docs")
    def api_docs():
        return render_template("api.html")

    @app.get("/favicon.ico")
    def favicon():
        return send_file("static/favicon.ico", mimetype="image/x-icon")

    @app.get("/")
    def index():
        tree = database.build_tree()
        process_tree = database.build_process_tree()
        return render_template("dashboard.html", tree=tree, process_tree=process_tree)

    @app.get("/inventory")
    def inventory_page():
        return render_template("inventory.html")

    @app.get("/prices")
    def prices_page():
        return render_template("prices.html")
