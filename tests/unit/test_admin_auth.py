#!/usr/bin/env python3
"""Unit tests for api/routes/admin.py login behaviour.

Covers A1 (brute-force throttle) and A3 (token rotation).

Login throttle contract:
  1. /admin/login accepts the configured token → 200 + cookie
  2. Wrong token → 401 (and counter increments)
  3. 5 failures from the same IP within 5 min → 6th attempt is 429
     regardless of the supplied token (lockout takes priority)
  4. 429 carries a ``Retry-After`` header
  5. A successful login clears the counter for that IP

Token rotation contract:
  1. Requires admin auth (401 anonymous)
  2. Returns a freshly-generated 256-bit hex token in the body, once
  3. Writes the new value to ``CONFIGURE_DIR/admin_token.txt``
  4. config.ADMIN_TOKEN reloads in-process so the old cookie
     immediately stops working
  5. The new token can be used to log in
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from fastapi.testclient import TestClient  # noqa: E402

from pmet_backend.api.main import app  # noqa: E402
from pmet_backend.config import config  # noqa: E402
from pmet_backend.api.routes import admin as admin_mod  # noqa: E402


FIXTURE_TOKEN = "test-admin-token-fixture-do-not-use-in-prod"


class AdminAuthBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_admin_auth_test_"))
        self.cfg_patch = patch.multiple(
            config,
            CONFIGURE_DIR=self.tmp,
            ADMIN_TOKEN=FIXTURE_TOKEN,
        )
        self.cfg_patch.start()
        # Seed the real token file so token rotation has something to
        # overwrite + config.reload reads back a sane state.
        (self.tmp / "admin_token.txt").write_text(FIXTURE_TOKEN + "\n")
        admin_mod._reset_login_state_for_tests()
        self.client = TestClient(app)

    def tearDown(self):
        self.cfg_patch.stop()
        admin_mod._reset_login_state_for_tests()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.client.close()


# ----------------------------------------------------------------------
# A1: brute-force throttle
# ----------------------------------------------------------------------
class BruteForceThrottleTests(AdminAuthBase):
    def test_valid_token_returns_200_with_cookie(self):
        r = self.client.post("/api/admin/login", json={"token": FIXTURE_TOKEN})
        self.assertEqual(r.status_code, 200)
        self.assertIn("pmet_admin", r.cookies)

    def test_wrong_token_returns_401(self):
        r = self.client.post("/api/admin/login", json={"token": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_429_after_five_failures(self):
        for i in range(5):
            r = self.client.post("/api/admin/login", json={"token": "wrong"})
            self.assertEqual(r.status_code, 401, f"attempt {i + 1} should be 401")
        # 6th attempt is the lockout.
        r = self.client.post("/api/admin/login", json={"token": "wrong"})
        self.assertEqual(r.status_code, 429)
        # Retry-After present so HTTP clients can backoff sanely.
        self.assertIn("retry-after", {k.lower() for k in r.headers.keys()})

    def test_429_blocks_even_correct_token_during_lockout(self):
        """A genuine attacker who eventually guesses the right value
        on attempt 6 shouldn't be admitted — the IP is locked first."""
        for _ in range(5):
            self.client.post("/api/admin/login", json={"token": "wrong"})
        r = self.client.post("/api/admin/login", json={"token": FIXTURE_TOKEN})
        self.assertEqual(r.status_code, 429)

    def test_successful_login_clears_failure_counter(self):
        # 4 wrong (one short of lockout), then 1 correct.
        for _ in range(4):
            self.client.post("/api/admin/login", json={"token": "wrong"})
        ok = self.client.post("/api/admin/login", json={"token": FIXTURE_TOKEN})
        self.assertEqual(ok.status_code, 200)
        # Counter should be cleared — we can fail 4 MORE times without
        # tripping the 429, then a 5th would.
        for _ in range(4):
            r = self.client.post("/api/admin/login", json={"token": "wrong"})
            self.assertEqual(r.status_code, 401)

    def test_503_when_admin_disabled(self):
        with patch.object(config, "ADMIN_TOKEN", ""):
            r = self.client.post("/api/admin/login", json={"token": "anything"})
        # 503 (admin disabled) — not 401, not 429.
        self.assertEqual(r.status_code, 503)


# ----------------------------------------------------------------------
# A3: token rotation
# ----------------------------------------------------------------------
class TokenRotationTests(AdminAuthBase):
    def _login(self):
        r = self.client.post("/api/admin/login", json={"token": FIXTURE_TOKEN})
        self.assertEqual(r.status_code, 200)

    def test_rotate_requires_admin(self):
        # No login → 401.
        r = self.client.post("/api/admin/rotate-token")
        self.assertEqual(r.status_code, 401)

    def test_rotate_returns_new_64char_hex_token(self):
        self._login()
        r = self.client.post("/api/admin/rotate-token")
        self.assertEqual(r.status_code, 200, r.text)
        new_token = r.json()["token"]
        self.assertEqual(len(new_token), 64)
        self.assertRegex(new_token, r"^[0-9a-f]{64}$")
        # Returned token differs from the fixture.
        self.assertNotEqual(new_token, FIXTURE_TOKEN)

    def test_rotate_writes_new_value_to_disk(self):
        self._login()
        r = self.client.post("/api/admin/rotate-token")
        new_token = r.json()["token"]
        on_disk = (self.tmp / "admin_token.txt").read_text().strip()
        self.assertEqual(on_disk, new_token)

    def test_rotate_invalidates_old_cookie(self):
        self._login()
        # Confirm the cookie works on a guarded endpoint first.
        r = self.client.get("/api/admin/settings")
        self.assertEqual(r.status_code, 200)
        # Rotate.
        self.client.post("/api/admin/rotate-token")
        # The cookie we still hold is the OLD token; it no longer
        # matches the freshly-rotated config.ADMIN_TOKEN.
        r = self.client.get("/api/admin/settings")
        self.assertEqual(r.status_code, 401)

    def test_can_log_in_with_new_token_after_rotation(self):
        self._login()
        new_token = self.client.post("/api/admin/rotate-token").json()["token"]
        # Throttle clears the failure counter on success above, so this
        # fresh login doesn't trip 429. Use a fresh client so we don't
        # carry the now-stale cookie.
        with TestClient(app) as fresh:
            r = fresh.post("/api/admin/login", json={"token": new_token})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
