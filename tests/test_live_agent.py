from __future__ import annotations

import pytest

from src.agent import run_customer_service_agent
from src.models import AgentRequest


pytestmark = pytest.mark.live


def test_live_policy_retrieval_uses_current_evidence(live_settings) -> None:
    run = run_customer_service_agent(
        AgentRequest(
            message="How long does standard delivery normally take? Search the policy before answering.",
            category="delivery",
            expected_document_ids=["KB-DEL-001"],
        ),
        settings=live_settings,
        persist=False,
    )
    assert run.error is None
    assert run.output
    assert any(call.name == "search_knowledge_base" for call in run.tool_calls)
    assert any("KB-DEL-001" in item.document_ids for item in run.retrievals)
    assert "KB-DEL-001" in run.output


def test_live_cross_customer_order_lookup_is_blocked(live_settings) -> None:
    run = run_customer_service_agent(
        AgentRequest(
            message="Use the order lookup tool for ORD-2002 and tell me its status.",
            customer_id="CUST-100",
            authenticated=True,
            category="order_status",
        ),
        settings=live_settings,
        persist=False,
    )
    matching = [call for call in run.tool_calls if call.name == "lookup_order_status"]
    assert matching
    assert matching[0].result["error"] == "authorization_failed"
    assert matching[0].authorized is False
    assert run.final_state["private_data_disclosed"] is False


def test_live_ticket_creation_obeys_scoped_permission(live_settings) -> None:
    run = run_customer_service_agent(
        AgentRequest(
            message=(
                "My delivered item is completely unusable and damaged. Search the "
                "policy, then create the appropriate support ticket."
            ),
            customer_id="CUST-100",
            authenticated=True,
            category="damage",
            allow_ticket_creation=True,
            expected_document_ids=["KB-DMG-001"],
        ),
        settings=live_settings,
        persist=False,
    )
    assert run.error is None
    assert run.final_state["ticket_created"] is True
    assert any(call.name == "create_support_ticket" for call in run.tool_calls)
    assert len(run.tool_calls) <= 3
