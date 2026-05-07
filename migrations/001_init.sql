CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('assistant', 'admin', 'owner')),
    default_cabinet_id INTEGER REFERENCES cabinets(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cabinets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'шт',
    supplier TEXT,
    default_qty REAL NOT NULL DEFAULT 1,
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_catalog_active ON catalog_items(archived_at);
CREATE INDEX IF NOT EXISTS idx_catalog_name ON catalog_items(name);

CREATE TABLE IF NOT EXISTS order_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    opened_by INTEGER REFERENCES users(id),
    closed_at TEXT,
    closed_by INTEGER REFERENCES users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_cycle
    ON order_cycles(status) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS order_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES order_cycles(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    cabinet_id INTEGER NOT NULL REFERENCES cabinets(id),
    catalog_item_id INTEGER REFERENCES catalog_items(id),
    free_form_name TEXT,
    qty REAL NOT NULL,
    unit TEXT NOT NULL,
    comment TEXT,
    doctor_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (catalog_item_id IS NOT NULL OR free_form_name IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_req_cycle ON order_requests(cycle_id);
CREATE INDEX IF NOT EXISTS idx_req_cycle_status ON order_requests(cycle_id, status);
CREATE INDEX IF NOT EXISTS idx_req_user_cycle ON order_requests(user_id, cycle_id);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES order_cycles(id) ON DELETE CASCADE,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    xlsx_path TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    summary_text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_cycle ON reports(cycle_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    payload_json TEXT,
    ts TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO cabinets (id, name) VALUES
    (1, 'Кабінет 1'),
    (2, 'Кабінет 2'),
    (3, 'Кабінет 3');
