from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from advancore.services.fuel_market_sources import (
    FuelSourceError,
    _shell_download_url,
    parse_shell_workbook,
    parse_spc_page,
)


def _workbook(product: str = "Shell FuelSave Diesel") -> bytes:
    shared = ["Listed Pump Price", product, "3.950"]
    shared_xml = (
        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{value}</t></si>" for value in shared)
        + "</sst>"
    )
    sheet_xml = """<?xml version="1.0"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="B1" t="s"><v>0</v></c></row>
        <row r="5"><c r="A5" t="s"><v>1</v></c><c r="B5" t="s"><v>2</v></c></row>
      </sheetData>
    </worksheet>"""
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def test_strict_parsers_read_only_gross_diesel_and_source_timestamp():
    spc = parse_spc_page(
        '<img src="home-diesel.png"><span data-price="3.890">0.00</span>'
        '<div>Last updated on 07 Jul 2026 at 1740hrs. Prices shown are in Singapore Dollar</div>'
    )
    shell = parse_shell_workbook(_workbook(), "09 August 2026, 2215hrs")
    assert str(spc.price_per_litre) == "3.8900"
    assert str(shell.price_per_litre) == "3.9500"
    assert spc.source_updated_at == "07 Jul 2026 at 1740hrs"


def test_shell_model_accepts_only_one_official_https_workbook():
    payload = json.dumps({
        "text": "updated as of <b>09 August 2026, 2215hrs</b>",
        "links": ["https://www.shell.com.sg/approved/fuel.xlsx"],
    })
    assert _shell_download_url(payload) == (
        "https://www.shell.com.sg/approved/fuel.xlsx",
        "09 August 2026, 2215hrs",
    )
    unsafe = payload.replace("www.shell.com.sg", "example.invalid")
    with pytest.raises(FuelSourceError, match="outside the approved source"):
        _shell_download_url(unsafe)


def test_changed_source_formats_fail_closed_without_a_figure():
    with pytest.raises(FuelSourceError, match="verifiable diesel"):
        parse_spc_page("<html>no price</html>")
    with pytest.raises(FuelSourceError, match="gross FuelSave Diesel"):
        parse_shell_workbook(_workbook("Other Fuel Product"), "date")
