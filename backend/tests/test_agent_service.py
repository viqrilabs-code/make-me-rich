from __future__ import annotations

from app.brokers.types import BrokerAccount
from app.models import AgentSession
from app.services.agent_service import autonomous_agent


def test_agent_session_serialization_includes_live_financials(db_session):
    session = AgentSession(
        symbol="INFY",
        status="running",
        mode="paper",
        selected_broker="mock",
        target_multiplier=1.2,
        start_equity=100000.0,
        current_equity=100000.0,
        target_equity=120000.0,
        auto_execute=True,
        launched_from="overview",
        allowed_lanes_json=["stock_intraday"],
        raw_state_json={},
    )
    db_session.add(session)
    db_session.flush()

    autonomous_agent._refresh_session_financials(  # noqa: SLF001
        db_session,
        session,
        account=BrokerAccount(
            cash_balance=64000.0,
            total_equity=104500.0,
            margin_available=59000.0,
            realized_pnl=2500.0,
            unrealized_pnl=2000.0,
            source="mock-broker",
            raw_payload={},
        ),
        broker_name="mock",
        using_fallback=False,
    )

    payload = autonomous_agent._serialize_session(session)  # noqa: SLF001

    assert payload.current_equity == 104500.0
    assert payload.progress_pct == 22.5
    assert payload.cash_balance == 64000.0
    assert payload.realized_pnl == 2500.0
    assert payload.unrealized_pnl == 2000.0
    assert payload.today_pnl == 4500.0
    assert payload.session_pnl == 4500.0
    assert payload.target_gap == 15500.0
