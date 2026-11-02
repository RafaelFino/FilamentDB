"""Testes do validador de invariantes dos perfis de processo (validate.py).

Modelado em tests/test_multi_device.py: insere ROOT no sys.path, importa build
e validate, e usa o mesmo padrão de build real (--only-db em DB temporário) para
o teste de integração.

Cobre (Requisito 4.5 da spec profile-audit-consistency):
  (a) perfil válido gerado por build → 0 violações HIGH;
  (b) BUG MOTIVADOR: initial_layer_print_height=0.24 @ layer_height=0.16 →
      check_layer_multiple reporta exatamente 1 violação HIGH (injeção SÓ no
      teste, nunca em process-base);
  (c) velocidade acima do cap do device → check_device_caps reporta HIGH;
  (d) integração: build.py --only-db (validação ON por default) sobre a
      process-base ATUAL retorna exit 0;
  (e) check_combinations: contagem != total derivado → HIGH.

NÃO depende de tests/test_price_pipeline_e2e.py nem tests/test_inventory_e2e.py
(travam em deps de rede).
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build as build_mod  # noqa: E402
import validate as validate_mod  # noqa: E402

COMBINATIONS = build_mod.PROCESS_BASE_DIR / "combinations.json"


def _load_combinations():
    import json
    with open(COMBINATIONS, "r", encoding="utf-8") as f:
        return json.load(f)


def _valid_item(profile_type="standard", layer_height="0.20", material="PLA",
                device_id="k2"):
    """GeneratedProfile real, gerado por build.generate_process_profile."""
    device = build_mod.load_device(device_id)
    profile = build_mod.generate_process_profile(
        profile_type, layer_height, material, device
    )
    return validate_mod.GeneratedProfile(
        profile=profile,
        profile_type=profile_type,
        layer_height=layer_height,
        material=material,
        device=device,
    )


class ValidProfileTests(unittest.TestCase):
    def test_valid_profile_no_high(self):
        """(a) Standard 0.20 PLA k2 não gera nenhuma violação HIGH."""
        item = _valid_item()
        one_combo = {
            "default_devices": ["k2"],
            "combinations": [{
                "profile_type": "standard",
                "layer_heights": ["0.20"],
                "materials": ["PLA"],
                "devices": ["k2"],
            }],
        }
        violations = validate_mod.run_all([item], {"k2": item.device}, one_combo)
        highs = [v for v in violations if v.severity == "high"]
        self.assertEqual(highs, [], f"HIGH inesperadas: {[str(v) for v in highs]}")


class LayerMultipleTests(unittest.TestCase):
    def test_motivating_bug_non_multiple_is_high(self):
        """(b) initial_layer_print_height=0.24 @ layer_height=0.16 → 1 HIGH.

        Injeção SÓ no fixture de teste — nunca em process-base. Razão 1.5 não é
        inteira: é a classe do bug do Safe que o validador deve pegar.
        """
        item = _valid_item(layer_height="0.16")
        item.profile["initial_layer_print_height"] = "0.24"
        violations = validate_mod.check_layer_multiple(item)
        highs = [v for v in violations if v.severity == "high"]
        self.assertEqual(len(highs), 1, f"esperado 1 HIGH, obtido {len(highs)}")
        self.assertEqual(highs[0].invariant, "check_layer_multiple")

    def test_profile_type_override_source_attribution(self):
        """Quando o profile_type força o valor não-múltiplo, a fonte citada é o
        profile_type (não o layer_height). Simula o caso Safe-style."""
        item = _valid_item(profile_type="standard", layer_height="0.16")
        # Simula um profile_type cujo raw também teria 0.24 — usamos monkeypatch
        # do helper para não depender de dados reais.
        item.profile["initial_layer_print_height"] = "0.24"
        original = validate_mod._load_profile_type_raw
        validate_mod._load_profile_type_raw = lambda pt: {"initial_layer_print_height": "0.24"}
        try:
            violations = validate_mod.check_layer_multiple(item)
        finally:
            validate_mod._load_profile_type_raw = original
        self.assertEqual(len(violations), 1)
        self.assertIn("profile_types/standard.json", violations[0].source_path)

    def test_valid_multiple_passes_prime_tower_off(self):
        """0.24 @ 0.12 (2x) é múltiplo inteiro → sem violação SÓ com a prime
        tower desligada (piso mínimo = múltiplo inteiro). Com a prime tower
        ligada a regra endurecida exige igualdade estrita (coberto abaixo)."""
        item = _valid_item(layer_height="0.12")
        item.profile["initial_layer_print_height"] = "0.24"
        item.profile["enable_prime_tower"] = "0"
        self.assertEqual(validate_mod.check_layer_multiple(item), [])

    def test_multiple_but_not_equal_is_high_with_prime_tower(self):
        """INVARIANTE DO FIX CFS: 0.24 @ 0.12 (2x, múltiplo inteiro) ainda é
        HIGH quando a prime tower está ligada — a condição segura é
        initial == layer_height, não apenas múltiplo inteiro."""
        item = _valid_item(layer_height="0.12")
        item.profile["initial_layer_print_height"] = "0.24"
        # prime tower ligada por default (base.json enable_prime_tower=1)
        violations = validate_mod.check_layer_multiple(item)
        highs = [v for v in violations if v.severity == "high"]
        self.assertEqual(len(highs), 1, f"esperado 1 HIGH, obtido {len(highs)}")
        self.assertEqual(highs[0].invariant, "check_layer_multiple")


class DeviceCapTests(unittest.TestCase):
    def test_over_cap_speed_is_high(self):
        """(c) inner_wall_speed=999 em k2 (cap extrusão 600) → HIGH."""
        item = _valid_item()
        item.profile["inner_wall_speed"] = "999"
        violations = validate_mod.check_device_caps(item)
        highs = [v for v in violations if v.severity == "high"]
        self.assertTrue(highs, "esperava HIGH por ultrapassar o cap de extrusão")
        self.assertTrue(
            any("inner_wall_speed" in v.detail for v in highs),
            "a violação deve citar inner_wall_speed",
        )

    def test_within_cap_passes(self):
        item = _valid_item()
        # Standard 0.20 PLA já respeita todos os caps do k2.
        self.assertEqual(validate_mod.check_device_caps(item), [])


class CombinationsTests(unittest.TestCase):
    def test_count_mismatch_is_high(self):
        """(e) len(profiles) diferente do total derivado → HIGH."""
        source_defs = {
            "default_devices": ["k2"],
            "combinations": [{
                "profile_type": "standard",
                "layer_heights": ["0.20"],
                "materials": ["PLA", "PETG"],
                "devices": ["k2"],
            }],
        }
        # total derivado = 1 lh × 2 mats × 1 dev = 2; passamos lista vazia.
        violations = validate_mod.check_combinations([], source_defs)
        highs = [v for v in violations if v.severity == "high"]
        self.assertTrue(
            any(v.invariant == "check_combinations" and "contagem" in v.detail
                for v in highs),
            "esperava HIGH de contagem divergente",
        )

    def test_expected_count_derived_from_real_combinations(self):
        """O total derivado da combinations.json real é o contrato atual (47)."""
        combos = _load_combinations()
        self.assertEqual(validate_mod.expected_profile_count(combos), 47)

    def test_missing_device_file_is_high(self):
        source_defs = {
            "default_devices": ["k2"],
            "combinations": [{
                "profile_type": "standard",
                "layer_heights": ["0.20"],
                "materials": ["PLA"],
                "devices": ["nao_existe"],
            }],
        }
        # 1 perfil derivado; passamos 1 perfil fake p/ não disparar contagem.
        fake = _valid_item()
        violations = validate_mod.check_combinations([fake], source_defs)
        self.assertTrue(
            any("nao_existe" in str(v.got) for v in violations
                if v.severity == "high"),
            "esperava HIGH por device sem arquivo",
        )


class _BuildDBMixin:
    """Build real (--only-db) em DB temporário (validação ON por default)."""

    @classmethod
    def _build_db(cls, extra_args=()):
        import tempfile
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmp.name) / "filament.db"
        env = dict(os.environ)
        env["DB_PATH"] = str(cls.db_path)
        py = ROOT / ".venv" / "bin" / "python"
        python = str(py) if py.exists() else sys.executable
        cls.result = subprocess.run(
            [python, "build.py", "--only-db", *extra_args],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300,
        )


class BuildIntegrationTests(_BuildDBMixin, unittest.TestCase):
    """(d) build.py --only-db com validação ON sobre a process-base atual → 0."""

    @classmethod
    def setUpClass(cls):
        cls._build_db()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_build_with_validation_exits_zero(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"build.py --only-db (validação ON) falhou:\n{self.result.stderr[-3000:]}",
        )

    def test_validation_ran(self):
        self.assertIn("Validando invariantes", self.result.stdout)
        self.assertIn("0 violação(ões) ALTA", self.result.stdout)

    def test_no_high_violation_logged(self):
        self.assertNotIn("[ALTA]", self.result.stdout)
        self.assertNotIn("[ALTA]", self.result.stderr)


class NoValidateFlagTests(_BuildDBMixin, unittest.TestCase):
    """--no-validate pula a validação e ainda sai 0."""

    @classmethod
    def setUpClass(cls):
        cls._build_db(extra_args=("--no-validate",))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_no_validate_skips_validation(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        self.assertNotIn("Validando invariantes", self.result.stdout)


if __name__ == "__main__":
    unittest.main()
