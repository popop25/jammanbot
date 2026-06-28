from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from jammanbot.link_summary import LinkFetchError, _is_text_content, _validate_public_url, fetch_link_content


class LinkSummaryTests(unittest.TestCase):
    def test_rejects_non_http_urls(self) -> None:
        with self.assertRaises(LinkFetchError):
            _validate_public_url("file:///etc/passwd", allow_private_hosts=False)

    def test_rejects_localhost_by_default(self) -> None:
        with self.assertRaises(LinkFetchError):
            _validate_public_url("http://localhost:8000", allow_private_hosts=False)

    def test_rejects_private_ip_by_default(self) -> None:
        with self.assertRaises(LinkFetchError):
            _validate_public_url("http://10.0.0.1", allow_private_hosts=False)

    def test_allows_private_ip_when_explicitly_enabled(self) -> None:
        url = _validate_public_url("http://10.0.0.1", allow_private_hosts=True)

        self.assertEqual(url, "http://10.0.0.1")

    def test_text_content_detection(self) -> None:
        self.assertTrue(_is_text_content("text/plain; charset=utf-8"))
        self.assertTrue(_is_text_content("application/json"))
        self.assertFalse(_is_text_content("application/pdf"))

    def test_fetch_link_content_extracts_html_text(self) -> None:
        url = "http://93.184.216.34"
        response = httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", url),
        )
        body = b"""
        <html>
          <head><title>Example Title</title></head>
          <body>
            <script>ignore()</script>
            <h1>Main Heading</h1>
            <p>This paragraph is long enough to be included in the extracted body.</p>
          </body>
        </html>
        """

        with patch("jammanbot.link_summary._get_with_redirects", return_value=(response, body)):
            content = fetch_link_content(url)

        self.assertEqual(content.title, "Example Title")
        self.assertIn("This paragraph is long enough", content.text)
        self.assertNotIn("ignore", content.text)


if __name__ == "__main__":
    unittest.main()
