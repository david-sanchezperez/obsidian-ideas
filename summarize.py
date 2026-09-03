"""Extracción de contenido de URLs y resumen vía DeepSeek."""
import io
import os
import re
from urllib.parse import urlparse

import httpx
import trafilatura
from pypdf import PdfReader

from llm_json import parse_json_content
from notes import ALLOWED_TAGS

URL_RE = re.compile(r"https?://\S+")
HASHTAG_RE = re.compile(r"#(\w[\w-]*)")
X_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
TAG_RE = re.compile(r"<[^>]+>")

# Vía LiteLLM (puerta única de modelos, ver ~/litellm_config.yaml en la sobremesa)
# en vez de la API de DeepSeek directa — así comparte caché y tope de gasto con
# el resto de consumidores, y la key de DeepSeek solo vive en un sitio.
LITELLM_URL = os.environ.get("LITELLM_URL", "http://192.168.1.32:4000/v1/chat/completions")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "sk-litellm-local")


PROMPT = """Eres un asistente que resume noticias, artículos o ideas para un almacén \
personal de ideas en Obsidian. Te doy un texto (o una idea suelta). Elige entre 1 y 3 \
tags SOLO de esta lista cerrada (no inventes otros): {allowed_tags}

Devuelve SOLO un JSON con esta forma exacta, sin markdown ni explicación:
{{"title": "título corto", "summary": "resumen en 3-5 frases en castellano", \
"tags": ["tag-de-la-lista"]}}

Texto:
{text}
"""


def extract_manual_tags(message: str) -> list[str]:
    """Hashtags que el usuario escribe a mano en el mensaje, filtrados al vocabulario cerrado."""
    found = {m.lower() for m in HASHTAG_RE.findall(message)}
    return [t for t in ALLOWED_TAGS if t in found]


def extract_urls(message: str) -> list[str]:
    """Todas las URLs del mensaje, en orden y sin duplicados."""
    return list(dict.fromkeys(URL_RE.findall(message)))


def fetch_link_content(url: str) -> str | None:
    """Contenido en texto de un enlace: tuit, PDF o artículo web."""
    if urlparse(url).netloc in X_HOSTS:
        return fetch_tweet_text(url)
    data = fetch_url_bytes(url)
    if not data:
        return None
    if data[:4] == b"%PDF":
        return extract_pdf_text(data)
    return trafilatura.extract(data.decode("utf-8", "ignore"))


def fetch_tweet_text(url: str) -> str | None:
    """X no sirve HTML renderizado (contenido vía JS); usamos su oEmbed público."""
    resp = httpx.get(
        "https://publish.twitter.com/oembed",
        params={"url": url, "omit_script": "true"},
        timeout=15,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        return None
    html = resp.json().get("html", "")
    return TAG_RE.sub(" ", html).strip() or None


def fetch_url_bytes(url: str) -> bytes | None:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    return resp.content if resp.status_code == 200 else None


def summarize(text: str) -> dict:
    resp = httpx.post(
        LITELLM_URL,
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={
            "model": "deepseek-v4-flash",
            "messages": [{
                "role": "user",
                "content": PROMPT.format(allowed_tags=", ".join(ALLOWED_TAGS), text=text[:8000]),
            }],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    result = parse_json_content(content)
    result["tags"] = [t for t in result.get("tags", []) if t in ALLOWED_TAGS]
    return result


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def process_pdf(data: bytes, filename: str) -> dict:
    """Devuelve {"title", "summary", "tags", "source_url"} a partir de un PDF."""
    text = extract_pdf_text(data)
    if not text.strip():
        return {
            "title": filename,
            "summary": "No se pudo extraer texto de este PDF (¿es un escaneo sin OCR?).",
            "tags": [],
            "source_url": None,
        }
    result = summarize(text)
    result["source_url"] = None
    return result


def process_message(message: str) -> dict:
    """Devuelve {"title", "summary", "tags", "source_url"} listo para guardar.

    Si el mensaje trae varios enlaces (p.ej. una noticia que cita varias fuentes),
    se descarga el contenido de todos y se resume en conjunto.
    """
    manual_tags = extract_manual_tags(message)
    urls = extract_urls(message)
    if not urls:
        result = summarize(message)
        result["source_url"] = None
        result["tags"] = list(dict.fromkeys(result["tags"] + manual_tags))
        return result

    contents = [(u, fetch_link_content(u)) for u in urls]
    text = "\n\n".join(f"[{u}]\n{c}" for u, c in contents if c)

    if not text:
        return {
            "title": urls[0],
            "summary": "No se pudo extraer el contenido de este enlace automáticamente.",
            "tags": manual_tags,
            "source_url": urls[0],
        }
    result = summarize(text)
    result["source_url"] = urls[0]
    result["tags"] = list(dict.fromkeys(result["tags"] + manual_tags))
    return result
