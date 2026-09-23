"""Regression coverage for moved views, imports and role boundaries."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

from backend.config import BASE_DIR
from backend.frontend_paths import ASSET_ROUTES, VIEW_ROUTES
import test_role_views


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "img"} and attrs.get("src"):
            self.urls.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.urls.append(attrs["href"])


class FrontendRoutesTests(unittest.TestCase):
    setUp = test_role_views.RoleViewTests.setUp
    tearDown = test_role_views.RoleViewTests.tearDown
    opener = test_role_views.RoleViewTests.opener
    get_json = test_role_views.RoleViewTests.get_json
    post_json = test_role_views.RoleViewTests.post_json
    login = test_role_views.RoleViewTests.login
    redirect_location = test_role_views.RoleViewTests.redirect_location

    def test_all_views_and_their_assets_still_load_by_role(self):
        guest, user, admin = self.opener(), self.opener(), self.opener()
        _, token = self.get_json(user, "/api/csrf")
        self.post_json(user, "/api/auth/register", {"display_name": "Cliente", "email": "cliente@example.com", "password": "ClienteSeguro123!"}, token["csrf_token"])
        self.login(admin, "admin@example.com", "AdminSeguro123!")
        for route in VIEW_ROUTES:
            opener = admin if route.startswith("/admin/") else user if route.startswith("/user/") else guest
            with self.subTest(route=route), opener.open(self.base + route) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.headers["Content-Type"])
                parser = References()
                parser.feed(response.read().decode())
            for ref in parser.urls:
                url = urljoin(self.base + route, ref)
                if urlsplit(url).netloc == urlsplit(self.base).netloc:
                    with self.subTest(asset=url), opener.open(url) as response:
                        self.assertEqual(response.status, 200)


    def test_physical_view_paths_cannot_bypass_role_checks(self):
        guest = self.opener()
        for file in VIEW_ROUTES.values():
            for path in ("/" + file, "/assets/../" + file):
                with self.subTest(path=path):
                    with self.assertRaises(HTTPError) as error:
                        guest.open(self.base + path)
                    self.assertEqual(error.exception.code, 404)
                    error.exception.close()
        for route in VIEW_ROUTES:
            if route.startswith(("/admin/", "/user/")):
                self.assertTrue(self.redirect_location(guest, route).startswith("/cuenta.html"))
