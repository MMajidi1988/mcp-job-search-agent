"""Data models for job listings and application tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobSource(str, Enum):
    """Supported job board sources."""

    NAV = "nav"
    FINN = "finn"
    JOBBNORGE = "jobbnorge"


class ApplicationStatus(str, Enum):
    """Status of a job application."""

    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class JobListing(BaseModel):
    """A job listing from a job board."""

    id: str = Field(description="Unique identifier from the source")
    source: JobSource = Field(description="Which job board this listing came from")
    title: str = Field(description="Job title")
    employer: str = Field(description="Employer/company name")
    location: str = Field(default="", description="Job location")
    description: str = Field(default="", description="Job description text")
    url: str = Field(default="", description="Link to the original listing")
    published: str = Field(default="", description="Publication date")
    deadline: str = Field(default="", description="Application deadline")
    work_language: str = Field(default="", description="Required working language")
    occupation: str = Field(default="", description="Occupation category")


class TrackedApplication(BaseModel):
    """A job application being tracked by the user."""

    id: int = Field(description="Internal tracking ID")
    job_id: str = Field(description="Job listing ID from source")
    source: JobSource = Field(description="Job board source")
    title: str = Field(description="Job title")
    employer: str = Field(description="Company name")
    url: str = Field(default="", description="Link to listing")
    status: ApplicationStatus = Field(default=ApplicationStatus.SAVED)
    notes: str = Field(default="", description="User notes about this application")
    applied_date: str | None = Field(default=None, description="Date application was submitted")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SearchFilters(BaseModel):
    """Filters for job search queries."""

    query: str = Field(description="Search keywords")
    location: str = Field(default="", description="Filter by location (e.g. 'Oslo')")
    language: str = Field(default="", description="Filter by work language (e.g. 'Engelsk')")
    published_after: str = Field(default="", description="Only show jobs published after this date")
    max_results: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Max results (0 = no cap within fetch limits)",
    )
