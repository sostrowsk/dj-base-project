"""LUCIDE_ICONS_DIR setting behavior of base_project.templatetags.lucide_tags (W18-BP1)."""

import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from base_project.templatetags.lucide_tags import icon, lucide


class LucideIconsDirSettingTests(SimpleTestCase):
    def test_default_resolves_from_node_modules(self):
        assert (Path(settings.BASE_DIR) / "node_modules" / "lucide-static" / "icons" / "check.svg").exists()
        svg = lucide("check")
        assert "<svg" in svg

    def test_lucide_icons_dir_setting_is_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "custom-test-icon.svg").write_text('<svg data-custom="1"></svg>')
            with override_settings(LUCIDE_ICONS_DIR=tmp):
                svg = lucide("custom-test-icon")
        assert 'data-custom="1"' in svg

    def test_missing_icon_renders_placeholder_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(LUCIDE_ICONS_DIR=tmp):
                html = lucide("does-not-exist-xyz")
        assert "lucide-missing" in html

    def test_icon_tag_maps_font_awesome_names(self):
        svg = icon("xmark")  # FA name, maps to lucide "x"
        assert "<svg" in svg
