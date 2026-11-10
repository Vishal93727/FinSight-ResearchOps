"""Paper-only portfolio account, order, fill, reconciliation and kill-switch APIs."""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from finsight.core.security import require_roles
from finsight.execution.broker import execute_paper_order
from finsight.execution.models import PaperAccount, PaperOrder, PaperFill, PaperPosition, PaperLedgerEntry
from finsight.governance.models import ModelVersion, ModelGovernanceDecision
from finsight.identity.models import User
from finsight.market_data.models import Instrument
from finsight.infrastructure.database.models import AuditEvent
from finsight.infrastructure.database.session import get_db
from app.schemas.phase4 import (PaperAccountCreate, PaperAccountResponse, PaperOrderCreate,
    PaperOrderResponse, KillSwitchRequest, ReconcileRequest)
from app.services.audit import record_audit

router = APIRouter(prefix="/execution", tags=["paper execution only"])


def _account_or_404(db: Session, account_id: str, user: User) -> PaperAccount:
    account = db.get(PaperAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Paper account not found")
    role_keys = {role.key for role in user.roles}
    if account.created_by != user.id and not role_keys.intersection({"ADMIN", "RISK_REVIEWER"}):
        raise HTTPException(status_code=404, detail="Paper account not found")
    return account


@router.post("/accounts", response_model=PaperAccountResponse, status_code=status.HTTP_201_CREATED)
def create_paper_account(payload: PaperAccountCreate, request: Request, db: Session = Depends(get_db),
                         user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST"))):
    if payload.max_symbol_exposure > payload.max_gross_exposure:
        raise HTTPException(status_code=422, detail="Per-symbol exposure cannot exceed gross exposure")
    account = PaperAccount(name=payload.name.strip(), currency=payload.currency,
        initial_cash=payload.initial_cash, cash_balance=payload.initial_cash,
        max_gross_exposure=payload.max_gross_exposure, max_symbol_exposure=payload.max_symbol_exposure,
        max_order_notional=payload.max_order_notional, fee_bps=payload.fee_bps,
        slippage_bps=payload.slippage_bps, kill_switch=False, created_by=user.id)
    db.add(account)
    record_audit(db, actor=user, action="paper.account_created", resource_type="paper_account",
        request_id=getattr(request.state, "request_id", None), details={"name": account.name, "currency": account.currency})
    db.commit()
    db.refresh(account)
    return account


@router.get("/accounts", response_model=list[PaperAccountResponse])
def list_paper_accounts(db: Session = Depends(get_db), user: User = Depends(require_roles(
        "ADMIN", "PORTFOLIO_ANALYST", "RISK_REVIEWER", "READ_ONLY_VIEWER"))):
    query = select(PaperAccount).order_by(PaperAccount.created_at.desc())
    if not {"ADMIN", "RISK_REVIEWER"}.intersection({role.key for role in user.roles}):
        query = query.where(PaperAccount.created_by == user.id)
    return db.scalars(query.limit(200)).all()


@router.get("/accounts/{account_id}/summary")
def account_summary(account_id: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST", "RISK_REVIEWER", "READ_ONLY_VIEWER"))):
    account = _account_or_404(db, account_id, user)
    positions = db.scalars(select(PaperPosition).where(PaperPosition.account_id == account.id).order_by(PaperPosition.symbol)).all()
    orders = db.scalars(select(PaperOrder).where(PaperOrder.account_id == account.id).order_by(PaperOrder.created_at.desc()).limit(100)).all()
    market_value = sum((Decimal(p.quantity) * Decimal(p.mark_price) for p in positions), Decimal("0"))
    gross = sum((abs(Decimal(p.quantity) * Decimal(p.mark_price)) for p in positions), Decimal("0"))
    equity = Decimal(account.cash_balance) + market_value
    return {"account": PaperAccountResponse.model_validate(account).model_dump(mode="json"),
        "cash_balance": str(account.cash_balance), "market_value": str(market_value),
        "equity": str(equity), "gross_exposure": str(gross),
        "gross_exposure_ratio": str(gross / equity if equity > 0 else Decimal("0")),
        "kill_switch": account.kill_switch,
        "positions": [{"symbol": p.symbol, "quantity": str(p.quantity), "average_entry_price": str(p.average_entry_price),
            "mark_price": str(p.mark_price), "market_value": str(Decimal(p.quantity) * Decimal(p.mark_price)),
            "realized_pnl": str(p.realized_pnl)} for p in positions if Decimal(p.quantity) != 0],
        "recent_orders": [PaperOrderResponse.model_validate(o).model_dump(mode="json") for o in orders]}


@router.post("/accounts/{account_id}/orders", response_model=PaperOrderResponse, status_code=status.HTTP_201_CREATED)
def submit_paper_order(account_id: str, payload: PaperOrderCreate, request: Request,
                       db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST"))):
    account = _account_or_404(db, account_id, user)
    existing = db.scalar(select(PaperOrder).where(PaperOrder.account_id == account.id,
                                                   PaperOrder.client_order_id == payload.client_order_id))
    if existing is not None:
        same = (existing.model_version_id == payload.model_version_id and existing.symbol == payload.symbol.upper()
            and existing.side == payload.side and Decimal(existing.quantity) == payload.quantity
            and Decimal(existing.simulation_reference_price) == payload.simulation_reference_price)
        if not same:
            raise HTTPException(status_code=409, detail="client_order_id was already used with a different order payload")
        return existing
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == payload.symbol.upper(), Instrument.is_active.is_(True)))
    if instrument is None:
        raise HTTPException(status_code=422, detail="Paper orders are limited to active instruments in the catalogue")
    if instrument.currency != account.currency:
        raise HTTPException(status_code=422, detail="Instrument currency must match the paper account currency")
    model = db.get(ModelVersion, payload.model_version_id)
    if model is None or model.state != "PROMOTED" or model.risk_decision != "PASS":
        raise HTTPException(status_code=409, detail="Paper execution requires a promoted, risk-passing model version")
    approval = db.scalar(select(ModelGovernanceDecision).where(
        ModelGovernanceDecision.model_version_id == model.id).order_by(ModelGovernanceDecision.created_at.desc()))
    if approval is None or approval.decision != "APPROVE":
        raise HTTPException(status_code=409, detail="Model has no current independent governance approval")
    try:
        order = execute_paper_order(db, account=account, model=model, created_by=user.id,
            payload=payload.model_dump())
        record_audit(db, actor=user, action=f"paper.order_{order.status.lower()}",
            resource_type="paper_order", resource_id=order.id,
            request_id=getattr(request.state, "request_id", None),
            details={"account_id": account.id, "symbol": order.symbol, "side": order.side,
                     "quantity": str(order.quantity), "risk_check": order.risk_check})
        db.commit()
        db.refresh(order)
        return order
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(PaperOrder).where(PaperOrder.account_id == account.id,
                                                       PaperOrder.client_order_id == payload.client_order_id))
        if existing is not None:
            return existing
        raise HTTPException(status_code=409, detail="Order could not be committed; retry with the same client_order_id") from exc


@router.get("/accounts/{account_id}/orders", response_model=list[PaperOrderResponse])
def list_paper_orders(account_id: str, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST", "RISK_REVIEWER", "READ_ONLY_VIEWER"))):
    account = _account_or_404(db, account_id, user)
    return db.scalars(select(PaperOrder).where(PaperOrder.account_id == account.id)
        .order_by(PaperOrder.created_at.desc()).limit(500)).all()


@router.post("/accounts/{account_id}/kill-switch")
def set_kill_switch(account_id: str, payload: KillSwitchRequest, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER"))):
    account = _account_or_404(db, account_id, user)
    if not payload.active and "ADMIN" not in {role.key for role in user.roles}:
        raise HTTPException(status_code=403, detail="Only an administrator can deactivate the kill switch")
    account.kill_switch = payload.active
    record_audit(db, actor=user, action="paper.kill_switch_activated" if payload.active else "paper.kill_switch_deactivated",
        resource_type="paper_account", resource_id=account.id,
        request_id=getattr(request.state, "request_id", None), details={"reason": payload.reason.strip()})
    db.commit()
    return {"account_id": account.id, "kill_switch": account.kill_switch, "reason": payload.reason.strip()}


def _rebuild_account(db: Session, account: PaperAccount) -> dict:
    fills = db.scalars(select(PaperFill).where(PaperFill.account_id == account.id).order_by(PaperFill.created_at.asc(), PaperFill.id.asc())).all()
    ledger_entries = db.scalars(select(PaperLedgerEntry).where(PaperLedgerEntry.account_id == account.id)).all()
    ledger_by_fill = {entry.fill_id: entry for entry in ledger_entries}
    ledger_mismatches: list[dict] = []
    fills_by_order = {fill.order_id: fill for fill in fills}
    filled_orders = db.scalars(select(PaperOrder).where(PaperOrder.account_id == account.id, PaperOrder.status == "FILLED")).all()
    for order in filled_orders:
        if order.id not in fills_by_order:
            ledger_mismatches.append({"order_id": order.id, "issue": "filled_order_missing_fill"})
    for fill in fills:
        matching_order = db.get(PaperOrder, fill.order_id)
        if matching_order is None or matching_order.status != "FILLED":
            ledger_mismatches.append({"fill_id": fill.id, "issue": "fill_order_status_mismatch"})
    cash = Decimal(account.initial_cash)
    rebuilt: dict[str, dict[str, Decimal]] = {}
    for fill in fills:
        symbol = fill.symbol
        item = rebuilt.setdefault(symbol, {"qty": Decimal("0"), "avg": Decimal("0"), "mark": Decimal("0"), "realized": Decimal("0")})
        qty, price, fee = Decimal(fill.quantity), Decimal(fill.fill_price), Decimal(fill.fee_amount)
        notional = qty * price
        expected_cash_delta = (-notional - fee) if fill.side == "BUY" else (notional - fee)
        cash += expected_cash_delta
        expected_quantity_delta = qty if fill.side == "BUY" else -qty
        ledger_entry = ledger_by_fill.get(fill.id)
        if ledger_entry is None:
            ledger_mismatches.append({"fill_id": fill.id, "issue": "missing_ledger_entry"})
        elif (Decimal(ledger_entry.cash_delta) != expected_cash_delta
              or Decimal(ledger_entry.quantity_delta) != expected_quantity_delta
              or Decimal(ledger_entry.execution_price) != price):
            ledger_mismatches.append({"fill_id": fill.id, "issue": "ledger_values_mismatch"})
        if fill.side == "BUY":
            old = item["qty"]
            item["qty"] += qty
            item["avg"] = ((old * item["avg"]) + (qty * price) + fee) / item["qty"]
        else:
            if qty > item["qty"]:
                raise HTTPException(status_code=409, detail=f"Ledger inconsistency: oversold {symbol}")
            item["realized"] += (price - item["avg"]) * qty - fee
            item["qty"] -= qty
            if item["qty"] == 0:
                item["avg"] = Decimal("0")
        item["mark"] = price
    return {"cash": cash, "positions": rebuilt, "ledger_mismatches": ledger_mismatches}


@router.post("/accounts/{account_id}/reconcile")
def reconcile_paper_account(account_id: str, payload: ReconcileRequest, request: Request,
                            db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST", "RISK_REVIEWER"))):
    account = _account_or_404(db, account_id, user)
    rebuilt = _rebuild_account(db, account)
    existing = {p.symbol: p for p in db.scalars(select(PaperPosition).where(PaperPosition.account_id == account.id)).all()}
    symbols = set(existing) | set(rebuilt["positions"])
    discrepancies = []
    cash_delta = rebuilt["cash"] - Decimal(account.cash_balance)
    if abs(cash_delta) > Decimal("0.00000001"):
        discrepancies.append({"field": "cash_balance", "actual": str(account.cash_balance), "ledger_expected": str(rebuilt["cash"])})
    for symbol in sorted(symbols):
        actual = Decimal(existing[symbol].quantity) if symbol in existing else Decimal("0")
        expected = rebuilt["positions"].get(symbol, {}).get("qty", Decimal("0"))
        if actual != expected:
            discrepancies.append({"field": "position_quantity", "symbol": symbol, "actual": str(actual), "ledger_expected": str(expected)})
    for item in rebuilt["ledger_mismatches"]:
        discrepancies.append({"field": "ledger_integrity", **item})
    if payload.repair and "ADMIN" not in {role.key for role in user.roles}:
        raise HTTPException(status_code=403, detail="Only an administrator may repair a paper ledger discrepancy")
    if payload.repair and discrepancies:
        account.cash_balance = rebuilt["cash"]
        for symbol in symbols:
            values = rebuilt["positions"].get(symbol, {"qty": Decimal("0"), "avg": Decimal("0"), "mark": Decimal("0"), "realized": Decimal("0")})
            pos = existing.get(symbol)
            if pos is None:
                pos = PaperPosition(account_id=account.id, symbol=symbol, quantity=Decimal("0"),
                    average_entry_price=Decimal("0"), mark_price=Decimal("0"), realized_pnl=Decimal("0"))
                db.add(pos)
            pos.quantity = values["qty"]
            pos.average_entry_price = values["avg"]
            pos.mark_price = values["mark"]
            pos.realized_pnl = values["realized"]
        # Rebuild each ledger row from its immutable fill record. This repairs drift without
        # changing execution facts (quantity, fill price or fee) and leaves an audit trail.
        fills = db.scalars(select(PaperFill).where(PaperFill.account_id == account.id)).all()
        ledger_rows = {entry.fill_id: entry for entry in db.scalars(select(PaperLedgerEntry).where(PaperLedgerEntry.account_id == account.id)).all()}
        for fill in fills:
            qty, price, fee = Decimal(fill.quantity), Decimal(fill.fill_price), Decimal(fill.fee_amount)
            cash_delta = (-qty * price - fee) if fill.side == "BUY" else (qty * price - fee)
            qty_delta = qty if fill.side == "BUY" else -qty
            entry = ledger_rows.get(fill.id)
            if entry is None:
                entry = PaperLedgerEntry(account_id=account.id, fill_id=fill.id, symbol=fill.symbol,
                    cash_delta=cash_delta, quantity_delta=qty_delta, execution_price=price, entry_type=fill.side)
                db.add(entry)
            else:
                entry.cash_delta = cash_delta
                entry.quantity_delta = qty_delta
                entry.execution_price = price
                entry.entry_type = fill.side
        record_audit(db, actor=user, action="paper.account_reconciled_repair", resource_type="paper_account",
            resource_id=account.id, request_id=getattr(request.state, "request_id", None),
            details={"discrepancies": discrepancies})
        db.commit()
        repaired = True
    else:
        record_audit(db, actor=user, action="paper.account_reconciled", resource_type="paper_account",
            resource_id=account.id, request_id=getattr(request.state, "request_id", None),
            details={"discrepancies": discrepancies})
        db.commit()
        repaired = False
    return {"account_id": account.id, "consistent": not discrepancies or repaired,
        "repaired": repaired, "discrepancies": discrepancies,
        "ledger_cash_balance": str(rebuilt["cash"]),
        "ledger_positions": {symbol: str(values["qty"]) for symbol, values in rebuilt["positions"].items()}}


@router.get("/accounts/{account_id}/audit")
def paper_account_audit(account_id: str, db: Session = Depends(get_db),
                        user: User = Depends(require_roles("ADMIN", "PORTFOLIO_ANALYST", "RISK_REVIEWER", "READ_ONLY_VIEWER"))):
    account = _account_or_404(db, account_id, user)
    orders = db.scalars(select(PaperOrder).where(PaperOrder.account_id == account.id).order_by(PaperOrder.created_at.desc()).limit(500)).all()
    fills = db.scalars(select(PaperFill).where(PaperFill.account_id == account.id).order_by(PaperFill.created_at.desc()).limit(500)).all()
    ledger = db.scalars(select(PaperLedgerEntry).where(PaperLedgerEntry.account_id == account.id).order_by(PaperLedgerEntry.created_at.desc()).limit(500)).all()
    events = db.scalars(select(AuditEvent).where(AuditEvent.resource_type == "paper_account",
        AuditEvent.resource_id == account.id).order_by(AuditEvent.created_at.desc()).limit(500)).all()
    order_ids = [item.id for item in orders]
    order_events = db.scalars(select(AuditEvent).where(AuditEvent.resource_type == "paper_order",
        AuditEvent.resource_id.in_(order_ids)).order_by(AuditEvent.created_at.desc()).limit(500)).all() if order_ids else []
    combined_events = sorted([*events, *order_events], key=lambda item: item.created_at, reverse=True)[:500]
    return {"account_id": account.id,
        "orders": [{"id": o.id, "client_order_id": o.client_order_id, "symbol": o.symbol, "side": o.side,
            "quantity": str(o.quantity), "status": o.status, "created_at": o.created_at} for o in orders],
        "fills": [{"id": f.id, "order_id": f.order_id, "symbol": f.symbol, "side": f.side,
            "quantity": str(f.quantity), "fill_price": str(f.fill_price), "fee": str(f.fee_amount), "created_at": f.created_at} for f in fills],
        "ledger": [{"id": x.id, "fill_id": x.fill_id, "symbol": x.symbol,
            "cash_delta": str(x.cash_delta), "quantity_delta": str(x.quantity_delta),
            "execution_price": str(x.execution_price), "created_at": x.created_at} for x in ledger],
        "audit_events": [{"id": e.id, "action": e.action, "actor_user_id": e.actor_user_id,
            "details": e.details, "created_at": e.created_at} for e in combined_events]}
