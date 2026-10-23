# uBiblio MCP server (stdio)

Lets an AI assistant (e.g. Claude Code) search your library, add books by ISBN, change shelves and mark books as verified. It only calls the uBiblio JSON API (`/api/v1`) with a token; it has no database access and no tools that delete anything.

Tools: `search_books`, `get_book`, `list_to_complete`, `stats` (read) and `add_book_by_isbn`, `update_book`, `mark_verified` (need a **write** token).

## Setup

1. In uBiblio: menu **Tokeny API** (`/api_tokens`) -> create a token. Choose `odczyt` (read) unless the assistant should change data.
2. Python 3.11+ venv for the server (separate from the app):

   ```
   python -m venv .venv-mcp
   .venv-mcp\Scripts\python -m pip install -r mcp_server/requirements-mcp.txt
   ```

3. Register it in Claude Code (stdio; syntax checked with `claude mcp add --help` on 2026-10-23):

   ```
   claude mcp add ubiblio -e UBIBLIO_URL=https://ubiblio.byst.re -e UBIBLIO_TOKEN=ubt_... -- C:\path\to\repo\.venv-mcp\Scripts\python.exe C:\path\to\repo\mcp_server\server.py
   ```

   The token ends up in Claude Code's local MCP configuration; revoke it on `/api_tokens` if that file leaks.

## Tests

```
.venv-mcp\Scripts\python -m pytest mcp_server/tests -c NUL --rootdir mcp_server
```

Manual check: MCP Inspector (`npx @modelcontextprotocol/inspector`) with the same command and environment.

## Notes

- Built for `mcp` 2.3.0 (`from mcp.server import MCPServer`; in older 1.x SDKs the class was `FastMCP`). Pinned in `requirements-mcp.txt`.
- Book summaries come from Google Books/Wikipedia/BN and may contain text that looks like instructions; `get_book` leaves the summary out unless asked, and the server instructions tell the model to treat book data as data.
- Remote MCP for the Claude apps (phase 7c, OAuth) is not implemented.
