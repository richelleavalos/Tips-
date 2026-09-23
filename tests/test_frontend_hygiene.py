"""Contratos para impedir que regresen capas visuales o scripts muertos."""

from pathlib import Path
import re
import unittest

from backend.config import BASE_DIR


class FrontendHygieneTests(unittest.TestCase):
    """Mantiene una única fuente visual por contexto de la aplicación."""

    def test_each_view_uses_only_its_canonical_stylesheet(self):
        groups = [
            (BASE_DIR / "frontend/usuario/vistas/publicas", "public.css"),
            (BASE_DIR / "frontend/usuario/vistas/cuenta", "account.css"),
            (BASE_DIR / "frontend/admin/vistas", "admin.css"),
        ]
        for folder, expected in groups:
            for path in folder.glob("*.html"):
                text = path.read_text(encoding="utf-8")
                styles = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', text)
                if path.name == "merchandise.html":
                    self.assertEqual(styles, [], path.name)
                    continue
                self.assertEqual(len(styles), 1, f"{path.name}: {styles}")
                self.assertIn(expected, styles[0], path.name)

    def test_removed_design_layers_do_not_return(self):
        dead = [
            "frontend/usuario/css/app.css",
            "frontend/usuario/css/editorial-v3.css",
            "frontend/usuario/css/client-v2.css",
            "frontend/usuario/css/ux.css",
            "frontend/usuario/css/estilos.css",
            "frontend/admin/css/admin-v3.css",
            "frontend/admin/css/admin-editorial.css",
            "frontend/admin/css/admin-fixes.css",
            "frontend/global/js/transitions.js",
            "frontend/global/js/scroll-reveal.js",
            "frontend/usuario/js/main.js",
            "frontend/usuario/js/profile-page.js",
            "frontend/admin/js/admin.js",
        ]
        for relative in dead:
            self.assertFalse((BASE_DIR / relative).exists(), relative)

    def test_canonical_css_has_no_import_chain(self):
        for relative in (
            "frontend/usuario/css/public.css",
            "frontend/usuario/css/account.css",
            "frontend/admin/css/admin.css",
        ):
            text = (BASE_DIR / relative).read_text(encoding="utf-8")
            self.assertNotIn("@import", text, relative)

    def test_views_do_not_load_duplicate_transition_runtime(self):
        for folder in (
            BASE_DIR / "frontend/usuario/vistas/publicas",
            BASE_DIR / "frontend/usuario/vistas/cuenta",
            BASE_DIR / "frontend/admin/vistas",
        ):
            for path in folder.glob("*.html"):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("transitions.js", text, path.name)
                self.assertLessEqual(text.count("motion-loader.js"), 1, path.name)

    def test_public_styles_do_not_contain_legacy_admin_or_profile_layouts(self):
        """Evita que estilos de roles distintos vuelvan a mezclarse en public.css."""
        text = (BASE_DIR / "frontend/usuario/css/public.css").read_text(encoding="utf-8")
        for dead_selector in (".admin-body", ".admin-shell", ".admin-sidebar", ".profile-page", ".profile-layout"):
            self.assertNotIn(dead_selector, text, dead_selector)

    def test_motion_runtime_never_transforms_body(self):
        """Los overlays fixed deben seguir anclados al viewport también en Safari."""
        text = (BASE_DIR / "frontend/global/css/motion.css").read_text(encoding="utf-8")
        body_rules = re.findall(r"body\.motion-page-(?:enter|exit)\s*\{([^}]+)\}", text)
        self.assertTrue(body_rules)
        for rule in body_rules:
            self.assertNotIn("transform", rule)
            self.assertNotIn("filter", rule)
            self.assertNotIn("clip-path", rule)

    def test_overlays_are_viewport_fixed_and_self_scrolling(self):
        public = (BASE_DIR / "frontend/usuario/css/public.css").read_text(encoding="utf-8")
        admin = (BASE_DIR / "frontend/admin/css/admin.css").read_text(encoding="utf-8")
        self.assertRegex(public, r"\.modal-backdrop[\s\S]*?position:\s*fixed\s*!important")
        self.assertRegex(public, r"\.cart-drawer[\s\S]*?height:\s*100dvh")
        self.assertRegex(admin, r"\.admin-modal-layer[\s\S]*?position:\s*fixed")
        self.assertIn("body.admin-overlay-open { overflow: hidden; }", admin)


if __name__ == "__main__":
    unittest.main()
