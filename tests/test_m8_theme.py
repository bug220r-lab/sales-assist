"""Checks for shared presentation assets and readable local synthetic labels."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from synthetic_sales_assist.portal.assets import PORTAL_CSS
from synthetic_sales_assist.portal.dashboard_assets import DASHBOARD_CSS
from synthetic_sales_assist.portal.theme import (
    DISPLAY_TITLE,
    SYNTHETIC_COMPANION,
    THEME_CSS,
    THEME_TOKENS,
)


ROOT = Path(__file__).resolve().parents[1]


def luminance(color: str) -> float:
    rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
              for value in rgb]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))


class ThemeTests(unittest.TestCase):
    def test_shared_tokens_and_local_assets(self) -> None:
        self.assertEqual((ROOT / 'chrome_extension/shared/theme.css').read_bytes(),
                         THEME_CSS.encode('utf-8'))
        panel = (ROOT / 'chrome_extension/side_panel/panel.css').read_text('utf-8')
        for css in (PORTAL_CSS, DASHBOARD_CSS, THEME_CSS + panel):
            self.assertTrue(css.startswith(THEME_CSS))
            self.assertNotRegex(css, r'(?i)url\s*\(|@import|https?://')
            for token in re.findall(r'var\(--ssa-([a-z0-9-]+)\)', css):
                self.assertIn(token, THEME_TOKENS)
            self.assertIn('focus-visible', css)
            self.assertIn('var(--ssa-color-primary-hover)', css)
            self.assertIn('var(--ssa-disabled-opacity)', css)

    def test_principal_surfaces_keep_visible_synthetic_labels(self) -> None:
        for path in ('src/synthetic_sales_assist/portal/rendering.py',
                     'src/synthetic_sales_assist/portal/dashboard_rendering.py',
                     'chrome_extension/side_panel/index.html'):
            source = (ROOT / path).read_text('utf-8')
            self.assertIn(DISPLAY_TITLE, source)
            self.assertIn(SYNTHETIC_COMPANION + '</div>', source)
        panel = (ROOT / 'chrome_extension/side_panel/index.html').read_text('utf-8')
        self.assertIn('href="../shared/theme.css"', panel)
        self.assertNotIn('https://', panel)

    def test_text_and_focus_contrast(self) -> None:
        pairs = [('text', 'surface'), ('muted', 'background'), ('surface', 'header'),
                 ('surface', 'primary'), ('surface', 'primary-hover'),
                 ('surface', 'primary-active'), ('surface', 'secondary'),
                 ('success', 'success-surface'), ('warning', 'warning-surface'),
                 ('error', 'error-surface'), ('info', 'info-surface')]
        for foreground, background in pairs:
            with self.subTest(foreground=foreground, background=background):
                values = sorted(luminance(THEME_TOKENS['color-' + key])
                                for key in (foreground, background))
                self.assertGreaterEqual((values[1] + .05) / (values[0] + .05), 4.5)
        for background in ('surface', 'header', 'background'):
            values = sorted(luminance(THEME_TOKENS['color-' + key])
                            for key in ('focus', background))
            self.assertGreaterEqual((values[1] + .05) / (values[0] + .05), 3)


if __name__ == '__main__':
    unittest.main()
