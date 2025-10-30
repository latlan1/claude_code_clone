# Claude-Code-Clone — LangGraph CLI Coding agent

A compact, runnable Python project that reconstructs a demo agent using LangGraph, LangChain and Anthropic Claude. The project provides a terminal UI (Rich), local utility tools, and support for remote MCP servers. This README focuses on getting started with uv and common workflows.

## Key features
- Interactive agent driven by a state graph (user input → model response → tool use → back to user).
- Local tools: file reader and unit-test runner (Pytest wrapper).
- MCP integrations (DesktopCommander, sandbox Python MCP, DuckDuckGo search, GitHub MCP, and a Deno Docker image).
- Rich terminal UI and Mermaid workflow visualization.

## Prerequisites
- macOS / Linux / Windows with Python 3.11+ (project uses 3.13 bytecode in cache but is compatible with 3.11+).
- uv
- Docker (required to build/run the provided MCP Docker images- ensure that Docker Desktop is running).

## Quick start (using uv)
1. Initialize the uv workspace (creates .venv and metadata):

   uv init

2. Install dependencies from requirements.txt into the uv-managed venv:

   uv add -r requirements.txt

3. Sync uv's lock state (optional but recommended):

   uv sync

4. Activate the virtual environment created by uv (common path):

   source .venv/bin/activate

5. Run the agent CLI:

   uv run main.py

You can also run directly with Python if you prefer (after activating venv):

   python3 main.py

## Environment variables (.env)
Create a .env file in the project root or export env vars before running.
Example .env:

  ANTHROPIC_API_KEY=sk-ant-...
  GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...


## Useful uv commands and examples
- Run the main agent:
  uv run main.py

- Build the Deno MCP Docker image:
  docker build -t deno-docker:latest -f ./mcps/deno/Dockerfile .

## Common prompts to try
- "Show me the content of main.py"
- "What tools do you have?"
- "Read /absolute/path/to/requirements.txt"

## Available tools and MCPs
Local tools (bundled in tools/):
- file_read_tool.py — safely reads and returns file contents; handles permission and not-found errors. Not used because we decided to use Desktop Commander MCP instead
- run_unit_tests_tool.py — wrapper that runs pytest and returns results.

- Run a local tool (file reader):
  uv run tools/file_read_tool.py -- /absolute/path/to/file.txt

  (The file reader will print contents and handle common file errors.)

- Run unit-test runner (project provides a Pytest wrapper):
  uv run tools/run_unit_tests_tool.py

Remote MCPs (configured in repo):
- DesktopCommander MCP
- Pydantic AI run-python (sandbox Python MCP)
- DuckDuckGo search MCP
- GitHub MCP (runs as a Docker container; requires GITHUB_PERSONAL_ACCESS_TOKEN)
    ```
    command: docker 
    Arguments: run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN=GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server
    ```

## Inspecting the SQLite database
The project uses SQLite to store checkpoints. You can inspect the database using the sqlite3 command-line tool:

   sqlite3 checkpoints.db

Common SQLite commands:
- List all tables:
  .tables

- Show table schema:
  .schema your_table_name

- Export query results:
  .mode csv
  .output results.csv
  .headers on
  SELECT * FROM your_table_name;
  .output stdout

Exit sqlite3 with .quit or Ctrl+D

## Development notes
- The agent composes system + working-directory guidance to the Claude model. You can change model parameters in the code if you prefer a different LLM.
- Tools are designed to return structured ToolMessages so the StateGraph can route responses back to the model correctly.
- The terminal UI uses Rich for Markdown, code highlighting, and Mermaid output.

## Troubleshooting
- uv: If `uv run` fails, ensure you ran `uv init` and `uv add -r requirements.txt`, and that you activated the .venv.
- Missing API key: set ANTHROPIC_API_KEY in .env or export it before running.
- Docker errors: verify Docker is running and you have permission to run docker commands.
- Python version mismatch: use the Python version your virtual environment is created with; recreate the venv if needed.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Security
- This project reads files but does not execute arbitrary shell commands or user files. Review tools before trusting them with sensitive directories.