"""SQLite-based application tracking storage."""

from __future__ import annotations

import aiosqlite

from .models import ApplicationStatus, JobSource, TrackedApplication

DEFAULT_DB_PATH = "job_applications.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    employer TEXT NOT NULL,
    url TEXT DEFAULT '',
    status TEXT DEFAULT 'saved',
    notes TEXT DEFAULT '',
    applied_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, source)
);
"""


class ApplicationTracker:
    """Persistent application tracker backed by SQLite."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the database and create tables if needed."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(CREATE_TABLE_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            await self.initialize()
        assert self._db is not None
        return self._db

    async def save_application(
        self,
        job_id: str,
        source: JobSource,
        title: str,
        employer: str,
        url: str = "",
        notes: str = "",
    ) -> TrackedApplication:
        """Save a new job application to track.

        Args:
            job_id: The job listing ID from the source.
            source: Which job board (nav, jobbnorge, etc.).
            title: Job title.
            employer: Company name.
            url: Link to the listing.
            notes: Optional notes.

        Returns:
            The created TrackedApplication.
        """
        db = await self._ensure_db()
        from datetime import datetime

        now = datetime.now().isoformat()

        cursor = await db.execute(
            """
            INSERT INTO applications (job_id, source, title, employer, url, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, source) DO UPDATE SET
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (job_id, source.value, title, employer, url, ApplicationStatus.SAVED.value, notes, now, now),
        )
        await db.commit()

        return TrackedApplication(
            id=cursor.lastrowid or 0,
            job_id=job_id,
            source=source,
            title=title,
            employer=employer,
            url=url,
            status=ApplicationStatus.SAVED,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

    async def update_status(
        self,
        application_id: int,
        status: ApplicationStatus,
        notes: str | None = None,
        applied_date: str | None = None,
    ) -> TrackedApplication | None:
        """Update the status of a tracked application.

        Args:
            application_id: Internal tracking ID.
            status: New status.
            notes: Optional updated notes.
            applied_date: Date the application was submitted.

        Returns:
            Updated TrackedApplication, or None if not found.
        """
        db = await self._ensure_db()
        from datetime import datetime

        now = datetime.now().isoformat()

        # Build dynamic update
        updates = ["status = ?", "updated_at = ?"]
        params: list[str | int] = [status.value, now]

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if applied_date is not None:
            updates.append("applied_date = ?")
            params.append(applied_date)

        params.append(application_id)

        await db.execute(
            f"UPDATE applications SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()

        return await self.get_application(application_id)

    async def get_application(self, application_id: int) -> TrackedApplication | None:
        """Get a single application by ID."""
        db = await self._ensure_db()
        cursor = await db.execute("SELECT * FROM applications WHERE id = ?", (application_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_application(row)

    async def list_applications(
        self,
        status: ApplicationStatus | None = None,
        limit: int = 50,
    ) -> list[TrackedApplication]:
        """List tracked applications, optionally filtered by status.

        Args:
            status: Filter by status, or None for all.
            limit: Maximum number to return.

        Returns:
            List of TrackedApplication objects.
        """
        db = await self._ensure_db()

        if status:
            cursor = await db.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM applications ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )

        rows = await cursor.fetchall()
        return [self._row_to_application(row) for row in rows]

    async def delete_application(self, application_id: int) -> bool:
        """Delete a tracked application.

        Returns:
            True if deleted, False if not found.
        """
        db = await self._ensure_db()
        cursor = await db.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        await db.commit()
        return (cursor.rowcount or 0) > 0

    @staticmethod
    def _row_to_application(row: aiosqlite.Row) -> TrackedApplication:
        return TrackedApplication(
            id=row["id"],
            job_id=row["job_id"],
            source=JobSource(row["source"]),
            title=row["title"],
            employer=row["employer"],
            url=row["url"],
            status=ApplicationStatus(row["status"]),
            notes=row["notes"],
            applied_date=row["applied_date"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
