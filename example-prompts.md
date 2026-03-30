# Example prompts (after the MCP server is connected)

Use these in **Claude Desktop**, **Cursor**, or any client that has loaded **Job Search Agent**. The model will call tools like `search_jobs` and `track_application` for you.

---

## Important: where to type these prompts

**Do not** paste example prompts into the **same terminal** where `python -m mcp_job_search.server` is running.

That terminal is **not** a chat box. The server reads **raw stdin** and expects **JSON-RPC** messages (the MCP wire protocol). If you type or paste English text there, you get errors like:

`Invalid JSON: expected value at line 1 column 1` with `input_value='Search NAV for software...'`

**Do** type the prompts in the **chat UI** of an MCP client that **starts** your server for you (Claude Desktop, Cursor with MCP configured, etc.). The client sends protocol on stdin; you never paste prompts into that pipe yourself.

---

## 1. Simple search (good first try)

```text
Search NAV for software developer jobs in Oslo. Show me up to 5 results with titles, employers, and links.
```

---

## 2. Search with language filter

```text
Find jobs matching "data engineer" where the working language is English. Limit to 10 results.
```

---

## 3. Full flow: search → details → save to tracker

```text
Search for "Python backend" jobs in Bergen. Pick the most relevant one, fetch full details with get_job_details using its job ID, then add it to my tracker with track_application (include title, employer, and URL from the listing). Tell me the tracking ID you got back.
```

---

## 4. Pipeline review

```text
List all my tracked applications. For anything still in "saved" status, suggest whether I should apply this week.
```

---

## 5. Update status after you applied

```text
I applied to the job you saved as tracking ID 3 today (2026-03-29). Update its status to "applied" and set the applied date.
```

*(Replace `3` and the date with your real tracking ID and date.)*

---

## 6. Using the server’s built-in MCP prompts

If your client supports **MCP prompts**, you can invoke:

- **`job_search_strategy`** — pass role and location (e.g. *software engineer*, *Oslo*).
- **`application_review`** — no args; it asks the model to review your pipeline via `list_applications`.

In Claude Desktop this may appear under prompts/resources for the connected server.

---

## Tips

- **Job IDs** for `get_job_details` come from **`search_jobs`** output (the UUID-style `ID:` line).
- If search returns nothing, try **broader keywords** or **clear the location** filter — NAV is filtered from a recent feed, not a full search engine.
- The server must be **running via the client’s MCP config**; a manual terminal session does not talk to Claude unless the client is configured to spawn that same command.
