from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from message_search import MAX_RESPONSE_CHARS, MessageSearchIndex


class MessageSearchIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.source_path = root / "messages.db"
        self.search_path = root / "messages-search.db"
        self._create_source()
        self.index = MessageSearchIndex(
            str(self.source_path),
            str(self.search_path),
            sync_interval_seconds=2,
            full_sync_interval_seconds=3600,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_source(self) -> None:
        with closing(sqlite3.connect(self.source_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE chats (
                    jid TEXT PRIMARY KEY,
                    name TEXT,
                    is_group INTEGER DEFAULT 0
                );
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    chat_jid TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    content TEXT,
                    timestamp TEXT NOT NULL,
                    is_from_me INTEGER DEFAULT 0,
                    media_type TEXT,
                    filename TEXT,
                    deleted_at TEXT,
                    quoted_message_id TEXT
                );
                INSERT INTO chats(jid, name) VALUES
                    ('atlas@g.us', 'Project Atlas'),
                    ('coffee@g.us', 'Coffee Club'),
                    ('noise@g.us', 'General');
                """
            )
            rows = [
                (
                    "atlas-old",
                    "atlas@g.us",
                    "111@s.whatsapp.net",
                    "Project Atlas deployment is blocked while we wait for the database migration.",
                    "2026-06-01 09:00:00",
                    0,
                    None,
                    None,
                    None,
                ),
                (
                    "atlas-incidental",
                    "noise@g.us",
                    "222@s.whatsapp.net",
                    "The Atlas logo looks nice.",
                    "2026-06-10 10:00:00",
                    0,
                    None,
                    None,
                    None,
                ),
                (
                    "atlas-latest",
                    "atlas@g.us",
                    "111@s.whatsapp.net",
                    "The database migration finished and the Atlas deployment is now live.",
                    "2026-06-12 12:00:00",
                    0,
                    None,
                    None,
                    "atlas-old",
                ),
                (
                    "cafe",
                    "coffee@g.us",
                    "333@s.whatsapp.net",
                    "Let's meet at the café beside the station.",
                    "2026-06-11 08:00:00",
                    0,
                    None,
                    None,
                    None,
                ),
                (
                    "deleted",
                    "atlas@g.us",
                    "111@s.whatsapp.net",
                    "Atlas secret obsolete status.",
                    "2026-06-13 12:00:00",
                    0,
                    None,
                    "2026-06-13 13:00:00",
                    None,
                ),
            ]
            connection.executemany(
                """
                INSERT INTO messages(
                    id, chat_jid, sender, content, timestamp, is_from_me,
                    media_type, deleted_at, quoted_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

    def search(self, query: str, **kwargs):
        return self.index.search(
            query,
            sender_name_resolver=lambda sender: {"111@s.whatsapp.net": "Alice"}.get(
                sender, sender
            ),
            **kwargs,
        )

    def test_recent_relevance_finds_latest_substantive_update(self) -> None:
        result = self.search("what is the latest status of Atlas deployment")
        self.assertTrue(result["results"])
        self.assertEqual(result["results"][0]["anchor_message_ids"][0], "atlas-latest")
        self.assertIn(
            "Alice",
            {message["sender_display"] for message in result["results"][0]["messages"]},
        )

    def test_relevance_and_structured_filters(self) -> None:
        result = self.search(
            "Atlas deployment",
            ranking="relevance",
            chat_jid="atlas@g.us",
            sender_phone_number="111",
            sender_aliases=["111@s.whatsapp.net"],
            after="2026-06-11T00:00:00",
        )
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["anchor_message_ids"], ["atlas-latest"])

    def test_unicode_diacritics_and_trigram_fragment(self) -> None:
        unicode_result = self.search("cafe")
        self.assertEqual(unicode_result["results"][0]["anchor_message_ids"], ["cafe"])
        trigram_result = self.search("migrat")
        anchors = {
            anchor
            for window in trigram_result["results"]
            for anchor in window["anchor_message_ids"]
        }
        self.assertIn("atlas-latest", anchors)

    def test_deleted_messages_are_not_indexed(self) -> None:
        result = self.search("secret obsolete")
        self.assertEqual(result["results"], [])

    def test_incremental_insert_and_delete_reconciliation(self) -> None:
        self.search("Atlas")
        with closing(sqlite3.connect(self.source_path)) as connection:
            connection.execute(
                """
                INSERT INTO messages(id, chat_jid, sender, content, timestamp, is_from_me)
                VALUES ('atlas-newer', 'atlas@g.us', '111@s.whatsapp.net',
                        'Atlas deployment verification passed.', '2026-06-14 12:00:00', 0)
                """
            )
            connection.execute(
                "UPDATE messages SET deleted_at = '2026-06-14 12:01:00' WHERE id = 'atlas-latest'"
            )
            connection.commit()
        result = self.search("Atlas deployment", ranking="newest")
        anchors = [
            anchor
            for window in result["results"]
            for anchor in window["anchor_message_ids"]
        ]
        self.assertEqual(anchors[0], "atlas-newer")
        self.assertNotIn("atlas-latest", anchors)

    def test_new_message_is_visible_on_the_very_next_search(self) -> None:
        self.search("Atlas")
        with closing(sqlite3.connect(self.source_path)) as connection:
            connection.execute(
                """
                INSERT INTO messages(id, chat_jid, sender, content, timestamp, is_from_me)
                VALUES ('instant', 'atlas@g.us', '111@s.whatsapp.net',
                        'Realtime Falcon status is green.', '2026-06-15 12:00:00', 0)
                """
            )
            connection.commit()
        result = self.search("Falcon status")
        anchors = [
            anchor
            for window in result["results"]
            for anchor in window["anchor_message_ids"]
        ]
        self.assertIn("instant", anchors)

    def test_pagination_cursor_is_bound_to_query(self) -> None:
        result = self.search("Atlas", limit=1)
        self.assertTrue(result["has_more"])
        next_page = self.search("Atlas", limit=1, cursor=result["next_cursor"])
        self.assertNotEqual(
            result["results"][0]["anchor_message_ids"],
            next_page["results"][0]["anchor_message_ids"],
        )
        with self.assertRaisesRegex(ValueError, "cursor"):
            self.search("different query", cursor=result["next_cursor"])
        with self.assertRaisesRegex(ValueError, "cursor"):
            self.search("Atlas", cursor="not-valid-base64!@#")

    def test_concurrent_searches_share_the_index_safely(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(lambda _: self.search("Atlas deployment"), range(24))
            )
        self.assertTrue(all(result["results"] for result in results))
        self.assertTrue(
            all(
                result["results"][0]["anchor_message_ids"][0] == "atlas-latest"
                for result in results
            )
        )

    def test_response_has_hard_size_bound(self) -> None:
        with closing(sqlite3.connect(self.source_path)) as connection:
            for index in range(30):
                connection.execute(
                    """
                    INSERT INTO messages(id, chat_jid, sender, content, timestamp, is_from_me)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        f"large-{index}",
                        f"large-{index}@g.us",
                        "999@s.whatsapp.net",
                        "oversizedtopic " + "x" * 7600,
                        f"2026-06-{index % 28 + 1:02d} 15:00:{index % 60:02d}",
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO chats(jid, name) VALUES (?, ?)",
                    (f"large-{index}@g.us", f"Large {index}"),
                )
            connection.commit()
        result = self.search("oversizedtopic", limit=15)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(encoded), MAX_RESPONSE_CHARS)
        self.assertTrue(
            any(
                message.get("content_truncated")
                for window in result["results"]
                for message in window["messages"]
            )
        )

    def test_source_database_schema_is_untouched(self) -> None:
        self.search("Atlas")
        with closing(sqlite3.connect(self.source_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertEqual(tables, {"chats", "messages"})

    def test_input_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            self.search("   ")
        with self.assertRaisesRegex(ValueError, "ranking"):
            self.search("Atlas", ranking="invalid")
        with self.assertRaisesRegex(ValueError, "ISO-8601"):
            self.search("Atlas", after="not-a-date")
        self.assertEqual(self.search('" OR * NOT')["results"], [])
        self.assertEqual(len(self.search("Atlas", limit=999)["results"]), 3)


if __name__ == "__main__":
    unittest.main()
