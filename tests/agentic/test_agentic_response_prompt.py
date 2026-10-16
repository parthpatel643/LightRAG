"""Agentic answer prompt: what the model is told about the query and versions.

``{user_prompt}`` carries optional extra instructions (rendered "n/a" when
empty), not the question; the question is the user message. Labelling the slot
"the user's query" told the model the query was "n/a", and with Spanish
contract material in context it then answered English questions in Spanish.
"""

import pytest

from lightrag.prompt import PROMPTS

pytestmark = pytest.mark.offline


def _render(user_prompt: str = "n/a") -> str:
    return PROMPTS["agentic_response"].format(user_prompt=user_prompt, context_data="")


def test_user_prompt_slot_is_not_presented_as_the_query():
    rendered = _render()
    assert "user's query: n/a" not in rendered
    assert "Additional instructions, if any: n/a" in rendered


def test_language_rule_follows_the_user_message_not_the_materials():
    rendered = _render()
    assert "same language as the user's query in the user message" in rendered
    assert "never in the language of the materials" in rendered


def test_latest_text_is_defined_by_version_tag_not_reference_id():
    rendered = _render()
    assert "highest sequence number/reference ID" not in rendered
    assert "highest version tag [vN]" in rendered
    assert "[v1]...[v4]" not in PROMPTS["kg_query_context"]


def test_relative_column_labels_resolve_against_the_effective_date():
    """A CPI letter's "current handling charges" column is the pre-increase rate.

    MUC's 2018 letter lists "current" and "new ... effective January 01, 2019"
    columns; the model reported the "current" column as today's rate.
    """
    rendered = _render()
    assert '"Table caption" line' in rendered
    assert "relative to the document's own date" in rendered
    assert 'the "current" column holds the prior rate' in rendered


def test_partial_index_letters_do_not_invent_adjusted_amounts():
    """FCO's CPI letter lists only turnaround fares, which already include an
    earlier index step, so multiplying another item by the letter's percentage
    gives a wrong figure."""
    rendered = _render()
    assert "note that the letter does not state its adjusted amount" in rendered
    assert "check whether the item falls under that clause" in rendered
    assert "do not compute one" in rendered
    assert "show the calculation" not in rendered


def test_price_schedule_outranks_cost_build_up():
    """IND's bid lists a Security Search Agent wage build-up ($18.54) and a
    pricing row labelled "Hourly Bill Rate" ($20.50); United pays the latter."""
    rendered = _render()
    assert "What the carrier pays is the price or bill rate" in rendered
    assert "show the vendor's cost, not the price" in rendered


def test_breakdown_keeps_the_figures_and_conditions_listed_with_a_rate():
    rendered = _render()
    assert "other figures the source lists with the rate" in rendered
    assert "conditions on when it applies or is included" in rendered


def test_short_answers_still_follow_the_output_structure():
    """Simple rate questions got one-line answers that dropped the conditions
    and index adjustments present in the materials."""
    rendered = _render()
    assert "even when the answer is a single figure" in rendered



def test_escalation_clauses_in_the_contract_count_as_dated_rate_changes():
    """FRA's single contract fixes rates until 31 MAR 2025 and adjusts them
    from 01 APR 2025; answers alternately ignored or double-compounded it."""
    rendered = _render()
    assert "or a contract clause that adjusts rates from a stated date" in rendered
    assert "if the text does not say whether it recurs" in rendered
