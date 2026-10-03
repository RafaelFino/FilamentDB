"""Contract tests for the multi-device profile pipeline.

Protege o contrato device como dimensão de primeira classe:
  - todo device referenciado em combinations.json tem arquivo em devices/;
  - os perfis gerados respeitam os caps físicos do seu device;
  - o perfil Standard 0.20 PLA do K2 mantém os valores atuais (regressão);
  - perfis Orca têm compatible_printers/inherits coerentes com o device;
  - devices com creality_print desabilitado não geram perfil Creality Print.

Roda offline (sem rede/LLM), no mesmo job `test` do CI via `pytest tests/`.
Importa build.py diretamente para exercitar a lógica de device sem precisar
escrever nos diretórios de export do repositório.
"""
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build as build_mod  # noqa: E402

DEVICES_DIR = ROOT / "process-base" / "devices"
COMBINATIONS = ROOT / "process-base" / "combinations.json"

# Campos de velocidade/aceleração dos perfis de processo que devem respeitar os
# caps do device. Mapeia cada campo ao limite relevante do device.
SPEED_FIELDS = [
    "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "initial_layer_speed",
    "support_speed", "gap_infill_speed",
]
ACCEL_FIELDS = [
    "default_acceleration", "inner_wall_acceleration",
    "outer_wall_acceleration", "top_surface_acceleration",
]


def _load_combinations():
    with open(COMBINATIONS, "r", encoding="utf-8") as f:
        return json.load(f)


def _referenced_devices(combinations):
    refs = set(combinations.get("default_devices", ["k2"]))
    for combo in combinations["combinations"]:
        refs.update(combo.get("devices", []))
    return refs


class CombinationDeviceDefinitionTests(unittest.TestCase):
    def test_all_combination_devices_have_definition(self):
        combinations = _load_combinations()
        for dev_id in _referenced_devices(combinations):
            path = DEVICES_DIR / f"{dev_id}.json"
            self.assertTrue(
                path.exists(),
                f"device '{dev_id}' referenciado em combinations.json sem arquivo {path}",
            )
            # load_device deve carregar sem erro (schema mínimo + defaults).
            device = build_mod.load_device(dev_id)
            self.assertEqual(device["id"], dev_id)
            self.assertIn("limits", device)


class DeviceCapTests(unittest.TestCase):
    def test_generated_speeds_respect_device_caps(self):
        combinations = _load_combinations()
        default_devices = combinations.get("default_devices", ["k2"])
        checked = 0
        for combo in combinations["combinations"]:
            pt = combo["profile_type"]
            for dev_id in combo.get("devices", default_devices):
                device = build_mod.load_device(dev_id)
                limits = device["limits"]
                for lh in combo["layer_heights"]:
                    for mat in combo["materials"]:
                        prof = build_mod.generate_process_profile(pt, lh, mat, device)
                        for field in SPEED_FIELDS:
                            if field in prof:
                                self.assertLessEqual(
                                    float(prof[field]),
                                    float(limits["max_extrusion_speed"]) + 1e-6,
                                    f"{dev_id}/{pt}/{lh}/{mat}: {field} acima do cap de extrusão",
                                )
                        if "travel_speed" in prof:
                            self.assertLessEqual(
                                float(prof["travel_speed"]),
                                float(limits["max_travel_speed"]) + 1e-6,
                                f"{dev_id}/{pt}/{lh}/{mat}: travel_speed acima do cap",
                            )
                        for field in ACCEL_FIELDS:
                            if field in prof:
                                self.assertLessEqual(
                                    float(prof[field]),
                                    float(limits["max_acceleration"]) + 1e-6,
                                    f"{dev_id}/{pt}/{lh}/{mat}: {field} acima do cap de aceleração",
                                )
                        checked += 1
        self.assertGreater(checked, 0, "nenhum perfil exercitado")


class K2RegressionTests(unittest.TestCase):
    def test_k2_standard_regression(self):
        device = build_mod.load_device("k2")
        prof = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        # Nome idêntico ao perfil atual.
        self.assertEqual(prof["name"], "0.20mm Standard @Creality K2 0.4 nozzle - PLA")
        # inherits Creality Print do K2.
        self.assertEqual(prof["inherits"], "0.20mm Standard @Creality K2 0.4 nozzle")
        # Valores-chave do Standard 0.20 PLA (base calibrada para K2).
        self.assertEqual(float(prof["inner_wall_speed"]), 450.0)
        self.assertEqual(float(prof["outer_wall_speed"]), 250.0)
        self.assertEqual(float(prof["sparse_infill_speed"]), 500.0)
        self.assertEqual(int(float(prof["default_acceleration"])), 18000)

    def test_k2_caps_are_600_800_20000(self):
        device = build_mod.load_device("k2")
        self.assertEqual(device["limits"]["max_extrusion_speed"], 600)
        self.assertEqual(device["limits"]["max_travel_speed"], 800)
        self.assertEqual(device["limits"]["max_acceleration"], 20000)


