from mcp_job_search.cv_matcher import extract_cv_keywords, score_job_against_cv
from mcp_job_search.models import JobListing, JobSource


def test_extract_cv_keywords_basic() -> None:
    cv = "Python Java Spring Boot SQL PostgreSQL Docker RAG"
    kw = extract_cv_keywords(cv)
    assert "python" in kw
    assert "java" in kw
    assert "postgresql" in kw


def test_score_job_against_cv_prefers_overlap() -> None:
    cv_kw = extract_cv_keywords("Python Java Spring Boot Docker")
    job1 = JobListing(id="1", source=JobSource.NAV, title="Backend Developer (Java)", employer="A", description="Spring Boot")
    job2 = JobListing(id="2", source=JobSource.NAV, title="Frontend Developer", employer="B", description="React CSS")
    r1 = score_job_against_cv(job1, cv_kw, target_roles=["backend"])
    r2 = score_job_against_cv(job2, cv_kw, target_roles=["backend"])
    assert r1.score > r2.score

