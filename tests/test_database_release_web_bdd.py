import unittest
from unittest.mock import patch

import tools.database_release_web as database_release_web


class DatabaseReleaseWebBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database_release_web.app.config.update(TESTING=True)
        cls.client = database_release_web.app.test_client()

    def _csrf_token(self):
        response = self.client.get("/api/csrf")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def test_console_exposes_only_full_migration_mode(self):
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "full_and_diff_migration")
        self.assertNotIn("packages", payload)

    def test_release_requires_csrf(self):
        response = self.client.post("/api/release", json={"target": "staging"})
        self.assertEqual(response.status_code, 403)

    def test_release_passes_full_migration_contract_to_service(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_database_release",
            return_value={"id": "full_1", "status": "queued", "target": "staging"},
        ) as start_release:
            response = self.client.post(
                "/api/release",
                json={"target": "staging", "package_id": "__full__"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_release.assert_called_once_with("staging", package_id="__full__", confirm_production=False)

    def test_production_release_requires_explicit_confirmation(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_database_release",
            side_effect=ValueError("production_confirmation_required"),
        ):
            response = self.client.post(
                "/api/release",
                json={"target": "production", "package_id": "__full__", "confirm_production": False},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "production_confirmation_required")

    def test_incremental_and_simulation_endpoints_are_not_exposed(self):
        for path in ("/api/packages", "/api/incremental", "/api/simulations", "/api/production-to-staging-sync"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_diff_scan_is_read_only_and_exposed_on_5051(self):
        with patch.object(
            database_release_web,
            "scan_database_release_delta",
            return_value={"target": "staging", "summary": {"data_difference_tables": 2}},
        ) as scan:
            response = self.client.get("/api/diff/scan?target=staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["scan"]["target"], "staging")
        scan.assert_called_once_with("staging")

    def test_diff_generation_and_release_require_csrf_and_reviewed_plan(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "generate_database_release_delta",
            return_value={
                "target": "staging",
                "report_path": ".deploy/diff.json",
                "diff_fingerprint": "fingerprint",
                "generated_packages": [{"id": "database_release_packages/2026-09-15/v1.0.0"}],
                "blockers": [],
            },
        ) as generate:
            response = self.client.post(
                "/api/diff/generate",
                json={"target": "staging", "include_schema": True, "include_master_data": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 201)
        generate.assert_called_once_with("staging", include_schema=True, include_master_data=True, include_runtime_data=False)

        with patch.object(
            database_release_web,
            "start_database_release_delta",
            return_value={"id": "delta_1", "status": "queued", "target": "staging"},
        ) as start_delta:
            response = self.client.post(
                "/api/diff/release",
                json={
                    "target": "staging",
                    "report_path": ".deploy/diff.json",
                    "diff_fingerprint": "fingerprint",
                    "package_ids": ["database_release_packages/2026-09-15/v1.0.0"],
                },
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_delta.assert_called_once_with(
            "staging", ".deploy/diff.json", "fingerprint", ["database_release_packages/2026-09-15/v1.0.0"], confirm_production=False,
        )


if __name__ == "__main__":
    unittest.main()
