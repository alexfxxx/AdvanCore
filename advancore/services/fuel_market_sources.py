"""Strict, bounded readers for the two owner-approved official diesel sources."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
import re
from urllib.parse import urlparse
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx


SHELL_PAGE_URL = "https://www.shell.com.sg/fuels-oils-and-coolants/shell-fuels/shell-station-price-board.model.json"
SPC_PAGE_URL = "https://www.spc.com.sg/"
MAX_SOURCE_BYTES = 2 * 1024 * 1024


class FuelSourceError(RuntimeError):
    def __init__(self, code: str, summary: str):
        super().__init__(summary)
        self.code = code


@dataclass(frozen=True)
class SourcePrice:
    provider: str
    price_per_litre: Decimal
    source_updated_at: str


@dataclass(frozen=True)
class CollectedFuelPrices:
    shell: SourcePrice
    spc: SourcePrice


def _positive_price(raw: str) -> Decimal:
    try:
        price = Decimal(raw.strip())
    except (InvalidOperation, ValueError) as exc:
        raise FuelSourceError("INVALID_PRICE", "A source returned an invalid diesel figure.") from exc
    if not price.is_finite() or price <= 0:
        raise FuelSourceError("INVALID_PRICE", "A source returned an invalid diesel figure.")
    return price.quantize(Decimal("0.0001"))


def parse_spc_page(html: str) -> SourcePrice:
    diesel = re.search(
        r"home-diesel[^>]*>.*?data-price=[\"']([0-9]+(?:\.[0-9]+)?)[\"']",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    updated = re.search(
        r"Last\s+updated\s+on\s+([^<]{1,80}?)\.\s*Prices\s+shown",
        html,
        flags=re.IGNORECASE,
    )
    if diesel is None or updated is None:
        raise FuelSourceError("SPC_FORMAT_CHANGED", "SPC did not expose a verifiable diesel figure and timestamp.")
    return SourcePrice("SPC", _positive_price(diesel.group(1)), updated.group(1).strip())


def _shell_download_url(model_payload: str) -> tuple[str, str]:
    try:
        document = json.loads(model_payload)
    except json.JSONDecodeError as exc:
        raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell returned an invalid price-board document.") from exc

    urls: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and value.lower().endswith(".xlsx"):
            urls.append(value)

    walk(document)
    updated = re.search(
        r"updated\s+as\s+of\s+(?:\\u003Cb\\u003E|<b>)([^<\\]{1,80})",
        model_payload,
        flags=re.IGNORECASE,
    )
    if len(urls) != 1 or updated is None:
        raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell did not expose one verifiable price workbook and timestamp.")
    parsed = urlparse(urls[0])
    if parsed.scheme != "https" or parsed.hostname != "www.shell.com.sg" or not parsed.path.endswith(".xlsx"):
        raise FuelSourceError("SHELL_UNTRUSTED_LINK", "Shell returned a price-workbook link outside the approved source.")
    return urls[0], updated.group(1).strip()


def parse_shell_workbook(content: bytes, source_updated_at: str) -> SourcePrice:
    try:
        with ZipFile(BytesIO(content)) as workbook:
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            sheet_root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell returned an unreadable price workbook.") from exc

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = [
        "".join(node.text or "" for node in item.findall(".//x:t", namespace))
        for item in shared_root.findall("x:si", namespace)
    ]
    cells: dict[str, str] = {}
    for cell in sheet_root.findall(".//x:c", namespace):
        reference = cell.attrib.get("r", "")
        value_node = cell.find("x:v", namespace)
        if not reference or value_node is None or value_node.text is None:
            continue
        value = value_node.text
        if cell.attrib.get("t") == "s":
            try:
                value = shared[int(value)]
            except (IndexError, ValueError) as exc:
                raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell returned an invalid shared workbook value.") from exc
        cells[reference] = value.strip()

    listed_column = next(
        (re.match(r"[A-Z]+", ref).group(0) for ref, value in cells.items() if value.lower() == "listed pump price"),
        None,
    )
    diesel_row = next(
        (re.search(r"\d+", ref).group(0) for ref, value in cells.items() if value.lower() == "shell fuelsave diesel"),
        None,
    )
    if listed_column is None or diesel_row is None:
        raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell workbook did not contain the gross FuelSave Diesel row.")
    raw_price = cells.get(f"{listed_column}{diesel_row}")
    if raw_price is None:
        raise FuelSourceError("SHELL_FORMAT_CHANGED", "Shell workbook omitted the listed diesel pump price.")
    return SourcePrice("Shell", _positive_price(raw_price), source_updated_at)


class OfficialFuelMarketCollector:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "AdvanCore/0.1 local-owner fuel benchmark"},
        )
        self._owns_client = client is None

    def _get_bounded(self, url: str, provider: str) -> tuple[bytes, str]:
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > MAX_SOURCE_BYTES:
                        raise FuelSourceError(
                            f"{provider.upper()}_TOO_LARGE",
                            f"{provider} price source exceeded the safe response size.",
                        )
                    chunks.append(chunk)
                return b"".join(chunks), str(response.url)
        except FuelSourceError:
            raise
        except httpx.HTTPError as exc:
            raise FuelSourceError(
                f"{provider.upper()}_UNAVAILABLE",
                f"{provider} price source was unavailable.",
            ) from exc

    def collect(self) -> CollectedFuelPrices:
        try:
            spc_content, spc_final_url = self._get_bounded(SPC_PAGE_URL, "SPC")
            if urlparse(spc_final_url).hostname not in {"spc.com.sg", "www.spc.com.sg"}:
                raise FuelSourceError("SPC_UNTRUSTED_REDIRECT", "SPC redirected outside the approved source.")
            spc = parse_spc_page(spc_content.decode("utf-8", errors="strict"))

            model_content, model_final_url = self._get_bounded(SHELL_PAGE_URL, "Shell")
            if urlparse(model_final_url).hostname != "www.shell.com.sg":
                raise FuelSourceError("SHELL_UNTRUSTED_REDIRECT", "Shell redirected outside the approved source.")
            workbook_url, updated = _shell_download_url(model_content.decode("utf-8", errors="strict"))
            workbook_content, workbook_final_url = self._get_bounded(workbook_url, "Shell")
            final_url = urlparse(workbook_final_url)
            if final_url.scheme != "https" or final_url.hostname != "www.shell.com.sg":
                raise FuelSourceError("SHELL_UNTRUSTED_REDIRECT", "Shell redirected outside the approved source.")
            shell = parse_shell_workbook(workbook_content, updated)
            return CollectedFuelPrices(shell=shell, spc=spc)
        except UnicodeDecodeError as exc:
            raise FuelSourceError("SOURCE_ENCODING", "A fuel source returned unreadable text.") from exc
        finally:
            if self._owns_client:
                self._client.close()
