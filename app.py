import ipaddress
import json
import re
import socket
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QRPriceFinder/1.0; +https://example.com)",
    "Accept": "text/html,application/xhtml+xml"
}
TIMEOUT = 12
MAX_HTML = 2_000_000

def public_http_url(url):
    """Allow only public HTTP(S) destinations; reject local/private network targets."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return False
        host = p.hostname.lower()
        if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            addresses = {x[4][0] for x in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))}
        except socket.gaierror:
            return False
        for addr in addresses:
            ip = ipaddress.ip_address(addr.split("%")[0])
            if not ip.is_global:
                return False
        return True
    except Exception:
        return False

def safe_fetch(url):
    current = url
    for _ in range(4):
        if not public_http_url(current):
            raise ValueError("ئەم لینکە پارێزراو نییە یان دەستڕاگەیشتن پێی نییە.")
        response = requests.get(
            current, headers=HEADERS, timeout=TIMEOUT,
            allow_redirects=False, stream=True
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("لینکەکە بەردەست نییە.")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type and "xhtml" not in content_type:
            response.close()
            raise ValueError("ئەم لینکە پەڕەی HTML نییە.")
        chunks, total = [], 0
        for chunk in response.iter_content(16384):
            total += len(chunk)
            if total > MAX_HTML:
                break
            chunks.append(chunk)
        response.close()
        return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"), current
    raise ValueError("ژمارەی گواستنەوەی لینک زۆرە.")

def clean_price(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    value = str(value).strip()
    return value[:100] if value else None

def inspect_jsonld(node, found):
    if isinstance(node, list):
        for item in node:
            inspect_jsonld(item, found)
    elif isinstance(node, dict):
        typ = node.get("@type", [])
        if isinstance(typ, str):
            typ = [typ]
        if any("Product" in str(t) for t in typ):
            name = node.get("name")
            offers = node.get("offers")
            offers_list = offers if isinstance(offers, list) else [offers]
            for offer in offers_list:
                if isinstance(offer, dict):
                    price = offer.get("price")
                    currency = offer.get("priceCurrency")
                    if price is None and isinstance(offer.get("priceSpecification"), dict):
                        spec = offer["priceSpecification"]
                        price, currency = spec.get("price"), spec.get("priceCurrency")
                    if price is not None:
                        found.append({
                            "name": str(name)[:200] if name else None,
                            "price": clean_price(price),
                            "currency": str(currency)[:12] if currency else None
                        })
        for value in node.values():
            if isinstance(value, (dict, list)):
                inspect_jsonld(value, found)

def extract_product(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    found = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        try:
            inspect_jsonld(json.loads(raw), found)
        except Exception:
            pass

    if found:
        # Prefer first structured product offer; pages may list several variants.
        item = found[0]
        return {
            "name": item.get("name") or title,
            "price": item.get("price"),
            "currency": item.get("currency"),
            "method": "Product structured data (JSON-LD)",
            "page_title": title,
            "url": page_url
        }

    def meta(*selectors):
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                val = tag.get("content") or tag.get_text(" ", strip=True)
                if val:
                    return val.strip()[:200]
        return None

    name = meta('meta[property="og:title"]', 'meta[name="twitter:title"]') or title
    price = meta(
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
        '[itemprop="price"]'
    )
    currency = meta(
        'meta[property="product:price:currency"]',
        'meta[property="og:price:currency"]',
        'meta[itemprop="priceCurrency"]'
    )
    if price:
        return {
            "name": name, "price": price, "currency": currency,
            "method": "Price metadata", "page_title": title, "url": page_url
        }

    return {
        "name": name, "price": None, "currency": None,
        "method": "No machine-readable price found",
        "page_title": title, "url": page_url
    }

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/api/scan")
def scan():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if len(url) > 2048 or not public_http_url(url):
        return jsonify(error="لینکەکە نادروستە یان پارێزراو نییە."), 400
    try:
        html, final_url = safe_fetch(url)
        result = extract_product(html, final_url)
        return jsonify(result)
    except requests.RequestException:
        return jsonify(error="ماڵپەڕەکە وەڵامی نەدایەوە یان ڕێگری لە داواکاری کرد."), 502
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("Unexpected scan error")
        return jsonify(error="هەڵەیەکی نەزانراو ڕوویدا."), 500

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port= int(__import__("os").environ.get("PORT", 5000)))
