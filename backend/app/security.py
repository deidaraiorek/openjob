from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings


@dataclass(frozen=True)
class AuthenticatedUser:
    email: str


def _serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.session_secret, salt="openjob-session")


def authenticate_owner(email: str, password: str) -> bool:
    settings = get_settings()
    return email == settings.owner_email and password == settings.owner_password


def create_session(response: Response, email: str) -> None:
    settings = get_settings()
    token = _serializer().dumps({"email": email})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(key=get_settings().session_cookie_name)


def current_user_from_request(request: Request) -> AuthenticatedUser | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None

    try:
        data = _serializer().loads(token)
    except BadSignature:
        return None

    email = data.get("email")
    if not email:
        return None

    return AuthenticatedUser(email=email)


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = current_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
