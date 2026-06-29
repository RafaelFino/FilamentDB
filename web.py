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

    @app.get("/tree")
    def tree_page():
        tree = app_database.build_tree()
        return render_template("tree.html", tree=tree)
