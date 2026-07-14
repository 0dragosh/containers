from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


SCHEMA_VERSION = "1"
DEFAULT_LIMIT = 6
MAX_LIMIT = 15
MAX_RESPONSE_CHARS = 30_000
MAX_SNIPPET_CHARS = 500
MAX_MESSAGES_PER_WINDOW = 5
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 2
LANE_LIMIT = 50
MAX_ANCHORS = 100
RRF_K = 60

_QUERY_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "any",
    "are",
    "current",
    "did",
    "do",
    "for",
    "from",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "latest",
    "of",
    "on",
    "or",
    "status",
    "the",
    "to",
    "update",
    "was",
    "we",
    "were",
    "what",
    "whats",
    "when",
    "where",
    "with",
}
_TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)


class MessageSearchError(RuntimeError):
    pass


def _fts_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _parse_datetime(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date format for '{field}': {value}. Please use ISO-8601 format."
        ) from exc
    return parsed.isoformat(sep=" ")


def _cursor_fingerprint(
    query: str,
    chat_jid: str | None,
    sender_phone_number: str | None,
    after: str | None,
    before: str | None,
    ranking: str,
) -> str:
    canonical = json.dumps(
        [query, chat_jid, sender_phone_number, after, before, ranking],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def _encode_cursor(fingerprint: str, offset: int) -> str:
    payload = json.dumps(
        {"v": 1, "q": fingerprint, "o": offset}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, fingerprint: str) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload != {"v": 1, "q": fingerprint, "o": payload.get("o")}:
            raise ValueError
        offset = int(payload["o"])
        if offset < 0:
            raise ValueError
        return offset
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as exc:
        raise ValueError("Invalid or mismatched search cursor") from exc


def _sender_aliases(
    identifier: str | None, resolved: Sequence[str] | None
) -> list[str]:
    if identifier is None:
        return []
    aliases = {alias for alias in (resolved or []) if alias}
    normalized = identifier.strip()
    if normalized:
        aliases.add(normalized)
    digits = "".join(character for character in normalized if character.isdigit())
    if digits:
        aliases.update({digits, f"{digits}@s.whatsapp.net", f"{digits}@lid"})
    return sorted(aliases)


class MessageSearchIndex:
    def __init__(
        self,
        source_db_path: str,
        search_db_path: str,
        *,
        sync_interval_seconds: float = 2,
        full_sync_interval_seconds: float = 3600,
    ) -> None:
        self.source_db_path = str(Path(source_db_path).resolve())
        self.search_db_path = str(Path(search_db_path).resolve())
        self.sync_interval_seconds = sync_interval_seconds
        self.full_sync_interval_seconds = full_sync_interval_seconds
        self._lock = threading.RLock()
        self._schema_initialized = False
        self._last_delete_check = 0.0
        self._last_source_check_epoch = 0.0

    def _connect(self) -> sqlite3.Connection:
        Path(self.search_db_path).parent.mkdir(parents=True, exist_ok=True)
        uri = f"file:{quote(self.search_db_path, safe='/')}?mode=rwc"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            with self._lock:
                # WAL changes and schema DDL take database locks, so concurrent
                # first searches must not run them on separate connections.
                if not self._schema_initialized:
                    connection.execute("PRAGMA journal_mode=WAL")
                    self._initialize_schema(connection)
                    self._schema_initialized = True
        except Exception:
            connection.close()
            raise
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS search_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = connection.execute(
            "SELECT value FROM search_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is not None and row[0] != SCHEMA_VERSION:
            connection.executescript(
                """
                DROP TRIGGER IF EXISTS documents_ai;
                DROP TRIGGER IF EXISTS documents_ad;
                DROP TRIGGER IF EXISTS documents_au;
                DROP TABLE IF EXISTS documents_vocab;
                DROP TABLE IF EXISTS documents_trigram;
                DROP TABLE IF EXISTS documents_fts;
                DROP TABLE IF EXISTS documents;
                DELETE FROM search_meta;
                """
            )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                rowid INTEGER PRIMARY KEY,
                source_rowid INTEGER NOT NULL UNIQUE,
                message_id TEXT NOT NULL UNIQUE,
                chat_jid TEXT NOT NULL,
                chat_name TEXT,
                sender TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                content TEXT NOT NULL,
                is_from_me INTEGER NOT NULL DEFAULT 0,
                media_type TEXT,
                quoted_message_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_documents_chat_timestamp
                ON documents(chat_jid, timestamp, rowid);
            CREATE INDEX IF NOT EXISTS idx_documents_sender_timestamp
                ON documents(sender, timestamp, rowid);
            CREATE INDEX IF NOT EXISTS idx_documents_timestamp
                ON documents(timestamp, rowid);

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                content,
                content='documents',
                content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_trigram USING fts5(
                content,
                content='documents',
                content_rowid='rowid',
                tokenize='trigram'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_vocab USING fts5vocab(documents_fts, 'row');

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.content);
                INSERT INTO documents_trigram(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                INSERT INTO documents_trigram(documents_trigram, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.content);
                INSERT INTO documents_trigram(documents_trigram, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                INSERT INTO documents_trigram(rowid, content) VALUES (new.rowid, new.content);
            END;
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO search_meta(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        connection.commit()

    def _attach_source(self, connection: sqlite3.Connection) -> None:
        source_uri = f"file:{quote(self.source_db_path, safe='/')}?mode=ro"
        connection.execute("ATTACH DATABASE ? AS source", (source_uri,))

    @staticmethod
    def _detach_source(connection: sqlite3.Connection) -> None:
        connection.execute("DETACH DATABASE source")

    @staticmethod
    def _meta_float(connection: sqlite3.Connection, key: str) -> float:
        row = connection.execute(
            "SELECT value FROM search_meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return 0.0
        try:
            return float(row[0])
        except ValueError:
            return 0.0

    @staticmethod
    def _meta_int(connection: sqlite3.Connection, key: str) -> int:
        return int(MessageSearchIndex._meta_float(connection, key))

    @staticmethod
    def _set_meta(
        connection: sqlite3.Connection, key: str, value: str | int | float
    ) -> None:
        connection.execute(
            "INSERT INTO search_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    @staticmethod
    def _upsert_sql(extra_where: str = "") -> str:
        return f"""
            INSERT INTO documents(
                source_rowid, message_id, chat_jid, chat_name, sender,
                timestamp, content, is_from_me, media_type, quoted_message_id
            )
            SELECT
                m.rowid, m.id, m.chat_jid, c.name, m.sender,
                m.timestamp, COALESCE(m.content, ''), COALESCE(m.is_from_me, 0),
                m.media_type, m.quoted_message_id
            FROM source.messages AS m
            LEFT JOIN source.chats AS c ON c.jid = m.chat_jid
            WHERE m.deleted_at IS NULL {extra_where}
            ON CONFLICT(message_id) DO UPDATE SET
                source_rowid = excluded.source_rowid,
                chat_jid = excluded.chat_jid,
                chat_name = excluded.chat_name,
                sender = excluded.sender,
                timestamp = excluded.timestamp,
                content = excluded.content,
                is_from_me = excluded.is_from_me,
                media_type = excluded.media_type,
                quoted_message_id = excluded.quoted_message_id
            WHERE documents.source_rowid IS NOT excluded.source_rowid
               OR documents.chat_jid IS NOT excluded.chat_jid
               OR documents.chat_name IS NOT excluded.chat_name
               OR documents.sender IS NOT excluded.sender
               OR documents.timestamp IS NOT excluded.timestamp
               OR documents.content IS NOT excluded.content
               OR documents.is_from_me IS NOT excluded.is_from_me
               OR documents.media_type IS NOT excluded.media_type
               OR documents.quoted_message_id IS NOT excluded.quoted_message_id
        """

    def _synchronize(
        self, connection: sqlite3.Connection, *, force_full: bool = False
    ) -> None:
        now = time.time()
        monotonic_now = time.monotonic()
        last_full = self._meta_float(connection, "last_full_sync_at")
        high_water = self._meta_int(connection, "source_high_water_rowid")
        self._attach_source(connection)
        try:
            source_max = connection.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM source.messages"
            ).fetchone()[0]
            full = (
                force_full
                or last_full == 0
                or now - last_full >= self.full_sync_interval_seconds
            )
            if source_max < high_water:
                full = True

            connection.execute("BEGIN IMMEDIATE")
            if full:
                connection.execute(self._upsert_sql())
                self._set_meta(connection, "last_full_sync_at", now)
            else:
                # Revisit a small recent tail on every search. New messages are
                # indexed immediately, and edits to recently inserted messages
                # are picked up without waiting for the hourly full pass.
                recent_floor = max(0, high_water - 500)
                connection.execute(self._upsert_sql("AND m.rowid > ?"), (recent_floor,))
                connection.execute(
                    "DELETE FROM documents WHERE source_rowid > ? AND message_id IN "
                    "(SELECT id FROM source.messages WHERE deleted_at IS NOT NULL)",
                    (recent_floor,),
                )

            if (
                full
                or monotonic_now - self._last_delete_check >= self.sync_interval_seconds
            ):
                connection.execute(
                    "DELETE FROM documents WHERE message_id NOT IN "
                    "(SELECT id FROM source.messages WHERE deleted_at IS NULL)"
                )
                self._last_delete_check = monotonic_now

            if source_max != high_water:
                self._set_meta(connection, "source_high_water_rowid", source_max)
            connection.commit()
            self._last_source_check_epoch = now
        except Exception:
            connection.rollback()
            raise
        finally:
            self._detach_source(connection)

    def _ensure_synchronized(self, connection: sqlite3.Connection) -> None:
        with self._lock:
            self._synchronize(connection)

    @staticmethod
    def _tokens(query: str) -> list[str]:
        tokens = [token.casefold() for token in _TOKEN_RE.findall(query)]
        without_stopwords = [token for token in tokens if token not in _QUERY_STOPWORDS]
        return (without_stopwords or tokens)[:12]

    @staticmethod
    def _select_terms(connection: sqlite3.Connection, tokens: list[str]) -> list[str]:
        if len(tokens) <= 1:
            return tokens
        total = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        frequencies: list[tuple[str, int, int]] = []
        for position, token in enumerate(tokens):
            row = connection.execute(
                "SELECT doc FROM documents_vocab WHERE term = ?", (token,)
            ).fetchone()
            frequencies.append((token, int(row[0]) if row else 0, position))
        selected = [
            item for item in frequencies if total == 0 or item[1] / total <= 0.20
        ]
        if not selected:
            selected = sorted(frequencies, key=lambda item: (item[1], item[2]))[:4]
        selected = sorted(selected, key=lambda item: item[2])[:8]
        return [item[0] for item in selected]

    @staticmethod
    def _filter_sql(
        *,
        chat_jid: str | None,
        sender_aliases: Sequence[str],
        after: str | None,
        before: str | None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if chat_jid:
            clauses.append("d.chat_jid = ?")
            parameters.append(chat_jid)
        if sender_aliases:
            placeholders = ",".join("?" for _ in sender_aliases)
            clauses.append(f"d.sender IN ({placeholders})")
            parameters.extend(sender_aliases)
        if after:
            clauses.append("d.timestamp > ?")
            parameters.append(after)
        if before:
            clauses.append("d.timestamp < ?")
            parameters.append(before)
        return (" AND " + " AND ".join(clauses) if clauses else "", parameters)

    @staticmethod
    def _run_lane(
        connection: sqlite3.Connection,
        *,
        table: str,
        expression: str,
        order_by: str,
        filters: str,
        filter_parameters: Sequence[Any],
    ) -> list[sqlite3.Row]:
        score = f"bm25({table})" if order_by == "relevance" else "0.0"
        ordering = (
            f"bm25({table}) ASC, d.timestamp DESC"
            if order_by == "relevance"
            else "d.timestamp DESC"
        )
        sql = f"""
            SELECT d.*, {score} AS lane_score
            FROM {table}
            JOIN documents AS d ON d.rowid = {table}.rowid
            WHERE {table} MATCH ? {filters}
            ORDER BY {ordering}
            LIMIT ?
        """
        return connection.execute(
            sql, [expression, *filter_parameters, LANE_LIMIT]
        ).fetchall()

    def _rank_candidates(
        self,
        connection: sqlite3.Connection,
        *,
        query: str,
        terms: list[str],
        ranking: str,
        filters: str,
        filter_parameters: Sequence[Any],
    ) -> list[dict[str, Any]]:
        any_expression = " OR ".join(_fts_quote(term) for term in terms)
        all_expression = " AND ".join(_fts_quote(term) for term in terms)
        lanes: list[tuple[str, float, list[sqlite3.Row]]] = []

        if len(terms) > 1:
            lanes.append(
                (
                    "phrase",
                    2.0,
                    self._run_lane(
                        connection,
                        table="documents_fts",
                        expression=_fts_quote(query.strip()),
                        order_by="relevance",
                        filters=filters,
                        filter_parameters=filter_parameters,
                    ),
                )
            )
            lanes.append(
                (
                    "all_terms",
                    1.5,
                    self._run_lane(
                        connection,
                        table="documents_fts",
                        expression=all_expression,
                        order_by="relevance",
                        filters=filters,
                        filter_parameters=filter_parameters,
                    ),
                )
            )

        lanes.append(
            (
                "bm25",
                1.0,
                self._run_lane(
                    connection,
                    table="documents_fts",
                    expression=any_expression,
                    order_by="relevance",
                    filters=filters,
                    filter_parameters=filter_parameters,
                ),
            )
        )
        if ranking in {"recent_relevance", "newest"}:
            lanes.append(
                (
                    "recent",
                    1.0,
                    self._run_lane(
                        connection,
                        table="documents_fts",
                        expression=any_expression,
                        order_by="newest",
                        filters=filters,
                        filter_parameters=filter_parameters,
                    ),
                )
            )

        trigram_terms = [term for term in terms if len(term) >= 3]
        if trigram_terms:
            lanes.append(
                (
                    "trigram",
                    0.4,
                    self._run_lane(
                        connection,
                        table="documents_trigram",
                        expression=" OR ".join(
                            _fts_quote(term) for term in trigram_terms
                        ),
                        order_by="relevance",
                        filters=filters,
                        filter_parameters=filter_parameters,
                    ),
                )
            )

        candidates: dict[int, dict[str, Any]] = {}
        for lane_name, weight, rows in lanes:
            for rank, row in enumerate(rows, start=1):
                candidate = candidates.setdefault(
                    row["rowid"],
                    {"row": row, "score": 0.0, "lanes": set()},
                )
                candidate["score"] += weight / (RRF_K + rank)
                candidate["lanes"].add(lane_name)

        if ranking == "newest":
            ordered = sorted(
                candidates.values(),
                key=lambda item: (item["row"]["timestamp"], item["score"]),
                reverse=True,
            )
        else:
            ordered = sorted(
                candidates.values(),
                key=lambda item: (item["score"], item["row"]["timestamp"]),
                reverse=True,
            )
        return ordered[:MAX_ANCHORS]

    @staticmethod
    def _context_rows(
        connection: sqlite3.Connection, anchor: sqlite3.Row
    ) -> list[sqlite3.Row]:
        before = connection.execute(
            """
            SELECT * FROM documents
            WHERE chat_jid = ?
              AND unixepoch(timestamp) >= unixepoch(?) - 21600
              AND (timestamp < ? OR (timestamp = ? AND rowid < ?))
            ORDER BY timestamp DESC, rowid DESC LIMIT ?
            """,
            (
                anchor["chat_jid"],
                anchor["timestamp"],
                anchor["timestamp"],
                anchor["timestamp"],
                anchor["rowid"],
                CONTEXT_BEFORE,
            ),
        ).fetchall()
        after = connection.execute(
            """
            SELECT * FROM documents
            WHERE chat_jid = ?
              AND unixepoch(timestamp) <= unixepoch(?) + 21600
              AND (timestamp > ? OR (timestamp = ? AND rowid > ?))
            ORDER BY timestamp ASC, rowid ASC LIMIT ?
            """,
            (
                anchor["chat_jid"],
                anchor["timestamp"],
                anchor["timestamp"],
                anchor["timestamp"],
                anchor["rowid"],
                CONTEXT_AFTER,
            ),
        ).fetchall()
        return [*reversed(before), anchor, *after]

    @staticmethod
    def _sender_display(
        row: sqlite3.Row,
        resolver: Callable[[str], str] | None,
        cache: dict[str, str],
    ) -> str:
        if row["is_from_me"]:
            return "Me"
        sender = row["sender"]
        fallback = sender.split("@", 1)[0]
        if resolver is None:
            return fallback
        if sender not in cache:
            try:
                resolved = resolver(sender)
            except Exception:
                resolved = fallback
            cache[sender] = resolved if resolved and resolved != sender else fallback
        return cache[sender]

    @staticmethod
    def _compact_message(
        row: sqlite3.Row,
        resolver: Callable[[str], str] | None,
        cache: dict[str, str],
    ) -> dict[str, Any]:
        content = row["content"] or ""
        truncated = len(content) > MAX_SNIPPET_CHARS
        snippet = content[:MAX_SNIPPET_CHARS]
        if truncated:
            snippet = snippet.rstrip() + "…"
        message: dict[str, Any] = {
            "id": row["message_id"],
            "timestamp": row["timestamp"],
            "sender_display": MessageSearchIndex._sender_display(row, resolver, cache),
            "snippet": snippet,
        }
        if truncated:
            message["content_truncated"] = True
        if row["media_type"]:
            message["media_type"] = row["media_type"]
        if row["quoted_message_id"]:
            message["quoted_message_id"] = row["quoted_message_id"]
        return message

    def _build_windows(
        self,
        connection: sqlite3.Connection,
        candidates: list[dict[str, Any]],
        terms: Sequence[str],
        resolver: Callable[[str], str] | None,
    ) -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []
        resolver_cache: dict[str, str] = {}
        for candidate in candidates:
            anchor = candidate["row"]
            rows = self._context_rows(connection, anchor)
            row_ids = {row["message_id"] for row in rows}
            existing = next(
                (
                    window
                    for window in windows
                    if window["chat_jid"] == anchor["chat_jid"]
                    and row_ids.intersection(window["_message_ids"])
                ),
                None,
            )
            if existing is not None:
                if anchor["message_id"] not in existing["anchor_message_ids"]:
                    existing["anchor_message_ids"].append(anchor["message_id"])
                existing["match_kinds"] = sorted(
                    set(existing["match_kinds"]).union(candidate["lanes"])
                )
                continue

            compact = [
                self._compact_message(row, resolver, resolver_cache)
                for row in rows[:MAX_MESSAGES_PER_WINDOW]
            ]
            normalized_content = anchor["content"].casefold()
            matched_terms = [term for term in terms if term in normalized_content]
            windows.append(
                {
                    "chat_jid": anchor["chat_jid"],
                    "chat_name": anchor["chat_name"],
                    "start_timestamp": rows[0]["timestamp"],
                    "end_timestamp": rows[-1]["timestamp"],
                    "anchor_message_ids": [anchor["message_id"]],
                    "matched_terms": matched_terms,
                    "match_kinds": sorted(candidate["lanes"]),
                    "messages": compact,
                    "_message_ids": row_ids,
                }
            )
        for window in windows:
            window.pop("_message_ids", None)
        return windows

    def search(
        self,
        query: str,
        *,
        chat_jid: str | None = None,
        sender_phone_number: str | None = None,
        sender_aliases: Sequence[str] | None = None,
        after: str | None = None,
        before: str | None = None,
        ranking: str = "recent_relevance",
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        sender_name_resolver: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("query must be non-empty")
        if len(query) > 1000:
            raise ValueError("query must be at most 1000 characters")
        if ranking not in {"recent_relevance", "relevance", "newest"}:
            raise ValueError(
                "ranking must be one of: recent_relevance, relevance, newest"
            )
        limit = max(1, min(int(limit), MAX_LIMIT))
        after = _parse_datetime(after, "after")
        before = _parse_datetime(before, "before")
        aliases = _sender_aliases(sender_phone_number, sender_aliases)
        fingerprint = _cursor_fingerprint(
            query, chat_jid, sender_phone_number, after, before, ranking
        )
        offset = _decode_cursor(cursor, fingerprint)

        try:
            with closing(self._connect()) as connection:
                self._ensure_synchronized(connection)
                tokens = self._tokens(query)
                terms = self._select_terms(connection, tokens)
                if not terms:
                    return {
                        "query": query,
                        "ranking": ranking,
                        "results": [],
                        "has_more": False,
                        "next_cursor": None,
                    }
                filters, filter_parameters = self._filter_sql(
                    chat_jid=chat_jid,
                    sender_aliases=aliases,
                    after=after,
                    before=before,
                )
                candidates = self._rank_candidates(
                    connection,
                    query=query,
                    terms=terms,
                    ranking=ranking,
                    filters=filters,
                    filter_parameters=filter_parameters,
                )
                windows = self._build_windows(
                    connection, candidates, terms, sender_name_resolver
                )
                last_sync = self._last_source_check_epoch
        except sqlite3.Error as exc:
            raise MessageSearchError(f"WhatsApp search index error: {exc}") from exc

        selected: list[dict[str, Any]] = []
        next_offset = offset
        for window in windows[offset:]:
            if len(selected) >= limit:
                break
            trial = [*selected, window]
            envelope = {
                "query": query,
                "ranking": ranking,
                "results": trial,
                "has_more": True,
                "next_cursor": _encode_cursor(fingerprint, offset + len(trial)),
                "index_timestamp": datetime.fromtimestamp(last_sync)
                .astimezone()
                .isoformat(),
                "index_lag_seconds": max(0, int(time.time() - last_sync)),
            }
            if (
                len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
                > MAX_RESPONSE_CHARS
            ):
                break
            selected = trial
            next_offset = offset + len(selected)

        has_more = next_offset < len(windows)
        return {
            "query": query,
            "ranking": ranking,
            "results": selected,
            "has_more": has_more,
            "next_cursor": _encode_cursor(fingerprint, next_offset)
            if has_more
            else None,
            "index_timestamp": datetime.fromtimestamp(last_sync)
            .astimezone()
            .isoformat(),
            "index_lag_seconds": max(0, int(time.time() - last_sync)),
        }


_instances: dict[tuple[str, str], MessageSearchIndex] = {}
_instances_lock = threading.Lock()


def search_messages(
    query: str,
    chat_jid: str | None = None,
    sender_phone_number: str | None = None,
    after: str | None = None,
    before: str | None = None,
    ranking: str = "recent_relevance",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    *,
    sender_aliases: Sequence[str] | None = None,
    sender_name_resolver: Callable[[str], str] | None = None,
    source_db_path: str | None = None,
    search_db_path: str | None = None,
) -> dict[str, Any]:
    source = source_db_path or os.environ.get("WHATSAPP_DB_PATH", "/config/messages.db")
    search = search_db_path or os.environ.get(
        "WHATSAPP_SEARCH_DB_PATH",
        str(Path(source).with_name("messages-search.db")),
    )
    key = (str(Path(source).resolve()), str(Path(search).resolve()))
    with _instances_lock:
        index = _instances.setdefault(key, MessageSearchIndex(*key))
    return index.search(
        query,
        chat_jid=chat_jid,
        sender_phone_number=sender_phone_number,
        sender_aliases=sender_aliases,
        after=after,
        before=before,
        ranking=ranking,
        limit=limit,
        cursor=cursor,
        sender_name_resolver=sender_name_resolver,
    )
