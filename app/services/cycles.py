from app.db import Database
from app.models import OrderCycle


async def get_open_cycle(db: Database) -> OrderCycle | None:
    cur = await db.conn.execute(
        "SELECT * FROM order_cycles WHERE status = 'open' ORDER BY id DESC LIMIT 1"
    )
    row = await cur.fetchone()
    if not row:
        return None
    return OrderCycle(**dict(row))


async def get_cycle(db: Database, cycle_id: int) -> OrderCycle | None:
    cur = await db.conn.execute("SELECT * FROM order_cycles WHERE id = ?", (cycle_id,))
    row = await cur.fetchone()
    return OrderCycle(**dict(row)) if row else None


async def open_cycle(db: Database, opened_by_user_id: int) -> OrderCycle:
    existing = await get_open_cycle(db)
    if existing:
        return existing
    cur = await db.conn.execute(
        "INSERT INTO order_cycles (status, opened_by) VALUES ('open', ?)",
        (opened_by_user_id,),
    )
    await db.conn.commit()
    cycle_id = cur.lastrowid
    return await get_cycle(db, cycle_id)  # type: ignore[return-value]


async def close_cycle(db: Database, cycle_id: int, closed_by_user_id: int) -> None:
    await db.conn.execute(
        "UPDATE order_cycles SET status = 'closed', closed_at = datetime('now'), closed_by = ? WHERE id = ?",
        (closed_by_user_id, cycle_id),
    )
    await db.conn.commit()


async def cycle_counts(db: Database, cycle_id: int) -> dict[str, int]:
    cur = await db.conn.execute(
        """
        SELECT
            SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected
        FROM order_requests WHERE cycle_id = ?
        """,
        (cycle_id,),
    )
    row = await cur.fetchone()
    return {
        "approved": row["approved"] or 0,
        "pending": row["pending"] or 0,
        "rejected": row["rejected"] or 0,
    }


async def list_recent_cycles(db: Database, limit: int = 10) -> list[OrderCycle]:
    cur = await db.conn.execute(
        "SELECT * FROM order_cycles ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = await cur.fetchall()
    return [OrderCycle(**dict(r)) for r in rows]
