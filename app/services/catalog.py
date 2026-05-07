from app.db import Database
from app.models import CatalogItem


async def list_items(db: Database, query: str | None = None, limit: int = 10) -> list[CatalogItem]:
    if query:
        cur = await db.conn.execute(
            """
            SELECT * FROM catalog_items
            WHERE archived_at IS NULL AND name LIKE ? COLLATE NOCASE
            ORDER BY name LIMIT ?
            """,
            (f"%{query}%", limit),
        )
    else:
        cur = await db.conn.execute(
            "SELECT * FROM catalog_items WHERE archived_at IS NULL ORDER BY name LIMIT ?",
            (limit,),
        )
    rows = await cur.fetchall()
    return [CatalogItem(**dict(r)) for r in rows]


async def get_item(db: Database, item_id: int) -> CatalogItem | None:
    cur = await db.conn.execute("SELECT * FROM catalog_items WHERE id = ?", (item_id,))
    row = await cur.fetchone()
    return CatalogItem(**dict(row)) if row else None


async def add_item(
    db: Database,
    name: str,
    unit: str,
    default_qty: float,
    supplier: str | None,
) -> int:
    cur = await db.conn.execute(
        "INSERT INTO catalog_items (name, unit, supplier, default_qty) VALUES (?, ?, ?, ?)",
        (name, unit, supplier, default_qty),
    )
    await db.conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


async def archive_item(db: Database, item_id: int) -> None:
    await db.conn.execute(
        "UPDATE catalog_items SET archived_at = datetime('now') WHERE id = ?",
        (item_id,),
    )
    await db.conn.commit()


async def list_cabinets(db: Database) -> list[tuple[int, str]]:
    cur = await db.conn.execute("SELECT id, name FROM cabinets ORDER BY id")
    rows = await cur.fetchall()
    return [(r["id"], r["name"]) for r in rows]
