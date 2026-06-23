import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "podcast.db")
TEXT_REPLACEMENTS = (
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("\ufffd", ""),
    ("\u00e2\u20ac\u02dc", "'"),
    ("\u00e2\u20ac\u2122", "'"),
    ("\u00e2\u20ac\u0153", '"'),
    ("\u00e2\u20ac\u009d", '"'),
    ("\u00e2\u20ac\u201c", "-"),
    ("\u00e2\u20ac\u201d", "-"),
)


def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            script TEXT NOT NULL DEFAULT '',
            audio_path TEXT,
            interests TEXT NOT NULL DEFAULT '[]',
            articles TEXT NOT NULL DEFAULT '[]',
            tone TEXT NOT NULL DEFAULT 'neutral',
            duration TEXT NOT NULL DEFAULT 'normal',
            frequency TEXT NOT NULL DEFAULT 'daily',
            voice TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            speaker_mode TEXT NOT NULL DEFAULT 'solo',
            selected_interest_count INTEGER NOT NULL DEFAULT 1,
            generation_type TEXT NOT NULL DEFAULT 'manual',
            schedule_id TEXT,
            article_count INTEGER NOT NULL DEFAULT 0,
            duplicate_articles_filtered INTEGER NOT NULL DEFAULT 0,
            seen_articles_filtered INTEGER NOT NULL DEFAULT 0,
            total_fetched INTEGER NOT NULL DEFAULT 0,
            invalid_articles_filtered INTEGER NOT NULL DEFAULT 0,
            title_irrelevant_articles_filtered INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
            tool_usage TEXT NOT NULL DEFAULT '[]',
            workflow_timings TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            generation_time_ms INTEGER,
            success INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'completed',
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS seen_articles (
            user_id TEXT NOT NULL,
            url TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (user_id, url)
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            selected_interests TEXT NOT NULL DEFAULT '[]',
            frequency TEXT NOT NULL DEFAULT 'daily',
            duration TEXT NOT NULL DEFAULT 'normal',
            tone TEXT NOT NULL DEFAULT 'neutral',
            voice TEXT NOT NULL DEFAULT '',
            speaker_mode TEXT NOT NULL DEFAULT 'solo',
            last_run_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS episode_events (
            id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            value REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (episode_id) REFERENCES episodes(id)
        );
    """)
    _ensure_episode_columns(conn)
    _normalize_existing_text(conn)
    conn.execute(
        """UPDATE episodes
           SET status = 'audio_failed'
           WHERE success = 0
             AND (status IS NULL OR status = '' OR status = 'completed')"""
    )
    conn.execute(
        """UPDATE episodes
           SET error_message = 'Audio generation failed before error tracking was added.'
           WHERE success = 0
             AND (error_message IS NULL OR error_message = '')"""
    )
    conn.commit()
    conn.close()


def _ensure_episode_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(episodes)").fetchall()
    }
    migrations = {
        "interests": "interests TEXT NOT NULL DEFAULT '[]'",
        "status": "status TEXT NOT NULL DEFAULT 'completed'",
        "error_message": "error_message TEXT",
        "user_id": "user_id TEXT NOT NULL DEFAULT ''",
        "speaker_mode": "speaker_mode TEXT NOT NULL DEFAULT 'solo'",
        "selected_interest_count": "selected_interest_count INTEGER NOT NULL DEFAULT 1",
        "generation_type": "generation_type TEXT NOT NULL DEFAULT 'manual'",
        "schedule_id": "schedule_id TEXT",
        "article_count": "article_count INTEGER NOT NULL DEFAULT 0",
        "duplicate_articles_filtered": "duplicate_articles_filtered INTEGER NOT NULL DEFAULT 0",
        "seen_articles_filtered": "seen_articles_filtered INTEGER NOT NULL DEFAULT 0",
        "total_fetched": "total_fetched INTEGER NOT NULL DEFAULT 0",
        "invalid_articles_filtered": "invalid_articles_filtered INTEGER NOT NULL DEFAULT 0",
        "title_irrelevant_articles_filtered": "title_irrelevant_articles_filtered INTEGER NOT NULL DEFAULT 0",
        "estimated_cost_usd": "estimated_cost_usd REAL NOT NULL DEFAULT 0.0",
        "tool_usage": "tool_usage TEXT NOT NULL DEFAULT '[]'",
        "workflow_timings": "workflow_timings TEXT NOT NULL DEFAULT '{}'",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE episodes ADD COLUMN {ddl}")


def _normalize_existing_text(conn: sqlite3.Connection) -> None:
    columns = ("title", "summary", "script", "articles", "interests", "error_message")
    for column in columns:
        for old, new in TEXT_REPLACEMENTS:
            conn.execute(
                f"UPDATE episodes SET {column} = REPLACE({column}, ?, ?)",
                (old, new),
            )
