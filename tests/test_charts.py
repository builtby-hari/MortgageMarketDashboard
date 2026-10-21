import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import charts  # noqa: E402
from mortgage_dashboard import parse_fred_csv, align, spread_stats, curve_spread, weekly_last  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
NAMES = {"spread", "rates", "curve", "spread-by-year", "spread-heatmap", "banner", "sample-output"}


def fx(name):
    with open(os.path.join(FIX, name + ".csv")) as fh:
        return parse_fred_csv(fh.read())


def fixture_inputs():
    d10, d2 = fx("DGS10"), fx("DGS2")
    rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), d10)
    return rows, spread_stats(rows), weekly_last(curve_spread(d10, d2))


class TestCharts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows, stats, curve = fixture_inputs()
        cls.rows, cls.stats, cls.curve = rows, stats, curve
        cls.rendered = charts.render_all(rows, stats, curve, ["$ python3 cli.py --offline", "one line"])

    def test_expected_graphics(self):
        self.assertEqual(set(self.rendered), NAMES)

    def test_every_svg_is_valid_xml_in_light_and_dark(self):
        for name, variants in self.rendered.items():
            for key in ("light", "dark"):
                root = ET.fromstring(variants[key])
                self.assertTrue(root.tag.endswith("svg"), name)

    def test_banner_is_1200_by_240(self):
        self.assertIn('viewBox="0 0 1200 240"', self.rendered["banner"]["light"])

    def test_dark_variant_uses_dark_palette(self):
        dark, light = self.rendered["spread"]["dark"], self.rendered["spread"]["light"]
        self.assertIn("#60a5fa", dark)
        self.assertNotIn("#60a5fa", light)
        self.assertIn("#1f3a5f", light)

    def test_write_all_creates_light_and_dark_files(self):
        out = tempfile.mkdtemp()
        try:
            paths = charts.write_all(self.rendered, out)
            self.assertEqual(len(paths), 2 * len(NAMES))
            for p in paths:
                self.assertTrue(os.path.getsize(p) > 0, p)
            self.assertTrue(os.path.exists(os.path.join(out, "spread-dark.svg")))
        finally:
            shutil.rmtree(out)

    def test_heatmap_with_no_data_still_renders(self):
        svg = charts._heatmap_chart(charts.THEMES["light"], "empty", [], {})
        ET.fromstring(svg)

    def test_curve_shading_only_when_inverted(self):
        svg = self.rendered["curve"]["light"]
        inverted = any(v < 0 for _, v in self.curve)
        self.assertEqual("<polygon" in svg, inverted)


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "matplotlib not installed")
class TestMatplotlibPlots(unittest.TestCase):
    def test_png_files_written(self):
        import plots_mpl
        rows, stats, curve = fixture_inputs()
        out = tempfile.mkdtemp()
        try:
            paths = plots_mpl.make_pngs(out, rows, stats, curve)
            self.assertEqual(len(paths), 5)
            for p in paths:
                with open(p, "rb") as fh:
                    self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n", p)
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
