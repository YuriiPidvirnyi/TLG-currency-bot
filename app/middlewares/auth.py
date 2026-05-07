from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from app.db import Database
from app.models import User


async def fetch_user(db: Database, tg_id: int) -> User | None:
    cur = await db.conn.execute(
        "SELECT id, tg_id, full_name, role, default_cabinet_id FROM users WHERE tg_id = ?",
        (tg_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return User(
        id=row["id"],
        tg_id=row["tg_id"],
        full_name=row["full_name"],
        role=row["role"],
        default_cabinet_id=row["default_cabinet_id"],
    )


class AuthMiddleware(BaseMiddleware):
    """Resolves the User from tg user_id and injects it into handler data.

    Unauthorized users get a polite refusal and the handler is skipped.
    """

    def __init__(self, db: Database):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        user = await fetch_user(self.db, tg_user.id)
        data["user"] = user

        if user is None:
            if hasattr(event, "answer"):
                await event.answer(
                    "🚫 У вас немає доступу до цього бота.\n"
                    f"Перешліть свій Telegram ID адміністратору: `{tg_user.id}`",
                    parse_mode="Markdown",
                )
            return None

        return await handler(event, data)


def require_role(*roles: str) -> Callable:
    """Decorator-like guard for handlers; checks data['user'].role."""

    allowed = set(roles)

    async def guard(user: User | None) -> bool:
        return bool(user and user.role in allowed)

    return guard
