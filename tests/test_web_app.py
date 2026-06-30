from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from jammanbot.web_app import create_app


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_cafeteria_options_include_bundang_biwon(self) -> None:
        response = self.client.get("/api/cafeteria/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"]["BD"]["21"], "분당캠퍼스 비원")

    def test_default_roulette_candidates(self) -> None:
        response = self.client.get("/api/recommend/defaults")

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()["candidates"]), 0)


if __name__ == "__main__":
    unittest.main()
