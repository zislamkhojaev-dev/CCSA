from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_user_id
from app.core.errors import AppError, ErrorCode
from app.core.security import decode_token
from app.database import get_db
from app.models import User


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias="access_token"),
) -> User:
    if not access_token:
        raise AppError.unauthorized("Not authenticated")
    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise AppError.unauthorized("Invalid token")
    login = payload.get("sub")
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.login == login, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise AppError.unauthorized("User not found")
    set_user_id(user.id)
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise AppError(ErrorCode.AUTH_FORBIDDEN, "Admin required", status.HTTP_403_FORBIDDEN)
    return user


# Kept for FastAPI internals that still raise HTTPException.
def http_unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
