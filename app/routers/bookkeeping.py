from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LedgerEntry
from ..schemas import LedgerEntryOut, TrialBalanceItem
from ..utils import day_end, day_start, to_money

router = APIRouter(prefix="/bookkeeping", tags=["bookkeeping"])


@router.get("/ledger", response_model=list[LedgerEntryOut])
def list_ledger(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[LedgerEntry]:
    stmt = select(LedgerEntry)
    if start_date:
        stmt = stmt.where(LedgerEntry.tx_date >= day_start(start_date))
    if end_date:
        stmt = stmt.where(LedgerEntry.tx_date <= day_end(end_date))
    stmt = stmt.order_by(LedgerEntry.tx_date.desc(), LedgerEntry.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/trial-balance", response_model=list[TrialBalanceItem])
def trial_balance(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[TrialBalanceItem]:
    debit_expr = func.coalesce(
        func.sum(case((LedgerEntry.direction == "debit", LedgerEntry.amount), else_=0)), 0
    )
    credit_expr = func.coalesce(
        func.sum(case((LedgerEntry.direction == "credit", LedgerEntry.amount), else_=0)), 0
    )

    stmt = select(
        LedgerEntry.account,
        debit_expr.label("debit"),
        credit_expr.label("credit"),
    ).group_by(LedgerEntry.account)

    if start_date:
        stmt = stmt.where(LedgerEntry.tx_date >= day_start(start_date))
    if end_date:
        stmt = stmt.where(LedgerEntry.tx_date <= day_end(end_date))

    stmt = stmt.order_by(LedgerEntry.account.asc())
    rows = db.execute(stmt).all()

    return [
        TrialBalanceItem(
            account=account,
            debit=to_money(debit),
            credit=to_money(credit),
            balance=to_money(to_money(debit) - to_money(credit)),
        )
        for account, debit, credit in rows
    ]
