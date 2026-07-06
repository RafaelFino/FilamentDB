import os
from flask import jsonify, request, render_template, send_file

import app_database
import services


def register_routes(app):
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "database": app_database.DB_PATH})

    @app.get("/manufacturers")
    def list_manufacturers():
        return jsonify(app_database.list_manufacturers())

    @app.get("/materials")
    def list_materials():
        return jsonify(app_database.list_materials())

    @app.get("/filament-profiles")
    def list_filament_profiles():
        return jsonify(app_database.list_filament_profiles())

    @app.get("/filament-profiles/<int:profile_id>")
    def get_filament_profile(profile_id):
        profile = app_database.get_filament_profile(profile_id)
        if profile is None:
            return jsonify({"error": "profile not found"}), 404
        return jsonify(profile)

    @app.get("/manufacturers/<int:manufacturer_id>/materials")
    def list_materials_by_manufacturer(manufacturer_id):
        return jsonify(app_database.list_materials_by_manufacturer(manufacturer_id))

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
        return jsonify(app_database.list_creality_print_download_options())

    @app.get("/api/process-profiles")
    def list_process_profiles():
        return jsonify(app_database.list_process_profiles())

    @app.get("/api/process-profiles/<int:profile_id>")
    def get_process_profile(profile_id):
        profile = app_database.get_process_profile(profile_id)
        if profile is None:
            return jsonify({"error": "process profile not found"}), 404
        return jsonify(profile)

    @app.get("/api/materials/<int:material_id>/process-profiles")
    def list_process_profiles_by_material(material_id):
        return jsonify(app_database.list_process_profiles_by_material(material_id))

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
        conn = app_database.get_db_connection()
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

    @app.get("/process-profiles")
    def process_profiles_page():
        return render_template("process-profiles.html")

    @app.get("/tree")
    def tree_page():
        tree = app_database.build_tree()
        return render_template("tree.html", tree=tree)
