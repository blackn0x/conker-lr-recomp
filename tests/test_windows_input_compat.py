"""Synthetic generated-code fixtures; no game binary required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec = importlib.util.spec_from_file_location("compat", Path(__file__).parents[1] / "tools/windows_input_compat.py")
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

class CompatTests(unittest.TestCase):
    def fixture(self, root, corrected=True):
        (root / "recomp_funcs.h").write_text("void sub_0055BDF8(void);\n")
        (root / "recomp_a.c").write_text("void sub_0055BDF8(void)\n{\n}\n")
        lahf = "    SET_HI8(eax, g_fp_cmp); /* lahf */" if corrected else "    /* lahf */"
        (root / "recomp_b.c").write_text("void sub_003F57D0(void)\n{\n" + lahf + "\n}\nvoid sub_002B0CB0(void)\n{\n    SET_HI8(eax, g_fp_cmp); /* lahf */\n}\n")
    def test_only_graphics_site_changes_and_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            compat.patch(root)
            graphics = (root / "recomp_b.c").read_text()
            self.assertEqual(graphics.count(compat.TAG), 1)
            self.assertIn('strcmp(skip, "003F57D0")', graphics)
            self.assertIn("void sub_002B0CB0(void)\n{\n    SET_HI8(eax, g_fp_cmp); /* lahf */\n}", graphics)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            compat.patch(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertIn("sub_0055BDF8_gen", (root / "recomp_a.c").read_text())
    def test_unexpected_translation_fails_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root, corrected=False)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(ValueError): compat.patch(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

if __name__ == "__main__": unittest.main()
