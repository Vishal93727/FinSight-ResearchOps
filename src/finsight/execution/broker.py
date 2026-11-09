"""Deterministic paper broker. No network calls or live broker adapter exists here."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.execution.models import PaperAccount, PaperFill, PaperLedgerEntry, PaperOrder, PaperPosition
from finsight.governance.models import ModelVersion
from finsight.infrastructure.database.mixins import new_id
from finsight.risk.governance import evaluate_paper_order

_CENT = Decimal("0.00000001")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def execute_paper_order(
    db: Session,
    *,
    account: PaperAccount,
    model: ModelVersion,
    created_by: str,
    payload: dict,
) -> PaperOrder:
    """Create a rejected or immediately-filled paper order with ledger-backed accounting."""
    symbol = str(payload["symbol"]).upper()
    side = payload["side"]
    quantity = Decimal(str(payload["quantity"]))
    reference = Decimal(str(payload["simulation_reference_price"]))
    slip = Decimal(str(account.slippage_bps)) / Decimal("10000")
    fee_rate = Decimal(str(account.fee_bps)) / Decimal("10000")
    simulated_fill_price = reference * (Decimal("1") + slip if side == "BUY" else Decimal("1") - slip)
    if simulated_fill_price <= 0:
        raise ValueError("Simulated fill price must remain positive")

    position = db.scalar(
        select(PaperPosition).where(
            PaperPosition.account_id == account.id,
            PaperPosition.symbol == symbol,
        )
    )
    positions = db.scalars(
        select(PaperPosition).where(PaperPosition.account_id == account.id)
    ).all()
    current_gross = sum(
        (abs(Decimal(item.quantity) * Decimal(item.mark_price)) for item in positions),
        Decimal("0"),
    )
    current_market_value = sum(
        (Decimal(item.quantity) * Decimal(item.mark_price) for item in positions),
        Decimal("0"),
    )
    current_equity = Decimal(account.cash_balance) + current_market_value
    position_quantity = Decimal(position.quantity) if position is not None else Decimal("0")
    symbol_notional = (
        position_quantity * Decimal(position.mark_price)
        if position is not None
        else Decimal("0")
    )
    limits = {
        "fee_bps": account.fee_bps,
        "max_order_notional": str(account.max_order_notional),
        "max_gross_exposure": account.max_gross_exposure,
        "max_symbol_exposure": account.max_symbol_exposure,
    }
    risk = evaluate_paper_order(
        side=side,
        quantity=quantity,
        reference_price=simulated_fill_price,
        cash_balance=Decimal(account.cash_balance),
        current_equity=current_equity,
        current_gross_exposure=current_gross,
        symbol_position=position_quantity,
        current_symbol_notional=symbol_notional,
        account_limits=limits,
        kill_switch=bool(account.kill_switch),
    )

    order = PaperOrder(
        id=new_id(),
        account_id=account.id,
        model_version_id=model.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        simulation_reference_price=reference,
        fill_price=None,
        status="REJECTED" if not risk["approved"] else "FILLED",
        client_order_id=payload["client_order_id"],
        risk_check=risk,
        rejection_reason="; ".join(risk["reasons"]) if risk["reasons"] else None,
        created_by=created_by,
        completed_at=datetime.now(UTC) if not risk["approved"] else None,
    )
    db.add(order)
    if not risk["approved"]:
        db.flush()
        return order

    # Only create a position after the deterministic risk gate approves the order.
    if position is None:
        position = PaperPosition(
            account_id=account.id,
            symbol=symbol,
            quantity=Decimal("0"),
            average_entry_price=Decimal("0"),
            mark_price=reference,
            realized_pnl=Decimal("0"),
        )
        db.add(position)
        db.flush()

    notional = quantity * simulated_fill_price
    fee = _money(notional * fee_rate)
    cash_delta = _money(-notional - fee if side == "BUY" else notional - fee)
    quantity_delta = quantity if side == "BUY" else -quantity

    if side == "BUY":
        old_qty = Decimal(position.quantity)
        new_qty = old_qty + quantity
        position.average_entry_price = _money(
            (
                old_qty * Decimal(position.average_entry_price)
                + quantity * simulated_fill_price
                + fee
            )
            / new_qty
        )
        position.quantity = new_qty
    else:
        realized = (simulated_fill_price - Decimal(position.average_entry_price)) * quantity - fee
        position.realized_pnl = _money(Decimal(position.realized_pnl) + realized)
        position.quantity = Decimal(position.quantity) - quantity
        if position.quantity == 0:
            position.average_entry_price = Decimal("0")

    position.mark_price = reference
    position.updated_at = datetime.now(UTC)
    account.cash_balance = _money(Decimal(account.cash_balance) + cash_delta)
    order.fill_price = _money(simulated_fill_price)
    order.completed_at = datetime.now(UTC)
    db.flush()

    fill = PaperFill(
        order_id=order.id,
        account_id=account.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price=order.fill_price,
        fee_amount=fee,
        slippage_bps=account.slippage_bps,
    )
    db.add(fill)
    db.flush()
    db.add(
        PaperLedgerEntry(
            account_id=account.id,
            fill_id=fill.id,
            symbol=symbol,
            cash_delta=cash_delta,
            quantity_delta=quantity_delta,
            execution_price=order.fill_price,
            entry_type=side,
        )
    )
    return order
