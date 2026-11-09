"""Contrato de MVS (max_volumetric_speed) dos filamentos em filament-data/*.yaml.

O MVS é exclusivo do filamento. Política: menor valor entre fabricante, classe do
material (Orca mvs_default) e histórico de impressão. Valores acima da classe só
com fonte registrada (allowlist abaixo). Roda offline.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "filament-data"

# Perfis autorizados a ficar acima do teto da classe, com fonte em notes/recommendation.
PLA_ALLOWLIST = {"Sunlu PLA High Speed": 22, "Creality Hyper PLA": 20}
PETG_ABOVE_12 = {"Creality Hyper PETG": 14}


def _profiles():
    out = []
    for f in sorted(DATA.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for mat, block in (doc.get("materials") or {}).items():
            for p in (block or {}).get("profiles", []) or []:
                out.append((f.name, mat, p))
    return out


def _material(mat, p):
    return str(mat).upper()


class FilamentMVSContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = _profiles()

    def test_loaded_profiles(self):
        self.assertGreaterEqual(len(self.profiles), 100)

    def _mvs(self, p):
        return p.get("max_volumetric_speed")

    def test_mvs_is_positive_integer(self):
        # Export Orca faz int(mvs): fracionários seriam truncados.
        for fname, _line, p in self.profiles:
            mvs = self._mvs(p)
            self.assertIsInstance(mvs, int, f"{fname} {p.get('profile_name')}")
            self.assertGreater(mvs, 0)

    def test_voolt3d_petg_hf_is_11(self):
        # MVS ancorado no Creality CR PETG (11) — intermediário, abaixo do teto
        # de classe PETG (12). Revisão nov/2026 (ver filamentdb-rules.md).
        hf = [p for _f, _l, p in self.profiles if p.get("profile_name") == "Voolt3D PETG HF"]
        self.assertEqual(len(hf), 1)
        self.assertEqual(hf[0]["max_volumetric_speed"], 11)

    def test_petg_ceilings(self):
        for fname, line, p in self.profiles:
            if _material(line, p) != "PETG":
                continue
            name = p.get("profile_name")
            limit = PETG_ABOVE_12.get(name, 12)
            self.assertLessEqual(self._mvs(p), limit, f"{fname} {name}")

    def test_pla_ceilings_and_allowlist_has_source(self):
        for fname, line, p in self.profiles:
            if _material(line, p) != "PLA":
                continue
            name = p.get("profile_name")
            limit = PLA_ALLOWLIST.get(name, 18)
            self.assertLessEqual(self._mvs(p), limit, f"{fname} {name}")
        for name in PLA_ALLOWLIST:
            p = next(p for _f, _l, p in self.profiles if p.get("profile_name") == name)
            text = f"{p.get('notes', '')} {p.get('recommendation', '')}"
            self.assertIn("MVS", text, name)

    def test_other_class_ceilings(self):
        caps = {"TPU": 6, "ABS": 12, "ASA": 12, "PLA-CF": 12}
        for fname, line, p in self.profiles:
            mat = _material(line, p)
            if mat in caps:
                self.assertLessEqual(self._mvs(p), caps[mat], f"{fname} {p.get('profile_name')}")

    def test_sunlu_pla_hs_untouched(self):
        p = next(p for _f, _l, p in self.profiles if p.get("profile_name") == "Sunlu PLA High Speed")
        self.assertEqual(p["max_volumetric_speed"], 22)


if __name__ == "__main__":
    unittest.main()
