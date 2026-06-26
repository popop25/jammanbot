from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

import httpx
from bs4 import BeautifulSoup


URL_RE = re.compile(r"https?://[^\s<>\]]+")


@dataclass(frozen=True)
class LinkContent:
    url: str
    title: str
    text: str


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).strip("<>").rstrip(").,]")
        if "|" in url:
            url = url.split("|", 1)[0]
        if url not in urls:
            urls.append(url)
    return urls


def fetch_link_content(url: str, max_chars: int = 14000) -> LinkContent:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; JammanBot/0.1; "
            "+https://github.com/jammanbot/jammanbot)"
        )
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        sample = response.text[:max_chars] if response.text else ""
        return LinkContent(url=str(response.url), title="", text=sample)

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta_description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        meta_description = str(meta["content"]).strip()

    paragraphs: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = " ".join(element.get_text(" ", strip=True).split())
        if len(text) >= 20:
            paragraphs.append(text)
        if sum(len(item) for item in paragraphs) >= max_chars:
            break

    body = "\n".join(paragraphs)
    if meta_description:
        body = f"{meta_description}\n\n{body}"

    return LinkContent(
        url=str(response.url),
        title=unescape(title),
        text=unescape(body[:max_chars]),
    )

