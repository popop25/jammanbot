from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


URL_RE = re.compile(r"https?://[^\s<>\]]+")
MAX_REDIRECTS = 5
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


class LinkFetchError(RuntimeError):
    pass


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


def fetch_link_content(
    url: str,
    max_chars: int = 14000,
    *,
    allow_private_hosts: bool = False,
    max_bytes: int = 2_000_000,
) -> LinkContent:
    current_url = _validate_public_url(url, allow_private_hosts=allow_private_hosts)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; JammanBot/0.1; "
            "+https://github.com/jammanbot/jammanbot)"
        )
    }
    with httpx.Client(timeout=20.0, follow_redirects=False, headers=headers) as client:
        try:
            response, body_bytes = _get_with_redirects(
                client,
                current_url,
                allow_private_hosts=allow_private_hosts,
                max_bytes=max_bytes,
            )
        except httpx.HTTPError as exc:
            raise LinkFetchError(f"링크를 여는 중 HTTP 오류가 났어: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    text = _decode_body(body_bytes, response)
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        if not _is_text_content(content_type):
            raise LinkFetchError("HTML이나 텍스트 링크만 요약할 수 있어.")
        sample = text[:max_chars] if text else ""
        return LinkContent(url=str(response.url), title="", text=sample)

    soup = BeautifulSoup(text, "html.parser")
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


def _get_with_redirects(
    client: httpx.Client,
    url: str,
    *,
    allow_private_hosts: bool,
    max_bytes: int,
) -> tuple[httpx.Response, bytes]:
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        response = client.send(client.build_request("GET", current_url), stream=True)
        try:
            if response.is_redirect:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise LinkFetchError("리다이렉트 위치가 비어 있어.")
                current_url = _validate_public_url(
                    urljoin(current_url, location),
                    allow_private_hosts=allow_private_hosts,
                )
                continue

            response.raise_for_status()
            body = _read_limited(response, max_bytes=max_bytes)
            return response, body
        except Exception:
            response.close()
            raise

    raise LinkFetchError("리다이렉트가 너무 많아서 멈췄어.")


def _read_limited(response: httpx.Response, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = max(0, max_bytes)
    for chunk in response.iter_bytes():
        if not chunk or remaining <= 0:
            break
        chunks.append(chunk[:remaining])
        remaining -= len(chunks[-1])
    response.close()
    return b"".join(chunks)


def _decode_body(body: bytes, response: httpx.Response) -> str:
    encoding = response.encoding or "utf-8"
    return body.decode(encoding, errors="replace")


def _validate_public_url(url: str, *, allow_private_hosts: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise LinkFetchError("http/https 링크만 열 수 있어.")
    if not parsed.hostname:
        raise LinkFetchError("호스트가 없는 링크야.")
    if not allow_private_hosts and _is_private_or_local_host(parsed.hostname):
        raise LinkFetchError("localhost나 사설망으로 향하는 링크는 기본 차단돼 있어.")
    return url


def _is_private_or_local_host(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        return _is_blocked_ip(ipaddress.ip_address(host))
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise LinkFetchError(f"호스트를 찾지 못했어: {hostname}") from exc

    for info in infos:
        address = info[4][0]
        if _is_blocked_ip(ipaddress.ip_address(address)):
            return True
    return False


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not address.is_global


def _is_text_content(content_type: str) -> bool:
    normalized = content_type.lower()
    return normalized.startswith("text/") or any(
        marker in normalized
        for marker in [
            "application/json",
            "application/xml",
            "application/rss+xml",
            "application/atom+xml",
        ]
    )
