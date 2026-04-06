from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.models import Account


def ensure_account(session: Session, email: str) -> Account:
    account = session.scalar(select(Account).where(Account.email == email))
    if account:
        return account

    account = Account(email=email, is_owner=True)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
