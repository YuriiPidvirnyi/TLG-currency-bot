import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_chat_id: int
    owner_chat_id: int
    clinic_name: str
    db_path: Path
    reports_dir: Path
    reminder_cron: str
    tz: str
    migrations_dir: Path


def load_config() -> Config:
    db_path = Path(os.environ.get("DB_PATH", "/data/clinic.db"))
    reports_dir = Path(os.environ.get("REPORTS_DIR", "/data/reports"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        admin_chat_id=int(os.environ.get("ADMIN_CHAT_ID") or "0"),
        owner_chat_id=int(os.environ.get("OWNER_CHAT_ID") or "0"),
        clinic_name=os.environ.get("CLINIC_NAME", "Стоматологічна клініка"),
        db_path=db_path,
        reports_dir=reports_dir,
        reminder_cron=os.environ.get("REMINDER_CRON", "0 16 * * 5"),
        tz=os.environ.get("TZ", "Europe/Kyiv"),
        migrations_dir=Path(__file__).resolve().parent.parent / "migrations",
    )
