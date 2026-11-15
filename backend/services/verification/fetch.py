"""Descarga de páginas y extracción de su texto (incremento 2, paso 3 del plan; defensas de 4.6).

Las páginas son datos no confiables y la dirección la decide un buscador, no el usuario, pero igual
se tratan como un ataque posible:

- Solo `http`/`https`, sin usuario ni contraseña en la URL y solo en los puertos 80 y 443.
- La dirección IP del servidor se resuelve aquí y debe ser pública: se rechazan las privadas,
  locales, de enlace local, reservadas y las de metadatos de la nube (169.254.169.254, por ejemplo).
  Se comprueba **en cada redirección**, y la conexión se hace a la IP ya validada (con el nombre
  original para el certificado), de modo que no se pueda cambiar la respuesta DNS entre la
  comprobación y la conexión.
- Las redirecciones se siguen a mano, con tope. Sin cookies, sin credenciales, sin proxys del
  entorno y con un agente de usuario genérico.
- Tope de bytes (ya descomprimidos, por si hay una bomba de compresión) y de tiempo total; solo se
  admiten HTML y texto plano.
- Del HTML se descartan los scripts, estilos, menús, contenido oculto y comentarios, y de todo el
  texto los caracteres invisibles con los que se pueden esconder órdenes al modelo.
"""

import codecs
import hashlib
import ipaddress
import logging
import re
import socket
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from backend.core.config import EvidenceLimits

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ScanTrueVerificador/1.0)"
ALLOWED_PORTS = (80, 443)
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
MAX_URL_CHARS = 2048
MAX_TEXT_CHARS = 150_000
MIN_LINE_WORDS = 5
NAT64 = ipaddress.ip_network("64:ff9b::/96")


