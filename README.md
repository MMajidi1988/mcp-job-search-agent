# MCP Job Search Agent

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that lets MCP clients (Claude Code, Claude Desktop, etc.) search jobs and manage an application pipeline with SQLite.

## Features

- **Multi-source search**: NAV Arbeidsplassen + optional FINN.no (requires API key)
- **Deadline filtering**: omit listings with deadlines in the past
- **Job details**: fetch full NAV listing text
- **Application tracker**: save/update/list/delete applications (SQLite)
- **CV matching**: rank search results against a CV file (keyword-based, no external AI keys)

## Install

### Requirements

- Python 3.11+

### Setup (pip)

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install:

```bash
python -m pip install -e ".[dev]"
```

## Use with Claude Code (VS Code extension)

Register the server (run from the project root; venv activated):

```powershell
claude mcp add --transport stdio job-search -- .\.venv\Scripts\python.exe src\mcp_job_search\server.py
```

Verify health:

```powershell
claude mcp list
```

If `job-search` is connected, open the **Claude Code chat panel** and use natural language prompts. Claude will call MCP tools automatically.

## Tools

| Tool | Description |
|------|-------------|
| `search_jobs` | Search jobs across sources (`nav`, optional `finn`) |
| `get_job_details` | Get full NAV listing details (and minimal source routing) |
| `track_application` | Save a job to the tracker |
| `update_application_status` | Update tracker status / notes / applied date |
| `list_applications` | List tracked applications |
| `delete_application` | Delete a tracked application |
| `match_cv` | Search + rank results against a CV file (`cv.txt`) |

## Example prompts

Search:

```text
Search for software developer jobs in Oslo. Use sources nav and do not limit results.
```

Search + details (NAV):

```text
Search for "backend developer" jobs in Oslo (nav). Pick one relevant result and fetch its full description with get_job_details.
```

Track:

```text
Save the first result to my tracker and set notes: "High priority".
```

CV match:

```text
Match my CV file cv.txt against "backend developer OR software engineer OR AI engineer OR ML engineer" jobs in Norway (sources nav). Show top 20.
```

CV file:

- Create a local `cv.txt` (see `cv.example.txt`).
- `cv.txt` is ignored by default via `.gitignore`.

## Data sources

### NAV Arbeidsplassen (default)

- Uses NAV job feed API: [pam-stilling-feed](https://navikt.github.io/pam-stilling-feed/)
- Authentication uses NAV’s **public token endpoint** automatically

### FINN.no (optional)

FINN search uses the official Search API and requires an API key.

Set environment variable:

```powershell
$env:FINN_API_KEY = "YOUR_KEY"
```

Without `FINN_API_KEY`, `search_jobs` will skip Finn and include a note in the response.

## Project layout

```
.
├── src/mcp_job_search/
│   ├── server.py
│   ├── nav_client.py
│   ├── finn_client.py
│   ├── tracker.py
│   ├── models.py
│   ├── cv_matcher.py
│   └── job_utils.py
├── tests/
├── Visualization.md
├── example-prompts.md
├── pyproject.toml
└── README.md
```

## Development

```bash
python -m pytest
python -m ruff check src
python -m mypy src
```

## License

MIT. See `LICENSE`.
