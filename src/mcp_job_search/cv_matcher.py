"""CV matching utilities (keyword-based, no external API keys).

This is intentionally simple and explainable:
- Extract keywords from CV
- Score job listing text by weighted keyword overlap + title boosts
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import JobListing

_WORD_RE = re.compile(r"[A-Za-z0-9+#.\-]{2,}")


def _normalize_token(tok: str) -> str:
    return tok.strip().lower()


def tokenize(text: str) -> list[str]:
    return [_normalize_token(t) for t in _WORD_RE.findall(text or "")]


def extract_cv_keywords(cv_text: str) -> set[str]:
    """Extract a set of normalized keywords from a CV text blob."""
    tokens = tokenize(cv_text)
    # Keep distinct tokens; drop very common noise words.
    stop = {
        "and",
        "or",
        "the",
        "a",
        "an",
        "with",
        "to",
        "of",
        "in",
        "for",
        "on",
        "as",
        "at",
        "by",
        "from",
        "into",
        "this",
        "that",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "you",
        "i",
        "my",
        "your",
    }
    return {t for t in tokens if t not in stop}


@dataclass(frozen=True)
class MatchResult:
    score: float
    matched_keywords: list[str]
    title_boosts: list[str]


def score_job_against_cv(
    job: JobListing,
    cv_keywords: set[str],
    *,
    target_roles: list[str] | None = None,
) -> MatchResult:
    """Compute a simple relevance score and explanation for a job listing."""
    target_roles = target_roles or []

    haystack = " ".join(
        [
            job.title or "",
            job.employer or "",
            job.location or "",
            job.description or "",
            job.occupation or "",
        ]
    )
    job_tokens = set(tokenize(haystack))

    matched = sorted(cv_keywords.intersection(job_tokens))

    # Base score: overlap count with diminishing returns.
    base = 0.0
    for i in range(min(len(matched), 40)):
        base += 1.0 / (1.0 + 0.08 * i)

    boosts: list[str] = []
    title_low = (job.title or "").lower()

    # Role/title boosts
    for role in target_roles:
        r = role.strip().lower()
        if r and r in title_low:
            base += 3.0
            boosts.append(f"title contains '{role}'")

    # Strong skill boosts if present
    strong = {"python", "java", "spring", "springboot", "spring-boot", "sql", "postgresql", "docker"}
    strong_hits = sorted(strong.intersection(job_tokens).intersection(cv_keywords))
    if strong_hits:
        base += 1.5
        boosts.append(f"strong skills: {', '.join(strong_hits[:6])}")

    # Normalize to a 0-100-ish range for readability (cap).
    score = min(100.0, base * 4.0)
    return MatchResult(score=score, matched_keywords=matched[:25], title_boosts=boosts[:5])

