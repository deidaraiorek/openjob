from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.domains.accounts.models import Account
from app.domains.accounts.service import ensure_account
from app.db.session import get_db_session
from app.security import AuthenticatedUser, require_authenticated_user


def get_current_account(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Account:
    return ensure_account(session, user.email)


def get_admin_account(
    account: Account = Depends(get_current_account),
    settings: Settings = Depends(get_settings),
) -> Account:
    if account.email != settings.owner_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return account
