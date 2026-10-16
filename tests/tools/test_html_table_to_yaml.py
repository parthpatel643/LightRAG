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


TWO_ROW_HEADER_TABLE = """
<table>
  <thead>
    <tr><th scope="col" colspan="2">Bid</th><th scope="col">Minutes</th>
        <th scope="col">Price/event</th></tr>
  </thead>
  <tbody>
    <tr><th scope="row" rowspan="2">Airbus</th><th scope="row">Turn</th>
        <td>20</td><td>$ 42.82</td></tr>
    <tr><th scope="row">Ron</th><td>25</td><td>$ 62.61</td></tr>
    <tr><th scope="row">757</th><th scope="row">Turn</th><td>30</td><td>$ 50.00</td></tr>
  </tbody>
</table>
"""

TD_ROWSPAN_TABLE = """
<table>
  <thead>
    <tr><th scope="col">Station</th><th scope="col">Service</th><th scope="col">Rate</th></tr>
  </thead>
  <tbody>
    <tr><td rowspan="2">MCO</td><td>Turn</td><td>$ 1.00</td></tr>
    <tr><td>Ron</td><td>$ 2.00</td></tr>
  </tbody>
</table>
"""


def test_every_row_header_cell_keeps_its_column():
    """Rows with an aircraft-group header (rowspan) and a service header each
    lost the service, shifting every value one column left."""
    headers, rows = converter.parse_html_table_to_rows(TWO_ROW_HEADER_TABLE)
    assert [dict(zip(headers, r)) for r in rows] == [
        {"Bid": "Airbus", "Bid (1)": "Turn", "Minutes": "20", "Price/event": "$ 42.82"},
        {"Bid": "Airbus", "Bid (1)": "Ron", "Minutes": "25", "Price/event": "$ 62.61"},
        {"Bid": "757", "Bid (1)": "Turn", "Minutes": "30", "Price/event": "$ 50.00"},
    ]


def test_data_cell_rowspan_is_carried_to_following_rows():
    headers, rows = converter.parse_html_table_to_rows(TD_ROWSPAN_TABLE)
    assert [dict(zip(headers, r)) for r in rows] == [
        {"Station": "MCO", "Service": "Turn", "Rate": "$ 1.00"},
        {"Station": "MCO", "Service": "Ron", "Rate": "$ 2.00"},
    ]
