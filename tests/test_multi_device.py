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
        # Valores-chave do Standard 0.20 PLA (base recalibrada, conservadora).
        # inner usa speed mult 1.0 (300); os campos de quality usam quality_speed
        # 0.50 (acabamento externo melhorado): outer 150*0.50=75, top 130*0.50=65,
        # init 50*0.50=25, gap 200*0.50=100. Infill (sparse) não é quality field.
        self.assertEqual(float(prof["inner_wall_speed"]), 300.0)
        self.assertEqual(float(prof["outer_wall_speed"]), 75.0)
        self.assertEqual(float(prof["top_surface_speed"]), 65.0)
        self.assertEqual(float(prof["initial_layer_speed"]), 25.0)
        self.assertEqual(float(prof["gap_infill_speed"]), 100.0)
        self.assertEqual(float(prof["sparse_infill_speed"]), 350.0)
        self.assertEqual(int(float(prof["default_acceleration"])), 18000)

    def test_cc2_standard_quality_speed_matches_k2(self):
        # quality_speed é por profile_type, independente do device: o Standard da
        # cc2 recebe os mesmos 4 valores de acabamento do k2.
        device = build_mod.load_device("cc2")
        prof = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        self.assertEqual(float(prof["outer_wall_speed"]), 75.0)
        self.assertEqual(float(prof["top_surface_speed"]), 65.0)
        self.assertEqual(float(prof["initial_layer_speed"]), 25.0)
        self.assertEqual(float(prof["gap_infill_speed"]), 100.0)

    def test_speed_scale_high_layers(self):
        # speed_scale reduz extrusão em layer heights altos (combate sub-extrusão),
        # sem tocar travel. 0.24=0.85, 0.28=0.75; 0.20 sem scale.
        device = build_mod.load_device("k2")
        p24 = build_mod.generate_process_profile("standard", "0.24", "PLA", device)
        p28 = build_mod.generate_process_profile("standard", "0.28", "PLA", device)
        p20 = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        self.assertEqual(float(p24["inner_wall_speed"]), 255.0)
        self.assertEqual(float(p28["inner_wall_speed"]), 225.0)
        self.assertEqual(float(p20["inner_wall_speed"]), 300.0)
        # travel não é escalado (movimento sem extrusão).
        self.assertEqual(float(p24["travel_speed"]), 700.0)
        self.assertEqual(float(p28["travel_speed"]), 700.0)

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


# Conjunto estendido multi-material/CFS que deve ser idêntico entre todos os
# profile types: 8 campos de prime-tower/flush + 9 campos de CFS materializados
# em base.json. É a invariante que garante o reconhecimento de multifilamento
# (CFS) sem depender da resolução da cadeia de inherits no runtime do slicer.
MULTI_MATERIAL_KEYSET = [
    "enable_prime_tower", "prime_tower_width", "prime_tower_brim_width",
    "prime_volume", "flush_into_infill", "flush_into_objects",
    "flush_into_support", "flush_multiplier",
    "single_extruder_multi_material_priming", "wiping_volumes_extruders",
    "wipe_tower_bridging", "wipe_tower_cone_angle", "wipe_tower_extra_spacing",
    "wipe_tower_no_sparse_layers", "wipe_tower_rotation_angle",
    "prime_tower_enhance_type", "ooze_prevention",
]


class MultiMaterialCFSTests(unittest.TestCase):
    """Todo profile type em 0.20 carrega o MESMO conjunto multi-material/CFS que
    o Standard. Protege o fix do bug de multifilamento (Detail/outros não
    reconhecidos pelo CFS): o bloco é materializado explícito em todo perfil.
    """

    def _profile_types_at_020(self):
        combinations = _load_combinations()
        types = set()
        for combo in combinations["combinations"]:
            if "0.20" in combo["layer_heights"]:
                types.add(combo["profile_type"])
        return sorted(types)

    def test_cfs_keyset_matches_standard(self):
        device = build_mod.load_device("k2")
        ref = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        ref_vals = {k: ref.get(k) for k in MULTI_MATERIAL_KEYSET}
        # Nenhum campo do conjunto pode faltar no Standard (todos vêm da base).
        for k in MULTI_MATERIAL_KEYSET:
            self.assertIsNotNone(ref_vals[k], f"Standard sem campo CFS '{k}'")
        for pt in self._profile_types_at_020():
            prof = build_mod.generate_process_profile(pt, "0.20", "PLA", device)
            vals = {k: prof.get(k) for k in MULTI_MATERIAL_KEYSET}
            self.assertEqual(
                vals, ref_vals,
                f"profile type '{pt}' 0.20 PLA diverge do Standard no conjunto CFS",
            )

    def test_wiping_volumes_present_in_exports(self):
        """Todo JSON de processo exportado (CP e Orca) contém
        wiping_volumes_extruders explicitamente — campo-chave do CFS."""
        import glob
        files = sorted(set(
            glob.glob(str(ROOT / "Creality-Print" / "process" / "*.json"))
            + glob.glob(str(ROOT / "OrcaSlicer" / "process" / "*.json"))
            + glob.glob(str(ROOT / "OrcaSlicer" / "process" / "**" / "*.json"), recursive=True)
        ))
        if not files:
            self.skipTest("nenhum JSON exportado (rodar build.py antes)")
        missing = [f for f in files if not json.load(open(f)).get("wiping_volumes_extruders")]
        self.assertEqual(missing, [], f"JSONs sem wiping_volumes_extruders: {missing}")


