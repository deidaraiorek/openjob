from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, EmailStr

from app.security import (
    AuthenticatedUser,
    authenticate_owner,
    clear_session,
    create_session,
    require_authenticated_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionResponse(BaseModel):
    authenticated: bool
    email: str | None = None


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response) -> SessionResponse:
    if not authenticate_owner(payload.email, payload.password):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return SessionResponse(authenticated=False)

    create_session(response, payload.email)
    return SessionResponse(authenticated=True, email=payload.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session", response_model=SessionResponse)
def session(user: AuthenticatedUser = Depends(require_authenticated_user)) -> SessionResponse:
    return SessionResponse(authenticated=True, email=user.email)
