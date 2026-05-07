from app.db import Database
from app.models import OrderRequest


async def create_catalog_request(
    db: Database,
    cycle_id: int,
    user_id: int,
    cabinet_id: int,
    catalog_item_id: int,
    qty: float,
    unit: str,
    comment: str | None,
    doctor_name: str | None,
) -> int:
    cur = await db.conn.execute(
        """
        INSERT INTO order_requests
            (cycle_id, user_id, cabinet_id, catalog_item_id, qty, unit, comment, doctor_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved')
        """,
        (cycle_id, user_id, cabinet_id, catalog_item_id, qty, unit, comment, doctor_name),
    )
    await db.conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


async def create_freeform_request(
    db: Database,
    cycle_id: int,
    user_id: int,
    cabinet_id: int,
    name: str,
    qty: float,
    unit: str,
    comment: str | None,
    doctor_name: str | None,
) -> int:
    cur = await db.conn.execute(
        """
        INSERT INTO order_requests
            (cycle_id, user_id, cabinet_id, free_form_name, qty, unit, comment, doctor_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (cycle_id, user_id, cabinet_id, name, qty, unit, comment, doctor_name),
    )
    await db.conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


async def list_user_requests(db: Database, user_id: int, cycle_id: int) -> list[dict]:
    cur = await db.conn.execute(
        """
        SELECT r.id, r.qty, r.unit, r.comment, r.status, r.free_form_name,
               c.name AS cabinet_name, ci.name AS catalog_name
        FROM order_requests r
        JOIN cabinets c ON c.id = r.cabinet_id
        LEFT JOIN catalog_items ci ON ci.id = r.catalog_item_id
        WHERE r.user_id = ? AND r.cycle_id = ?
        ORDER BY r.id DESC
        """,
        (user_id, cycle_id),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def list_pending_requests(db: Database, cycle_id: int) -> list[dict]:
    cur = await db.conn.execute(
        """
        SELECT r.id, r.free_form_name, r.qty, r.unit, r.comment, r.doctor_name,
               c.name AS cabinet_name, u.full_name AS author
        FROM order_requests r
        JOIN cabinets c ON c.id = r.cabinet_id
        JOIN users u ON u.id = r.user_id
        WHERE r.cycle_id = ? AND r.status = 'pending'
        ORDER BY r.id
        """,
        (cycle_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_status(db: Database, request_id: int, status: str) -> None:
    await db.conn.execute(
        "UPDATE order_requests SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, request_id),
    )
    await db.conn.commit()


async def delete_request(db: Database, request_id: int, user_id: int | None = None) -> bool:
    """If user_id is provided — only allow deleting own requests."""
    if user_id is not None:
        cur = await db.conn.execute(
            "DELETE FROM order_requests WHERE id = ? AND user_id = ?",
            (request_id, user_id),
        )
    else:
        cur = await db.conn.execute("DELETE FROM order_requests WHERE id = ?", (request_id,))
    await db.conn.commit()
    return cur.rowcount > 0