class ZAADetailScopeTests(unittest.TestCase):
    """ZAA (Z-layer anti-aliasing) é campo de qualidade Detail-only.

    O Detail declara zaa_enabled=1 / zaa_minimize_perimeter_height=55 /
    zaa_min_z=0.06; nenhum outro profile type os declara (ficam ausentes).
    """

    def test_detail_sets_zaa(self):
        device = build_mod.load_device("k2")
        prof = build_mod.generate_process_profile("detail", "0.20", "PLA", device)
        self.assertEqual(prof.get("zaa_enabled"), "1")
        self.assertEqual(prof.get("zaa_minimize_perimeter_height"), "55")
        self.assertEqual(prof.get("zaa_min_z"), "0.06")

    def test_standard_has_no_zaa(self):
        device = build_mod.load_device("k2")
        prof = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        self.assertNotIn("zaa_enabled", prof)
        self.assertNotIn("zaa_minimize_perimeter_height", prof)
        self.assertNotIn("zaa_min_z", prof)


class IroningDetailScopeTests(unittest.TestCase):
    """Ironing completo (6 campos) é configuração Detail-only.

    O Detail declara ironing_type=topmost / ironing_pattern=rectilinear /
    ironing_speed=30 / ironing_flow=50% / ironing_spacing=0.15 /
    ironing_angle=90. O Standard mantém seu ironing leve próprio
    (ironing_type=top, ironing_flow=7%) SEM ironing_pattern/ironing_angle.
    """

    def test_detail_ironing(self):
        device = build_mod.load_device("k2")
        prof = build_mod.generate_process_profile("detail", "0.20", "PLA", device)
        self.assertEqual(prof.get("ironing_type"), "topmost")
        self.assertEqual(prof.get("ironing_pattern"), "rectilinear")
        self.assertEqual(str(prof.get("ironing_flow")), "50%")
        self.assertEqual(str(prof.get("ironing_angle")), "90")
        self.assertAlmostEqual(float(prof.get("ironing_speed")), 30.0)
        self.assertAlmostEqual(float(prof.get("ironing_spacing")), 0.15)

    def test_standard_ironing_has_no_detail_fields(self):
        device = build_mod.load_device("k2")
        prof = build_mod.generate_process_profile("standard", "0.20", "PLA", device)
        # Standard mantém seu ironing leve próprio.
        self.assertEqual(prof.get("ironing_type"), "top")
        self.assertEqual(str(prof.get("ironing_flow")), "7%")
        # Mas NÃO carrega os campos exclusivos do Detail.
        self.assertNotIn("ironing_pattern", prof)
        self.assertNotIn("ironing_angle", prof)


class _BuildDBMixin:
    """Build real (--only-db) em DB temporário, compartilhado entre testes."""

    @classmethod
    def _build_db(cls):
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


class ProcessCountTests(_BuildDBMixin, unittest.TestCase):
    """Contrato de contagem: 51 processos no banco, factory ausente."""

    @classmethod
    def setUpClass(cls):
        cls._build_db()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_total_process_count(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        conn = sqlite3.connect(self.db_path)
        try:
            (total,) = conn.execute("SELECT COUNT(*) FROM process_profiles").fetchone()
            self.assertEqual(total, 51, f"esperado 51 processos, obtido {total}")
            (factory,) = conn.execute(
                "SELECT COUNT(*) FROM process_profiles WHERE profile_type='factory'"
            ).fetchone()
            self.assertEqual(factory, 0, "factory não deve aparecer em process_profiles")
        finally:
            conn.close()

    def test_support_critical_regions_only_invariant(self):
        """Todo processo (todos os devices, k2 + cc2) tem
        support_critical_regions_only == 1."""
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT profile_name, support_critical_regions_only FROM process_profiles"
            ).fetchall()
            bad = [name for name, v in rows if v != 1]
            self.assertEqual(bad, [], f"processos com suporte crítico desligado: {bad}")
        finally:
            conn.close()


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
