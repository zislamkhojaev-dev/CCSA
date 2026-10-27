from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models import User
from app.schemas.auth import TokenResponse


def cookie_kwargs(*, max_age: int) -> dict:
    settings = get_settings()
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "max_age": max_age,
    }


class AuthService:
    async def login(self, db: AsyncSession, login: str, password: str, response: Response) -> TokenResponse:
        result = await db.execute(select(User).where(User.login == login))
        user = result.scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid credentials", 401)
        if not user.is_active:
            raise AppError(ErrorCode.AUTH_INACTIVE, "User inactive", 403)

        settings = get_settings()
        access = create_access_token(user.id)
        refresh = create_refresh_token(user.id)
        response.set_cookie("access_token", access, **cookie_kwargs(max_age=settings.cookie_access_max_age))
        response.set_cookie(
            "refresh_token", refresh, **cookie_kwargs(max_age=settings.cookie_refresh_max_age)
        )
        return TokenResponse(access_token=access)

    def logout(self, response: Response) -> dict:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return {"message": "Logged out"}


auth_service = AuthService()
