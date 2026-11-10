"""Runs against a temp copy of a real project's HMI folder. Skipped when it is not on this machine."""
import hashlib
import os
import shutil
import tempfile
import unittest

from visuscaler import runner
from visuscaler.settings import Settings

REAL = r"C:\Projects\Customers\nVenia\SAL18_411f_110215\Logical\HMIControl"
PADS = ["AlphaPadQVGA", "AlphaPadQVGA1"]


def tree_hash(root):
    h = hashlib.md5()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            h.update(os.path.relpath(os.path.join(d, f), root).encode())
            with open(os.path.join(d, f), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


@unittest.skipUnless(os.path.isdir(os.path.join(REAL, "HMI")), "real project not available")
class RealProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pkg = os.path.join(self.tmp, "HMIControl")
        shutil.copytree(os.path.join(REAL, "HMI"), os.path.join(self.pkg, "HMI"))
        self.s = Settings(package_dir=self.pkg, source="HMI", dest="Visu", factor_x=2.0, factor_y=2.0, exclude_touchpads=PADS,
                          report_dir=os.path.join(self.tmp, "reports"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_steps(self, ids=None, **kw):
        return runner.run(self.s, ids, log=lambda m: None, **kw)

    def test_source_untouched_and_no_mismatches(self):
        before = tree_hash(os.path.join(self.pkg, "HMI"))
        ctx = self.run_steps()
        self.assertEqual(before, tree_hash(os.path.join(self.pkg, "HMI")))
        self.assertFalse([n for n in ctx.notes if n.step == "verify"], [n.text for n in ctx.notes if n.step == "verify"])
        self.assertTrue(os.path.isfile(ctx.report_path))

    def test_rerun_is_idempotent(self):
        self.run_steps()
        first = tree_hash(os.path.join(self.pkg, "Visu"))
        self.run_steps()
        self.assertEqual(first, tree_hash(os.path.join(self.pkg, "Visu")))

    def test_dry_run_changes_nothing(self):
        self.run_steps(dry_run=True)
        self.assertFalse(os.path.exists(os.path.join(self.pkg, "Visu")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "reports")))

    def test_steps_run_separately(self):
        self.run_steps(["copy"])
        self.run_steps(["geometry"])
        self.run_steps(["fonts"])
        self.run_steps(["bitmaps"])
        self.run_steps(["project", "verify"])
        together = tree_hash(os.path.join(self.pkg, "Visu"))
        shutil.rmtree(os.path.join(self.pkg, "Visu"))
        self.run_steps()
        self.assertEqual(together, tree_hash(os.path.join(self.pkg, "Visu")))

    def test_excluded_pads_and_bitmaps_unchanged(self):
        self.run_steps()
        for rel in ("TouchPads/AlphaPadQVGA.tpr", "BitmapGroups/AlphaPadQVGA.bmgrp",
                    "Bitmaps/zuneAlphaPadQVGA1_released.bminfo"):
            with open(os.path.join(self.pkg, "HMI", rel), "rb") as a, open(os.path.join(self.pkg, "Visu", rel), "rb") as b:
                self.assertEqual(a.read(), b.read(), rel)

    def test_create_missing_fonts_leaves_no_gaps(self):
        self.s.font_create_missing = True
        ctx = self.run_steps()
        self.assertFalse([n for n in ctx.notes if n.step == "fonts" and "No font of the exact" in n.text])
        self.assertTrue(os.path.isfile(os.path.join(self.pkg, "Visu", "Fonts", "Arial20px.fninfo")))
        with open(os.path.join(self.pkg, "Visu", "Package.vcp"), encoding="utf-8") as f:
            vcp = f.read()
        self.assertIn("Fonts\Arial20px.fninfo", vcp)


    def test_separate_x_and_y(self):
        self.s.factor_x, self.s.factor_y = 2.5, 2.0
        ctx = self.run_steps(["copy", "geometry", "project", "verify"])
        self.assertFalse([n for n in ctx.notes if n.step == "verify"])
        self.assertEqual(ctx.dest_resolution, (800, 480))
        with open(os.path.join(self.pkg, "Visu", "VCObject.vc"), encoding="utf-8") as f:
            vc = f.read()
        self.assertIn('Value="800"', vc)
        self.assertIn('Value="480"', vc)

    def test_line_end_points_are_scaled(self):
        """The sample project has no Line controls, so one is added to a page."""
        import re
        page = os.path.join(self.pkg, "HMI", "Pages", "LineTest.page")
        with open(page, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(['<Control ClassId="0x0000100D" Name="Line_1">',
                               '  <Property Name="EndX" Value="110"/>',
                               '  <Property Name="EndY" Value="359"/>',
                               '  <Property Name="StartX" Value="540"/>',
                               '  <Property Name="StartY" Value="100"/>',
                               '</Control>', '']))
        self.s.factor_x, self.s.factor_y = 2.0, 3.0
        ctx = self.run_steps(["copy", "geometry", "verify"])
        with open(os.path.join(self.pkg, "Visu", "Pages", "LineTest.page"), encoding="utf-8") as f:
            got = dict(re.findall(r'Name="(\w+)" Value="(-?\d+)"', f.read()))
        self.assertEqual(got, {"EndX": "220", "EndY": "1077", "StartX": "1080", "StartY": "300"})
        self.assertFalse([n for n in ctx.notes if n.step == "verify"])

    def test_bitmaps_use_whole_factor_when_asked(self):
        from PIL import Image
        name = "sign_outofspecification.gif"
        with Image.open(os.path.join(self.pkg, "HMI", "Bitmaps", name)) as im:
            w, h = im.size
        self.s.factor_x = self.s.factor_y = 2.25
        self.s.bitmap_integer_scale = True
        ctx = self.run_steps(["copy", "geometry", "bitmaps"])
        with Image.open(os.path.join(self.pkg, "Visu", "Bitmaps", name)) as im:
            self.assertEqual(im.size, (2 * w, 2 * h))
        self.assertTrue([n for n in ctx.notes if n.step == "bitmaps" and "whole part" in n.text])
        self.s.bitmap_integer_scale = False
        ctx = self.run_steps(["copy", "geometry", "bitmaps"])
        with Image.open(os.path.join(self.pkg, "Visu", "Bitmaps", name)) as im:
            self.assertEqual(im.size, (round(2.25 * w), round(2.25 * h)))
        self.assertTrue([n for n in ctx.notes if n.step == "bitmaps" and "not a whole number" in n.text])

    def test_non_whole_result_is_warned(self):
        self.s.factor_x = self.s.factor_y = 2.33
        ctx = self.run_steps(["copy", "geometry", "project"])
        texts = " ".join(n.text for n in ctx.notes)
        self.assertIn("not a whole number", texts)
        self.assertIn("did not scale to a whole pixel", texts)

    def _project_around_package(self):
        """Wrap the package in a minimal AS project so Package.pkg and Cpu.sw can be registered."""
        root = os.path.join(self.tmp, "proj")
        pkg = os.path.join(root, "Logical", "HMIControl")
        os.makedirs(os.path.dirname(pkg))
        shutil.move(self.pkg, pkg)
        self.pkg = self.s.package_dir = pkg
        open(os.path.join(root, "p.apj"), "w").close()
        with open(os.path.join(pkg, "Package.pkg"), "w", encoding="utf-8", newline="") as f:
            f.write('<Objects>\r\n    <Object Type="DataObject" Language="Vc">HMI</Object>\r\n</Objects>')
        sw = os.path.join(root, "Physical", "Cfg", "PLC1")
        os.makedirs(sw)
        self.cpu = os.path.join(sw, "Cpu.sw")
        with open(self.cpu, "w", encoding="utf-8", newline="") as f:
            f.write('<VcDataObjects>\r\n    <VcDataObject Name="HMI" Source="HMIControl.HMI.dob" '
                    'Memory="UserROM" Language="Vc" WarningLevel="2" />\r\n</VcDataObjects>')

    def test_target_size_creates_destination_and_registers_package(self):
        self._project_around_package()
        self.s.factor_x = self.s.factor_y = 1.0
        self.s.target_width, self.s.target_height = 800, 480
        ctx = self.run_steps()
        self.assertEqual(ctx.dest_resolution, (800, 480))
        self.assertFalse([n for n in ctx.notes if n.step == "verify"])
        with open(os.path.join(self.pkg, "Visu", "VCObject.vc"), encoding="utf-8") as f:
            vc = f.read()
        self.assertIn('Visualization Name="Visu"', vc)
        self.assertIn('Name="Width" Value="800"', vc)
        self.assertIn('Name="Height" Value="480"', vc)
        with open(os.path.join(self.pkg, "Package.pkg"), encoding="utf-8", newline="") as f:
            self.assertIn('Description="800x480">Visu</Object>', f.read())
        with open(self.cpu, encoding="utf-8", newline="") as f:
            self.assertNotIn("Visu", f.read())   # Physical is reported, never edited
        self.assertTrue([n for n in ctx.notes if n.level == "action" and "Cpu.sw" in n.text])
        before = (open(self.cpu, newline="").read(), open(os.path.join(self.pkg, "Package.pkg"), newline="").read())
        self.run_steps()   # second run must not register twice
        self.assertEqual(before, (open(self.cpu, newline="").read(), open(os.path.join(self.pkg, "Package.pkg"), newline="").read()))

    def test_destination_is_mapped_to_data_sources(self):
        self._project_around_package()
        ds = os.path.join(os.path.dirname(self.pkg), "VCShared", "DataSources")
        os.makedirs(ds)
        path = os.path.join(ds, "Internal.dso")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write('<P Name="ConnectingVisus" Value="HMIControl\\HMI"/><P Name="ConnectingVisus" Value=""/>')
        self.run_steps(["copy", "project"])
        with open(path, encoding="utf-8", newline="") as f:
            first = f.read()
        self.assertEqual(first, '<P Name="ConnectingVisus" Value="HMIControl\\HMI,HMIControl\\Visu"/>'
                                '<P Name="ConnectingVisus" Value=""/>')
        self.run_steps(["project"])
        with open(path, encoding="utf-8", newline="") as f:
            self.assertEqual(first, f.read())

    def test_dry_run_does_not_register(self):
        self._project_around_package()
        before = open(self.cpu, newline="").read()
        self.run_steps(dry_run=True)
        self.assertEqual(before, open(self.cpu, newline="").read())
        self.assertNotIn("Visu", open(os.path.join(self.pkg, "Package.pkg")).read())

    def test_register_can_be_turned_off(self):
        self._project_around_package()
        self.s.register_dest = False
        ctx = self.run_steps()
        self.assertNotIn("Visu", open(os.path.join(self.pkg, "Package.pkg")).read())
        self.assertTrue([n for n in ctx.notes if n.level == "action" and "not listed" in n.text])

    def test_target_needs_both_sides(self):
        self.s.target_width = 800
        with self.assertRaises(Exception):
            self.run_steps()


if __name__ == "__main__":
    unittest.main()