class OrcaCoherenceTests(unittest.TestCase):
    def test_orca_profile_device_coherence(self):
        combinations = _load_combinations()
        default_devices = combinations.get("default_devices", ["k2"])
        for combo in combinations["combinations"]:
            for dev_id in combo.get("devices", default_devices):
                device = build_mod.load_device(dev_id)
                orca = device["slicers"].get("orca", {})
                if not orca.get("enabled"):
                    continue
                # compatible_printers vem do device e não é vazio.
                self.assertTrue(
                    orca.get("compatible_printers"),
                    f"device '{dev_id}' Orca habilitado sem compatible_printers",
                )
                # inherits resolve para cada layer height da combinação.
                for lh in combo["layer_heights"]:
                    inh = build_mod.resolve_inherits(
                        orca.get("process_inherits_by_layer", []),
                        lh,
                        display_name=device["display_name"],
                        profile_type=combo["profile_type"],
                    )
                    self.assertTrue(
                        inh, f"device '{dev_id}' sem inherits Orca para layer {lh}",
                    )


class CrealityPrintOnlyWhenEnabledTests(unittest.TestCase):
    """Devices com creality_print desabilitado não devem gerar inherits CP.

    Garante a regra que isola a CC2 (Orca-only) sem depender de a CC2 já estar
    presente no combinations.json.
    """

    def test_cp_disabled_device_has_no_cp_inherits(self):
        # Device sintético Orca-only (mesmo contrato da CC2).
        device = {
            "id": "cp_disabled_probe",
            "display_name": "Probe Printer",
            "nozzle": "0.4",
            "orca_name_suffix": "PROBE",
            "name_template": build_mod.DEVICE_DEFAULT_NAME_TEMPLATE,
            "limits": dict(build_mod.DEVICE_DEFAULT_LIMITS),
            "slicers": {
                "orca": {"enabled": True, "compatible_printers": ["Probe 0.4 nozzle"],
                         "process_inherits_by_layer": [
                             {"max": 99.0, "inherits": "0.20mm Standard @Probe 0.4 nozzle"}]},
                "creality_print": {"enabled": False},
            },
        }
        prof = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        self.assertIsNone(
            prof["inherits"],
            "device com creality_print desabilitado não deve ter inherits CP",
        )

    def test_cc2_is_orca_only_if_present(self):
        # Se a CC2 já estiver cadastrada, ela deve ser Orca-only.
        path = DEVICES_DIR / "cc2.json"
        if not path.exists():
            self.skipTest("cc2.json ainda não cadastrado")
        device = build_mod.load_device("cc2")
        self.assertFalse(
            device["slicers"].get("creality_print", {}).get("enabled", False),
            "CC2 deve ter creality_print desabilitado (Orca-only)",
        )


class BuildDeviceColumnTests(unittest.TestCase):
    """Build real (--only-db) em DB temporário: coluna device_id populada."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmp.name) / "filament.db"
        env = dict(os.environ)
        env["DB_PATH"] = str(cls.db_path)
        py = ROOT / ".venv" / "bin" / "python"
        python = str(py) if py.exists() else sys.executable
        cls.result = subprocess.run(
            [python, "build.py", "--only-db"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_build_succeeded(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"build.py --only-db falhou:\n{self.result.stderr[-2000:]}",
        )

    def test_device_id_column_populated(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(process_profiles)")}
            self.assertIn("device_id", cols)
            rows = conn.execute(
                "SELECT DISTINCT device_id FROM process_profiles"
            ).fetchall()
            device_ids = {r[0] for r in rows}
            self.assertTrue(device_ids, "nenhum process_profile gerado")
            # Todo device_id presente no banco deve ter arquivo de device.
            for dev_id in device_ids:
                self.assertTrue(
                    (DEVICES_DIR / f"{dev_id}.json").exists(),
                    f"device_id '{dev_id}' no banco sem arquivo de device",
                )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