class FetchError(RuntimeError):
    """La página no se pudo usar. `code` dice por qué; las fallas de una página no frenan la afirmación."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FetchedPage:
    url: str  # la URL final, tras las redirecciones
    titulo: str
    texto: str
    consultada_en: datetime
    sha256: str  # de los bytes leídos (para la evidencia congelada de la Fase 7)
    truncada: bool


def is_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Solo las direcciones de internet público; también las IPv4 escondidas dentro de una IPv6."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and ip.teredo is not None:
            embedded = ip.teredo[1]
        if embedded is None and ip in NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None and not is_public_address(embedded):
            return False
    return ip.is_global and not ip.is_multicast


def resolve_host(host: str, port: int) -> list[str]:
    """Direcciones IP del servidor, como texto (el resolvedor de la plataforma)."""
    found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(item[4][0] for item in found))


class PageFetcher:
    def __init__(
        self,
        limits: EvidenceLimits | None = None,
        *,
        resolver: Callable[[str, int], list[str]] = resolve_host,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits or EvidenceLimits()
        self._resolver = resolver
        self._transport = transport
        self._clock = clock

    def fetch(self, url: str) -> FetchedPage:
        deadline = self._clock() + self.limits.page_seconds
        current = url
        for _ in range(self.limits.max_redirects + 1):
            scheme, host, port, target = self._check_url(current)
            address = self._public_address(host, port)
            location = self._request_once(scheme, host, port, target, address, deadline, current)
            if isinstance(location, FetchedPage):
                return location
            current = location
        raise FetchError("Demasiadas redirecciones.", "demasiadas_redirecciones")

    # --- comprobaciones previas -------------------------------------------------------------

    @staticmethod
    def _check_url(url: str) -> tuple[str, str, int, str]:
        def reject(why: str) -> FetchError:
            return FetchError(f"URL no permitida: {why}.", "url_no_permitida")

        if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS:
            raise reject("vacía o demasiado larga")
        if any(ord(ch) <= 32 or ord(ch) == 127 for ch in url):
            raise reject("tiene espacios o caracteres de control")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise reject("no se puede interpretar") from None
        if parts.scheme not in ("http", "https"):
            raise reject("solo http y https")
        if "@" in parts.netloc:
            raise reject("lleva usuario o contraseña")
        if not parts.hostname:
            raise reject("sin servidor")
        port = port or (443 if parts.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise reject("solo los puertos 80 y 443")
        try:
            host = parts.hostname.encode("idna").decode("ascii")
        except UnicodeError:
            raise reject("nombre de servidor inválido") from None
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        return parts.scheme, host, port, target

    def _public_address(self, host: str, port: int) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            raw = self._resolver(host, port)
        except OSError:
            raise FetchError("No se pudo resolver el servidor.", "error_red") from None
        addresses = []
        for text in raw:
            try:
                addresses.append(ipaddress.ip_address(text.split("%", 1)[0]))
            except ValueError:
                continue
        if not addresses:
            raise FetchError("No se pudo resolver el servidor.", "error_red")
        # Basta una dirección no pública para rechazar: el servidor podría estar apuntando adentro.
        if not all(is_public_address(ip) for ip in addresses):
            raise FetchError("El servidor resuelve a una dirección no pública.", "direccion_no_permitida")
        return sorted(addresses, key=lambda ip: ip.version)[0]

    # --- una petición -----------------------------------------------------------------------

    def _request_once(
        self, scheme: str, host: str, port: int, target: str, address, deadline: float, current: str
    ) -> "FetchedPage | str":
        """La página, o la URL a la que redirige."""
        ip_text = f"[{address}]" if address.version == 6 else str(address)
        default_port = 443 if scheme == "https" else 80
        headers = {
            "Host": host if port == default_port else f"{host}:{port}",
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Language": "es,en;q=0.5",
        }
        extensions = {"sni_hostname": host} if scheme == "https" else {}
        timeout = min(self.limits.page_seconds, 10.0)
        # Un cliente por salto: el pozo de conexiones no se comparte entre servidores que
        # compartan IP, y las cookies no pasan de un salto a otro.
        client = httpx.Client(
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        )
        try:
            with client.stream(
                "GET", f"{scheme}://{ip_text}:{port}{target}", headers=headers, extensions=extensions
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "").strip()
                    if not location:
                        raise FetchError("Redirección sin destino.", "error_http")
                    return urljoin(current, location)
                if response.status_code != 200:
                    raise FetchError(f"HTTP {response.status_code}.", "error_http")
                content_type = response.headers.get("content-type", "")
                mime = content_type.split(";", 1)[0].strip().lower()
                if mime not in ALLOWED_TYPES:
                    raise FetchError(f"Tipo de contenido no admitido ({mime or 'ninguno'}).", "tipo_no_admitido")
                body, truncated = self._read_body(response, deadline)
        except FetchError:
            raise
        except httpx.TimeoutException:
            raise FetchError("La página no respondió a tiempo.", "tiempo_agotado") from None
        except (httpx.TransportError, httpx.InvalidURL, OSError):
            raise FetchError("No se pudo descargar la página.", "error_red") from None
        finally:
            client.close()
        text = _decode(body, content_type)
        title, plain = (("", text) if mime == "text/plain" else extract_text(text))
        return FetchedPage(
            url=current,
            titulo=title,
            texto=_clean_plain(plain) if mime == "text/plain" else plain,
            consultada_en=datetime.now(timezone.utc),
            sha256=hashlib.sha256(body).hexdigest(),
            truncada=truncated,
        )

    def _read_body(self, response: httpx.Response, deadline: float) -> tuple[bytes, bool]:
        limit = self.limits.page_bytes
        buffer = bytearray()
        for chunk in response.iter_bytes():
            buffer.extend(chunk)
            if len(buffer) >= limit:
                return bytes(buffer[:limit]), True
            if self._clock() > deadline:
                raise FetchError("La descarga tardó demasiado.", "tiempo_agotado")
        return bytes(buffer), False


# --- texto de la página -----------------------------------------------------------------------

_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([\w-]+)", re.IGNORECASE)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w-]+)", re.IGNORECASE)


def _decode(body: bytes, content_type: str) -> str:
    candidates = []
    if match := _HEADER_CHARSET.search(content_type):
        candidates.append(match.group(1))
    if match := _META_CHARSET.search(body[:4096]):
        candidates.append(match.group(1).decode("ascii", "ignore"))
    for name in candidates:
        try:
            return body.decode(codecs.lookup(name).name, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def _strip_invisible(text: str) -> str:
    """Quita los caracteres de formato (ancho cero, etiquetas Unicode, control bidireccional)."""
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co"))


def _clean_plain(text: str) -> str:
    lines = []
    for raw in _strip_invisible(text.replace("\r", "\n")).split("\n"):
        line = " ".join(raw.split())
        if len(line.split()) >= MIN_LINE_WORDS and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)[:MAX_TEXT_CHARS]


_SKIPPED = frozenset({
    "script", "style", "noscript", "template", "svg", "iframe", "canvas", "object", "embed",
    "nav", "footer", "aside", "form", "button", "select", "textarea", "dialog", "menu",
})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
_BLOCK = frozenset({
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
    "main", "blockquote", "pre", "table", "header", "figcaption", "dd", "dt", "hr",
})
_HIDDEN_STYLE = re.compile(
    r"display:none|visibility:hidden|font-size:0(?![.\d])|opacity:0(?![.\d])|text-indent:-\d{3,}"
)


def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
    values = {name: (value or "") for name, value in attrs}
    if "hidden" in values or values.get("aria-hidden", "").lower() == "true":
        return True
    return bool(_HIDDEN_STYLE.search("".join(values.get("style", "").lower().split())))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool, bool]] = []  # etiqueta, omitida, article, main
        self.skipped = self.in_article = self.in_main = 0
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta_title = ""
        self.all: list[str] = []
        self.article: list[str] = []
        self.main: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            values = {name: (value or "") for name, value in attrs}
            if values.get("property", "").lower() == "og:title" and not self.meta_title:
                self.meta_title = values.get("content", "")
            return
        if tag in _BLOCK:
            self._add("\n")
        if tag in _VOID:
            return
        skip = tag in _SKIPPED or _is_hidden(attrs)
        self.stack.append((tag, skip, tag == "article", tag == "main"))
        self.skipped += skip
        self.in_article += tag == "article"
        self.in_main += tag == "main"
        if tag == "title" and not self.skipped:
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in _VOID or not any(item[0] == tag for item in self.stack):
            return
        while self.stack:
            name, skip, article, main = self.stack.pop()
            self.skipped -= skip
            self.in_article -= article
            self.in_main -= main
            if name == "title":
                self.in_title = False
            if name == tag:
                break
        if tag in _BLOCK:
            self._add("\n")

    def handle_data(self, data):
        if self.skipped:
            return
        if self.in_title:
            self.title_parts.append(data)
        else:
            # Los saltos de línea del código fuente son espacios; solo las etiquetas de bloque cortan.
            self._add(re.sub(r"\s+", " ", data))

    def _add(self, text: str) -> None:
        if self.skipped or self.in_title:
            return
        self.all.append(text)
        if self.in_article:
            self.article.append(text)
        if self.in_main:
            self.main.append(text)


def extract_text(html: str) -> tuple[str, str]:
    """(título, texto) de una página HTML: el cuerpo principal si lo hay, sin lo accesorio ni oculto."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # HTML roto: se usa lo que alcanzó a leerse
        logger.debug("HTML mal formado; se usa el texto leído hasta ahí")
    buckets = ["".join(parser.article), "".join(parser.main), "".join(parser.all)]
    body = next((cleaned for text in buckets if len(cleaned := _clean_plain(text)) >= 400), _clean_plain(buckets[2]))
    title = " ".join(_strip_invisible("".join(parser.title_parts) or parser.meta_title).split())
    return title[:300], body
