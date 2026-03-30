"""MCP Job Search Agent — Main server module.

An MCP server that provides tools for searching Norwegian job boards
and tracking job applications. Designed to work with Claude Desktop,
Claude Code, or any MCP-compatible client.

Usage:
    # Run directly
    python -m mcp_job_search.server

    # Or via the installed entry point
    mcp-job-search

    # Install in Claude Desktop
    uv run mcp install src/mcp_job_search/server.py
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

# When this file is executed as a script (e.g. `python src/mcp_job_search/server.py`)
# relative imports (from .models) fail because `__package__` is not set.
# Claude stdio MCP configs often run the file directly, so we support both:
try:
    from .cv_matcher import extract_cv_keywords, score_job_against_cv
    from .models import ApplicationStatus, JobListing, JobSource
    from .finn_client import FinnJobClient
    from .nav_client import NAVJobClient
    from .tracker import ApplicationTracker
except ImportError:  # pragma: no cover
    from mcp_job_search.cv_matcher import extract_cv_keywords, score_job_against_cv
    from mcp_job_search.finn_client import FinnJobClient
    from mcp_job_search.models import ApplicationStatus, JobListing, JobSource
    from mcp_job_search.nav_client import NAVJobClient
    from mcp_job_search.tracker import ApplicationTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Initialize MCP Server ───────────────────────────────────────────
mcp = FastMCP(
    "Job Search Agent",
    dependencies=["httpx", "aiosqlite", "pydantic"],
)

# ── Shared State ────────────────────────────────────────────────────
nav_client = NAVJobClient()
finn_client = FinnJobClient()
tracker = ApplicationTracker()


def _parse_sources(sources: str) -> set[str]:
    return {p.strip().lower() for p in sources.split(",") if p.strip()}


async def _search_jobs_raw(
    *,
    query: str,
    location: str,
    language: str,
    sources: str,
    max_results: int,
    exclude_expired_deadlines: bool,
) -> tuple[list[JobListing], list[str], set[str] | None]:
    wanted = _parse_sources(sources)
    allowed = {"nav", "finn", "jobbnorge"}
    if not wanted:
        wanted = {"nav", "finn"}
    invalid = wanted - allowed
    if invalid:
        return [], [f"Unknown source(s): {', '.join(sorted(invalid))}. Use: nav, finn, jobbnorge."], None

    jobs: list[JobListing] = []
    notes: list[str] = []

    if "nav" in wanted:
        jobs.extend(
            await nav_client.search_jobs(
                query=query,
                location=location,
                language=language,
                max_results=max_results,
                exclude_expired_deadlines=exclude_expired_deadlines,
            )
        )
    if "finn" in wanted:
        if not finn_client.has_api_key:
            notes.append("Finn.no: skipped (set environment variable FINN_API_KEY — see FINN API docs).")
        else:
            jobs.extend(
                await finn_client.search_jobs(
                    query=query,
                    location=location,
                    language=language,
                    max_results=max_results,
                    exclude_expired_deadlines=exclude_expired_deadlines,
                )
            )
    if "jobbnorge" in wanted:
        notes.append("Jobbnorge: not implemented yet (coming in a future release).")

    if max_results > 0:
        jobs = jobs[:max_results]

    return jobs, notes, wanted


# ── Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def search_jobs(
    query: str,
    location: str = "",
    language: str = "",
    sources: str = "nav,finn",
    max_results: int = 0,
    exclude_expired_deadlines: bool = True,
) -> str:
    """Search job listings across Norwegian sources (NAV + optional FINN.no).

    Args:
        query: Keywords to search for (e.g. 'software engineer', 'data scientist').
        location: Filter by location (e.g. 'Oslo', 'Bergen', 'Trondheim').
        language: Filter by working language (e.g. 'Engelsk' for English, 'Norsk') — NAV only.
        sources: Comma-separated list: nav, finn, jobbnorge (jobbnorge not implemented yet).
        max_results: Cap on total matches (0 = no cap within safety limits).
        exclude_expired_deadlines: If true, omit listings whose application deadline has passed.

    Returns:
        Formatted list of matching job listings with key details.
    """
    try:
        jobs, notes, wanted = await _search_jobs_raw(
            query=query,
            location=location,
            language=language,
            sources=sources,
            max_results=max_results,
            exclude_expired_deadlines=exclude_expired_deadlines,
        )
        if wanted is None:
            return "\n".join(notes)
    except Exception as e:
        logger.error("Job search failed: %s", e)
        return f"Error searching for jobs: {e}"

    if not jobs:
        msg = f"No jobs found matching '{query}'" + (f" in {location}" if location else "")
        msg += ". Try broadening your search terms."
        if notes:
            msg += "\n\n" + "\n".join(notes)
        return msg

    lines = [f"Found {len(jobs)} job(s) (sources: {', '.join(sorted(wanted))}) for '{query}':\n"]
    for i, job in enumerate(jobs, 1):
        lines.append(f"**{i}. {job.title}**")
        lines.append(f"   Employer: {job.employer}")
        if job.location:
            lines.append(f"   Location: {job.location}")
        if job.deadline:
            lines.append(f"   Deadline: {job.deadline}")
        if job.work_language:
            lines.append(f"   Language: {job.work_language}")
        lines.append(f"   ID: {job.id} (source: {job.source.value})")
        if job.url:
            lines.append(f"   URL: {job.url}")
        lines.append("")
    if notes:
        lines.append("\n".join(notes))

    return "\n".join(lines)


@mcp.tool()
async def match_cv(
    cv_path: str = "cv.txt",
    query: str = "",
    location: str = "",
    sources: str = "nav,finn",
    max_results: int = 0,
    top_k: int = 15,
) -> str:
    """Search jobs and rank them against your CV (keyword-based).

    No external embedding API keys required.

    Args:
        cv_path: Path to a text file containing your CV (default: cv.txt).
        query: Optional search keywords (recommended).
        location: Optional location filter.
        sources: Comma-separated list: nav,finn,jobbnorge.
        max_results: Cap on how many jobs to fetch before scoring (0 = no cap within safety limits).
        top_k: How many best matches to return.

    Returns:
        Ranked list of job listings with match score and explanation.
    """
    try:
        with open(cv_path, "r", encoding="utf-8") as f:
            cv_text = f.read()
    except OSError as e:
        return f"Could not read CV file at '{cv_path}': {e}"

    cv_keywords = extract_cv_keywords(cv_text)

    try:
        jobs, notes, wanted = await _search_jobs_raw(
            query=query,
            location=location,
            language="",
            sources=sources,
            max_results=max_results,
            exclude_expired_deadlines=True,
        )
        if wanted is None:
            return "\n".join(notes)
    except Exception as e:
        logger.error("CV match search failed: %s", e)
        return f"Error searching for jobs: {e}"

    if not jobs and query.strip():
        try:
            jobs, notes2, wanted2 = await _search_jobs_raw(
                query="",
                location=location,
                language="",
                sources=sources,
                max_results=max_results,
                exclude_expired_deadlines=True,
            )
            if wanted2 is not None:
                wanted = wanted2
            notes.extend(notes2)
            notes.append(
                "Note: keyword filter returned no jobs; re-ran without keywords so CV ranking can still run."
            )
        except Exception as e:
            logger.error("CV match fallback search failed: %s", e)
            return f"Error searching for jobs: {e}"

    if not jobs:
        msg = "No jobs found to match against your CV."
        if notes:
            msg += "\n\n" + "\n".join(notes)
        return msg

    # Role hints for scoring (English + common tech terms).
    target_roles = [
        "software engineer",
        "backend",
        "python",
        "java",
        "rag",
        "computer vision",
        "ai",
        "ml",
        "machine learning",
        "developer",
        "utvikler",
    ]

    scored = []
    for job in jobs:
        r = score_job_against_cv(job, cv_keywords, target_roles=target_roles)
        scored.append((r.score, job, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, min(top_k, 50))]

    lines = [
        f"Matched {len(jobs)} job(s) against CV `{cv_path}` (sources: {', '.join(sorted(wanted))}).",
        f"Showing top {len(top)}:\n",
    ]
    for i, (score, job, r) in enumerate(top, 1):
        lines.append(f"**{i}. {job.title}** (score: {score:.1f}/100) — {job.employer}")
        if job.location:
            lines.append(f"   Location: {job.location}")
        if job.deadline:
            lines.append(f"   Deadline: {job.deadline}")
        lines.append(f"   Source/ID: {job.source.value} / {job.id}")
        if job.url:
            lines.append(f"   URL: {job.url}")
        if r.title_boosts:
            lines.append(f"   Boosts: {', '.join(r.title_boosts)}")
        if r.matched_keywords:
            lines.append(f"   Matched keywords: {', '.join(r.matched_keywords)}")
        lines.append("")
    if notes:
        lines.append("\n".join(notes))

    return "\n".join(lines)

@mcp.tool()
async def get_job_details(job_id: str, source: str = "nav") -> str:
    """Get full details of a specific job listing (NAV UUID or Finn ad id).

    Args:
        job_id: Listing id from search_jobs (NAV UUID, or Finn numeric id).
        source: 'nav' or 'finn'. Finn details require FINN_API_KEY and use the Ad API.

    Returns:
        Detailed job information including full description.
    """
    try:
        src = JobSource(source.lower())
    except ValueError:
        return f"Invalid source '{source}'. Use 'nav', 'finn', or 'jobbnorge'."

    if src == JobSource.FINN:
        if not finn_client.has_api_key:
            return (
                "Finn job details require FINN_API_KEY. "
                "Alternatively, open the listing URL from search_jobs in your browser."
            )
        return (
            f"Finn listing `{job_id}`: open the job URL from search results, "
            f"or use FINN Ad API with your key (not yet wired in this tool)."
        )

    if src == JobSource.JOBBNORGE:
        return "Jobbnorge details are not implemented yet."

    try:
        details = await nav_client.get_ad_details(job_id)
    except Exception as e:
        logger.error("Failed to fetch job details: %s", e)
        return f"Error fetching job details: {e}"

    if details is None:
        return (
            f"Job with ID '{job_id}' not found via NAV API. "
            f"If you have a UUID, try opening: https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}"
        )

    ad = details.get("ad_content")
    if not ad:
        st = details.get("status", "unknown")
        return (
            f"NAV returned metadata only for `{job_id}` (status: {st}). "
            f"Full text may be unavailable. Open: https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}"
        )
    title = ad.get("title", "Unknown")
    employer = ad.get("employer", {})
    employer_name = employer.get("name", "Unknown") if isinstance(employer, dict) else str(employer)

    lines = [
        f"# {title}",
        f"**Employer:** {employer_name}",
    ]

    if location := ad.get("locationList"):
        loc_str = ", ".join(
            loc.get("city", loc.get("municipal", "")) for loc in location if isinstance(loc, dict)
        )
        lines.append(f"**Location:** {loc_str}")

    if deadline := ad.get("applicationDue"):
        lines.append(f"**Deadline:** {deadline}")

    if work_lang := ad.get("workLanguage"):
        lines.append(f"**Working language:** {work_lang}")

    if extent := ad.get("extent"):
        lines.append(f"**Extent:** {extent}")

    if start_time := ad.get("starttime"):
        lines.append(f"**Start date:** {start_time}")

    lines.append("")

    if description := ad.get("description"):
        lines.append("## Description")
        lines.append(description)

    if qualifications := ad.get("qualifications"):
        lines.append("\n## Qualifications")
        lines.append(qualifications)

    if apply_url := ad.get("applicationUrl") or ad.get("sourceurl"):
        lines.append(f"\n**Apply here:** {apply_url}")

    return "\n".join(lines)


@mcp.tool()
async def track_application(
    job_id: str,
    source: str = "nav",
    title: str = "",
    employer: str = "",
    url: str = "",
    notes: str = "",
) -> str:
    """Save a job listing to your application tracker.

    Args:
        job_id: The job ID from search results.
        source: Job board source ('nav' or 'jobbnorge').
        title: Job title.
        employer: Company name.
        url: Link to the job listing.
        notes: Any notes about this application.

    Returns:
        Confirmation with the tracking details.
    """
    try:
        job_source = JobSource(source)
    except ValueError:
        return f"Invalid source '{source}'. Use 'nav', 'finn', or 'jobbnorge'."

    await tracker.initialize()
    app = await tracker.save_application(
        job_id=job_id,
        source=job_source,
        title=title,
        employer=employer,
        url=url,
        notes=notes,
    )

    return (
        f"Saved to tracker!\n"
        f"  Tracking ID: {app.id}\n"
        f"  Title: {app.title}\n"
        f"  Employer: {app.employer}\n"
        f"  Status: {app.status.value}\n"
        f"  Notes: {app.notes or '(none)'}"
    )


@mcp.tool()
async def update_application_status(
    application_id: int,
    status: str,
    notes: str = "",
    applied_date: str = "",
) -> str:
    """Update the status of a tracked application.

    Args:
        application_id: The tracking ID (from track_application or list_applications).
        status: New status — one of: saved, applied, interviewing, offer, rejected, withdrawn.
        notes: Optional updated notes.
        applied_date: Date you applied (e.g. '2026-03-15').

    Returns:
        Updated application details.
    """
    try:
        app_status = ApplicationStatus(status)
    except ValueError:
        valid = ", ".join(s.value for s in ApplicationStatus)
        return f"Invalid status '{status}'. Valid options: {valid}"

    await tracker.initialize()
    app = await tracker.update_status(
        application_id=application_id,
        status=app_status,
        notes=notes or None,
        applied_date=applied_date or None,
    )

    if app is None:
        return f"No application found with ID {application_id}."

    return (
        f"Updated application #{app.id}:\n"
        f"  Title: {app.title}\n"
        f"  Employer: {app.employer}\n"
        f"  Status: {app.status.value}\n"
        f"  Notes: {app.notes or '(none)'}\n"
        f"  Applied: {app.applied_date or 'Not yet'}"
    )


@mcp.tool()
async def list_applications(
    status: str = "",
    limit: int = 20,
) -> str:
    """List all tracked job applications, optionally filtered by status.

    Args:
        status: Filter by status (saved/applied/interviewing/offer/rejected/withdrawn),
                or leave empty for all.
        limit: Maximum number of applications to show.

    Returns:
        Formatted list of tracked applications.
    """
    app_status = None
    if status:
        try:
            app_status = ApplicationStatus(status)
        except ValueError:
            valid = ", ".join(s.value for s in ApplicationStatus)
            return f"Invalid status '{status}'. Valid options: {valid}"

    await tracker.initialize()
    apps = await tracker.list_applications(status=app_status, limit=limit)

    if not apps:
        filter_msg = f" with status '{status}'" if status else ""
        return f"No tracked applications{filter_msg}."

    # Summary counts
    status_counts: dict[str, int] = {}
    for app in apps:
        status_counts[app.status.value] = status_counts.get(app.status.value, 0) + 1

    lines = [f"Tracked applications ({len(apps)} total):\n"]

    # Show summary
    summary = " | ".join(f"{s}: {c}" for s, c in sorted(status_counts.items()))
    lines.append(f"Summary: {summary}\n")

    for app in apps:
        emoji = {
            "saved": "📌",
            "applied": "📨",
            "interviewing": "🎯",
            "offer": "🎉",
            "rejected": "❌",
            "withdrawn": "🔙",
        }.get(app.status.value, "•")

        lines.append(f"{emoji} **#{app.id} — {app.title}** at {app.employer}")
        lines.append(f"   Status: {app.status.value}")
        if app.applied_date:
            lines.append(f"   Applied: {app.applied_date}")
        if app.notes:
            lines.append(f"   Notes: {app.notes}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def delete_application(application_id: int) -> str:
    """Remove an application from the tracker.

    Args:
        application_id: The tracking ID to delete.

    Returns:
        Confirmation message.
    """
    await tracker.initialize()
    deleted = await tracker.delete_application(application_id)

    if deleted:
        return f"Application #{application_id} has been removed from tracking."
    return f"No application found with ID {application_id}."


# ── Resources ───────────────────────────────────────────────────────


@mcp.resource("jobsearch://status-options")
def get_status_options() -> str:
    """List all valid application status values."""
    return "\n".join(
        f"- {s.value}: {s.name}" for s in ApplicationStatus
    )


@mcp.resource("jobsearch://sources")
def get_sources() -> str:
    """List all supported job board sources."""
    return "\n".join(
        f"- {s.value}: {s.name}" for s in JobSource
    )


# ── Prompts ─────────────────────────────────────────────────────────


@mcp.prompt()
def job_search_strategy(role: str, location: str = "Oslo") -> str:
    """Generate a job search strategy prompt.

    Args:
        role: The type of role you're looking for (e.g. 'software engineer').
        location: Preferred location (default: Oslo).
    """
    return f"""Help me create a job search strategy. I'm looking for a {role} position
in {location}, Norway.

Please:
1. Search for relevant jobs using the search_jobs tool
2. Summarize the most promising opportunities
3. Suggest related search terms I should also try
4. Recommend which listings I should save to my tracker"""


@mcp.prompt()
def application_review() -> str:
    """Review your current application pipeline."""
    return """Please review my job application pipeline:

1. List all my tracked applications using list_applications
2. Identify any that need follow-up (applied more than a week ago)
3. Suggest next steps for each application
4. Give me an overall summary of my search progress"""


# ── Entry Point ─────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
