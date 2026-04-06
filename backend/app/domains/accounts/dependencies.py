from fastapi import Depends
from sqlalchemy.orm import Session

from app.domains.accounts.models import Account
from app.domains.accounts.service import ensure_account
from app.db.session import get_db_session
from app.security import AuthenticatedUser, require_authenticated_user


def get_current_account(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Account:
    return ensure_account(session, user.email)
