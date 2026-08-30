"""
web.py — Rotas da API e páginas web.
"""

import time

from flask import jsonify, request, render_template, send_file

from src import auth, buildinfo, database, inventory, prices, services


def _probe(connect_fn, path, probe_sql):
    """Executa um probe de leitura contra um banco e mede latência.

    Retorna um dict no formato esperado pelos endpoints de health:
      {"status": "ok"|"error", "path": <str>, "latency_ms": <float>[, "error": <str>]}

    O probe roda `probe_sql` (um SELECT barato contra a tabela principal do
    banco). Não basta abrir a conexão: um arquivo .db vazio ou defasado abre
    sem erro mas falha no primeiro SELECT com "no such table". Esse é
    justamente o cenário que o Pangolin precisa enxergar como unhealthy.
    """
    start = time.perf_counter()
    conn = None
    try:
        conn = connect_fn()
        conn.execute(probe_sql).fetchone()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "path": str(path), "latency_ms": latency_ms}
    except Exception as exc:  # sqlite3.Error, arquivo ausente/corrompido, etc.
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "error", "path": str(path), "latency_ms": latency_ms, "error": str(exc)}
    finally:
        if conn is not None:
            conn.close()


def register_routes(app):
    @app.get("/health")
    def health():
        """Liveness: o processo Flask está de pé e respondendo.

        Barato de propósito — não toca em disco nem em banco. Sempre 200
        enquanto o worker consegue atender a requisição. Serve para o Pangolin
        detectar processo travado/morto, não dependências quebradas.
        """
        return jsonify({"status": "ok"})

    @app.get("/health/ready")
    def health_ready():
        """Readiness: o serviço consegue efetivamente atender requisições.

        Faz um probe de leitura em cada banco (catálogo + estoque). Retorna
        200 se ambos respondem, 503 se qualquer um falhar. O Pangolin avalia o
        health check pelo STATUS CODE, então o 503 é o que remove o target da
        rotação quando o banco está inacessível ou sem schema.
        """
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

    @app.get("/api/filaments")
    def list_filaments():
        return jsonify(database.list_filaments())

    @app.get("/filament-profiles")
    def list_filament_profiles():
        return jsonify(database.list_filament_profiles())

    @app.get("/filament-profiles/<int:profile_id>")
    def get_filament_profile(profile_id):
        profile = database.get_filament_profile(profile_id)
        if profile is None:
            return jsonify({"error": "profile not found"}), 404
        return jsonify(profile)

    @app.get("/manufacturers/<int:manufacturer_id>/materials")
    def list_materials_by_manufacturer(manufacturer_id):
        return jsonify(database.list_materials_by_manufacturer(manufacturer_id))

    @app.get("/download/creality-print")
    def download_creality_print_zip():
        manufacturer = request.args.get("manufacturer", "").strip()
        material = request.args.get("material", "").strip()
        if not manufacturer or not material:
            return jsonify({"error": "manufacturer and material query parameters are required"}), 400

        data, filename = services.build_creality_print_zip(manufacturer, material)
        if data is None:
            return jsonify({"error": "no profiles found for the requested manufacturer and material"}), 404

        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/creality-print/<path:manufacturer>/<path:material>")
    def download_creality_print_zip_path(manufacturer, material):
        data, filename = services.build_creality_print_zip(manufacturer, material)
        if data is None:
            return jsonify({"error": "no profiles found for the requested manufacturer and material"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/creality-print/options")
    def list_creality_print_download_options():
        return jsonify(database.list_creality_print_download_options())

    @app.get("/api/process-profiles")
    def list_process_profiles():
        return jsonify(database.list_process_profiles())

    @app.get("/api/process-profiles/<int:profile_id>")
    def get_process_profile(profile_id):
        profile = database.get_process_profile(profile_id)
        if profile is None:
            return jsonify({"error": "process profile not found"}), 404
        return jsonify(profile)

    @app.get("/api/materials/<int:material_id>/process-profiles")
    def list_process_profiles_by_material(material_id):
        return jsonify(database.list_process_profiles_by_material(material_id))

    @app.get("/download/process")
    def download_process_files():
        material = request.args.get("material", "").strip()
        if not material:
            return jsonify({"error": "material query parameter is required"}), 400

        data, filename = services.build_process_zip(material)
        if data is None:
            return jsonify({"error": "no process profiles found for the requested material"}), 404

        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/process/<path:material>")
    def download_process_files_path(material):
        data, filename = services.build_process_zip(material)
        if data is None:
            return jsonify({"error": "no process profiles found for the requested material"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/api/download/process/options")
    def list_process_download_options():
        conn = database.get_db_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT m.name AS material
            FROM process_profiles pp
            JOIN materials m ON m.id = pp.material_id
            WHERE pp.active = 1
            ORDER BY m.name
            """
        ).fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])

    # ─── Price intelligence API ──────────────────────────────────────────────

    @app.get("/api/prices")
    def prices_api():
        return jsonify(prices.dashboard())

    @app.get("/api/prices/<int:filament_id>/history")
    def price_history_api(filament_id):
        result = prices.history(filament_id)
        if result is None:
            return jsonify({"error": "tracked filament not found"}), 404
        return jsonify(result)

    # ─── Simulation API ──────────────────────────────────────────────────────

    @app.get("/api/simulate")
    def simulate_combination():
        """Calcula velocidades efetivas de uma combinação processo + filamento.

        Query params:
            process_id: ID do perfil de processo
            filament_id: ID do perfil de filamento
        """
        process_id = request.args.get("process_id", type=int)
        filament_id = request.args.get("filament_id", type=int)
        if not process_id or not filament_id:
            return jsonify({"error": "process_id and filament_id required"}), 400

        result = services.simulate_combination(process_id, filament_id)
        if result is None:
            return jsonify({"error": "profile not found"}), 404
        return jsonify(result)

    @app.get("/api/simulation-options")
    def simulation_options():
        """Lista opções disponíveis para a simulação (processos e filamentos)."""
        return jsonify(services.get_simulation_options())

    @app.get("/api/ranking")
    def ranking_api():
        """Retorna ranking de todas as combinações processo × filamento com scores."""
        return jsonify(services.get_ranking())

    # ─── Orca Slicer Downloads ───────────────────────────────────────────────

    @app.get("/download/orca/filament")
    def download_orca_filament_zip():
        manufacturer = request.args.get("manufacturer", "").strip()
        material = request.args.get("material", "").strip()
        if not manufacturer or not material:
            return jsonify({"error": "manufacturer and material query parameters are required"}), 400

        data, filename = services.build_orca_filament_zip(manufacturer, material)
        if data is None:
            return jsonify({"error": "no profiles found"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/orca/filament/<path:manufacturer>/<path:material>")
    def download_orca_filament_zip_path(manufacturer, material):
        data, filename = services.build_orca_filament_zip(manufacturer, material)
        if data is None:
            return jsonify({"error": "no profiles found"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/orca/process/<path:material>")
    def download_orca_process_zip_path(material):
        data, filename = services.build_orca_process_zip(material)
        if data is None:
            return jsonify({"error": "no process profiles found"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/download/orca/process")
    def download_orca_process_zip():
        material = request.args.get("material", "").strip()
        if not material:
            return jsonify({"error": "material query parameter is required"}), 400
        data, filename = services.build_orca_process_zip(material)
        if data is None:
            return jsonify({"error": "no process profiles found"}), 404
        return send_file(data, mimetype="application/zip", as_attachment=True, download_name=filename)

    # ─── Inventory API (controle de estoque) ─────────────────────────────────
    # Único conjunto de endpoints de ESCRITA do projeto. Persistido em
    # inventory.db (separado do catálogo), que sobrevive aos rebuilds.

    @app.get("/api/inventory")
    def list_inventory():
        """Estoque organizado por localização física (impressora → drybox → aberto → estoque)."""
        return jsonify(inventory.grouped_by_location())

    @app.get("/api/inventory/by-material")
    def list_inventory_by_material():
        """Estoque agrupado por material (paletas de cor por material)."""
        return jsonify(inventory.grouped_by_material())

    @app.get("/api/inventory/items")
    def list_inventory_items():
        """Lista plana de todos os itens de estoque."""
        return jsonify(inventory.list_items())

    @app.get("/api/inventory/<int:item_id>")
    def get_inventory_item(item_id):
        item = inventory.get_item(item_id)
        if item is None:
            return jsonify({"error": "item not found"}), 404
        return jsonify(item)

    @app.post("/api/inventory")
    @auth.require_writer
    def create_inventory_item():
        data = request.get_json(silent=True) or {}
        try:
            item = inventory.add_item(data)
        except inventory.LocationFullError as exc:
            return jsonify({"error": str(exc), "code": "location_full", "status": exc.status}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(item), 201

    @app.patch("/api/inventory/<int:item_id>")
    @auth.require_writer
    def update_inventory_item(item_id):
        data = request.get_json(silent=True) or {}
        try:
            item = inventory.update_item(item_id, data)
        except inventory.LocationFullError as exc:
            return jsonify({"error": str(exc), "code": "location_full", "status": exc.status}), 409
        if item is None:
            return jsonify({"error": "item not found"}), 404
        return jsonify(item)

    @app.post("/api/inventory/<int:item_id>/use")
    @auth.require_writer
    def use_inventory_item(item_id):
        """Marca uso: decrementa `amount` rolos (default 1)."""
        data = request.get_json(silent=True) or {}
        amount = int(data.get("amount", 1) or 1)
        item = inventory.use_item(item_id, amount)
        if item is None:
            return jsonify({"error": "item not found"}), 404
        return jsonify(item)

    @app.delete("/api/inventory/<int:item_id>")
    @auth.require_writer
    def delete_inventory_item(item_id):
        ok = inventory.delete_item(item_id)
        if not ok:
            return jsonify({"error": "item not found"}), 404
        return jsonify({"status": "deleted", "id": item_id})

    @app.get("/api/inventory/export")
    def export_inventory():
        """Dump lógico versionado do estoque (backup/migração).

        Retorna um envelope {schema_version, exported_at, count, items}
        desacoplado do schema físico. Consumido pelo update-server.sh (backup
        via curl) e por qualquer restauração posterior via /import.
        """
        return jsonify(inventory.export_data())

    @app.post("/api/inventory/import")
    @auth.require_writer
    def import_inventory():
        """Importa um envelope de export com upsert idempotente por uid.

        Query param opcional `replace=true` ativa o modo espelho (remove itens
        ausentes do payload). Default é merge (não apaga nada).
        """
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "corpo JSON ausente ou inválido"}), 400
        replace = request.args.get("replace", "").lower() in ("1", "true", "yes")
        try:
            summary = inventory.import_data(payload, replace=replace)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "imported", "replace": replace, "summary": summary})

    # ─── Identidade / build info ─────────────────────────────────────────────

    @app.get("/api/me")
    def whoami():
        """Identidade e permissão do usuário atual (para a UI).

        Com auth desligada: {"user": "guest", "can_write": true, ...}.
        Com auth ligada: o e-mail do header do proxy e se ele pode escrever.
        """
        return jsonify(auth.me())

    @app.get("/api/build-info")
    def build_info():
        """Data/commit da última atualização bem-sucedida (escrita pelo update-server.sh)."""
        return jsonify(buildinfo.read())

    # ─── Tree and pages ──────────────────────────────────────────────────────

    @app.get("/api/tree")
    def tree_api():
        return jsonify(database.build_tree())

    @app.get("/api/process-tree")
    def process_tree_api():
        return jsonify(database.build_process_tree())

    @app.get("/dashboard")
    def dashboard_page():
        return render_template(
            "dashboard.html",
            tree=database.build_tree(),
            process_tree=database.build_process_tree(),
        )

    @app.get("/")
    def index_page():
        return render_template(
            "dashboard.html",
            tree=database.build_tree(),
            process_tree=database.build_process_tree(),
        )

    @app.get("/process-profiles")
    def process_profiles_page():
        return render_template(
            "dashboard.html",
            tree=database.build_tree(),
            process_tree=database.build_process_tree(),
        )

    @app.get("/tree")
    def tree_page():
        return render_template(
            "dashboard.html",
            tree=database.build_tree(),
            process_tree=database.build_process_tree(),
        )
