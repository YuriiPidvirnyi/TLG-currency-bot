import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config
from app.db import Database
from app.services import cycles, notifications

log = logging.getLogger(__name__)


def _parse_cron(expr: str) -> CronTrigger:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
    )


async def _remind_close(bot: Bot, db: Database) -> None:
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        return
    counts = await cycles.cycle_counts(db, cycle.id)
    text = (
        f"⏰ Нагадування: пора закрити цикл #{cycle.id} і сформувати звіт.\n"
        f"Підтверджено: {counts['approved']} • На ревʼю: {counts['pending']}\n"
        f"Команда: /close (попередній перегляд: /preview)"
    )
    await notifications.notify_admins(bot, db, text)


def setup_scheduler(bot: Bot, db: Database, config: Config) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=config.tz)
    try:
        trigger = _parse_cron(config.reminder_cron)
    except ValueError as e:
        log.warning("Skipping scheduler: %s", e)
        return sched
    sched.add_job(_remind_close, trigger, args=[bot, db], id="cycle-close-reminder")
    return sched
