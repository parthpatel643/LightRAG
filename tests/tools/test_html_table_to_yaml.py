"""HTML table → YAML conversion (scripts/html_table_to_yaml.py)."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "html_table_to_yaml.py"
_spec = importlib.util.spec_from_file_location("html_table_to_yaml", _SCRIPT)
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)


TOTAL_ROW_TABLE = """
<table>
  <thead>
    <tr><th scope="col">Aircraft</th><th scope="col">Service</th>
        <th scope="col">Price/event</th><th scope="col">Cost/Day</th>
        <th scope="col">Annual Cost</th></tr>
  </thead>
  <tbody>
    <tr><th scope="row">737</th><td>Turn</td><td>$ 50.00</td>
        <td>$ 100.00</td><td>$ 36,500.00</td></tr>
    <tr><th scope="row" colspan="3">Total</th><td>$ 100.00</td><td>$ 36,500.00</td></tr>
  </tbody>
</table>
"""

ROWSPAN_TABLE = """
<table>
  <thead>
    <tr><th scope="col">Aircraft</th><th scope="col">Service</th><th scope="col">Price</th></tr>
  </thead>
  <tbody>
    <tr><th scope="row" rowspan="2">Airbus</th><td>Turn</td><td>$ 27.92</td></tr>
    <tr><td>Ron</td><td>$ 132.37</td></tr>
  </tbody>
</table>
"""


def test_row_header_colspan_keeps_values_under_their_columns():
    headers, rows = converter.parse_html_table_to_rows(TOTAL_ROW_TABLE)
    total = dict(zip(headers, rows[1]))
    assert total["Aircraft"] == "Total"
    assert total["Price/event"] == "Total"
    assert total["Cost/Day"] == "$ 100.00"
    assert total["Annual Cost"] == "$ 36,500.00"


def test_rowspan_row_header_is_carried_to_following_rows():
    headers, rows = converter.parse_html_table_to_rows(ROWSPAN_TABLE)
    assert [dict(zip(headers, r)) for r in rows] == [
        {"Aircraft": "Airbus", "Service": "Turn", "Price": "$ 27.92"},
        {"Aircraft": "Airbus", "Service": "Ron", "Price": "$ 132.37"},
    ]
