"""Tests for the MCP Job Search Agent."""

import pytest

from mcp_job_search.models import (
    ApplicationStatus,
    JobListing,
    JobSource,
    SearchFilters,
    TrackedApplication,
)
from mcp_job_search.tracker import ApplicationTracker


class TestModels:
    """Test Pydantic models."""

    def test_job_listing_creation(self):
        job = JobListing(
            id="abc-123",
            source=JobSource.NAV,
            title="Software Engineer",
            employer="Cool Company AS",
            location="Oslo",
        )
        assert job.title == "Software Engineer"
        assert job.source == JobSource.NAV

    def test_search_filters_defaults(self):
        filters = SearchFilters(query="python developer")
        assert filters.max_results == 0
        assert filters.location == ""

    def test_search_filters_max_results_bounds(self):
        SearchFilters(query="test", max_results=0)
        SearchFilters(query="test", max_results=10000)
        with pytest.raises(Exception):
            SearchFilters(query="test", max_results=10001)

    def test_application_status_values(self):
        assert ApplicationStatus.SAVED.value == "saved"
        assert ApplicationStatus.INTERVIEWING.value == "interviewing"
        assert ApplicationStatus.REJECTED.value == "rejected"


class TestTracker:
    """Test the application tracker with an in-memory SQLite DB."""

    @pytest.fixture
    async def tracker(self):
        t = ApplicationTracker(db_path=":memory:")
        await t.initialize()
        yield t
        await t.close()

    async def test_save_and_retrieve(self, tracker: ApplicationTracker):
        app = await tracker.save_application(
            job_id="test-123",
            source=JobSource.NAV,
            title="Backend Developer",
            employer="Test Corp",
            url="https://example.com/job/123",
            notes="Looks interesting",
        )
        assert app.id > 0
        assert app.status == ApplicationStatus.SAVED
        assert app.title == "Backend Developer"

        retrieved = await tracker.get_application(app.id)
        assert retrieved is not None
        assert retrieved.job_id == "test-123"
        assert retrieved.notes == "Looks interesting"

    async def test_update_status(self, tracker: ApplicationTracker):
        app = await tracker.save_application(
            job_id="test-456",
            source=JobSource.NAV,
            title="ML Engineer",
            employer="AI Corp",
        )

        updated = await tracker.update_status(
            application_id=app.id,
            status=ApplicationStatus.APPLIED,
            applied_date="2026-03-29",
        )

        assert updated is not None
        assert updated.status == ApplicationStatus.APPLIED
        assert updated.applied_date == "2026-03-29"

    async def test_list_applications_filter(self, tracker: ApplicationTracker):
        await tracker.save_application(
            job_id="j1", source=JobSource.NAV, title="Job A", employer="Corp A"
        )
        app2 = await tracker.save_application(
            job_id="j2", source=JobSource.NAV, title="Job B", employer="Corp B"
        )
        await tracker.update_status(app2.id, ApplicationStatus.APPLIED)

        all_apps = await tracker.list_applications()
        assert len(all_apps) == 2

        applied_only = await tracker.list_applications(status=ApplicationStatus.APPLIED)
        assert len(applied_only) == 1
        assert applied_only[0].title == "Job B"

    async def test_delete_application(self, tracker: ApplicationTracker):
        app = await tracker.save_application(
            job_id="del-1", source=JobSource.NAV, title="To Delete", employer="Corp"
        )
        assert await tracker.delete_application(app.id) is True
        assert await tracker.get_application(app.id) is None
        assert await tracker.delete_application(999) is False

    async def test_upsert_on_duplicate(self, tracker: ApplicationTracker):
        await tracker.save_application(
            job_id="dup-1", source=JobSource.NAV, title="Job", employer="Corp", notes="First"
        )
        app2 = await tracker.save_application(
            job_id="dup-1", source=JobSource.NAV, title="Job", employer="Corp", notes="Updated"
        )
        all_apps = await tracker.list_applications()
        assert len(all_apps) == 1
