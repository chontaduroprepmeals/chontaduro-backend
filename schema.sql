-- Minimal DB schema for starter (SQLite)
-- Run with: sqlite3 app.db < schema.sql

PRAGMA foreign_keys = ON;

-- Meals: you may continue to manage meals.json; this table is optional to import later
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT,
    ingredients TEXT,      -- JSON or comma-separated list
    calories INTEGER,
    protein_g REAL,
    cost_estimate REAL,
    price REAL,
    image_url TEXT,
    tags TEXT,             -- JSON array or comma-separated
    created_at TEXT DEFAULT (datetime('now'))
);

-- Templates (weekly menus)
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,   -- e.g. "plan4-omnivore-week-a"
    name TEXT,
    diet TEXT,
    description TEXT,
    pool_json TEXT,        -- JSON document with mains/breakfasts arrays
    rules_json TEXT,       -- JSON document for rules
    created_at TEXT DEFAULT (datetime('now'))
);

-- Images store: reference to files uploaded to Cloudinary (or other CDN)
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_name TEXT,            -- optional link by meal name
    template_id TEXT,          -- optional link to template
    url TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    format TEXT,
    filesize INTEGER,
    source TEXT,               -- 'real' | 'ai' | 'stock'
    uploaded_by TEXT,
    uploaded_at TEXT DEFAULT (datetime('now')),
    alt_text TEXT,
    tags TEXT,
    approved INTEGER DEFAULT 0,
    FOREIGN KEY(template_id) REFERENCES templates(id)
);

-- Sessions (lightweight order/session persistence)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    data_json TEXT,            -- full session state as JSON for now
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

-- Orders (confirmed placements)
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    template_id TEXT,
    week TEXT,
    placed_at TEXT DEFAULT (datetime('now')),
    total_price REAL,
    details_json TEXT,        -- menu snapshot or production snapshot
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

-- Swaps history (user replacements)
CREATE TABLE IF NOT EXISTS swaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    week TEXT,
    day_index INTEGER,
    slot_index INTEGER,
    original_name TEXT,
    new_name TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

-- Feedback
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    template_id TEXT,
    week TEXT,
    rating INTEGER,
    comment TEXT,
    day_index INTEGER,
    slot_index INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);