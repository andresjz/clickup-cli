# clickup-cli

## Stack
- Python 3.12+, [uv](https://docs.astral.sh/uv/) (uv_build backend), typer, httpx, rich, pyyaml, python-dotenv
- Single package `src/clickup_cli/`: `cli.py` (commands), `client.py` (HTTP), `config.py` (yaml resolver)
- Console entry: `clickup-cli` -> `clickup_cli.cli:app` (`pyproject.toml:18`)

## Setup
```bash
cp .env.example .env        # set CLICKUP_TOKEN
uv sync
uv run clickup-cli config init  # scaffolds .clickup-cli.yaml
```
- `.env` and `.clickup-cli.yaml` are gitignored. Never commit them.
- Config resolution: `$CLICKUP_CONFIG` > `./.clickup-cli.yaml` > `~/.config/clickup-cli/config.yaml` (`src/clickup_cli/config.py:10-13`).
- Config maps `team.id` + `spaces -> folders -> lists` (names -> IDs). Run `uv run clickup-cli config show` to inspect.

## Run
```bash
uv run clickup-cli <cmd>            # via uv
.venv/bin/clickup-cli <cmd>         # after uv sync, no uv overhead
```

## No tests, no lint, no typecheck, no CI
- No `tests/`, no pytest/ruff/mypy config, no `.github/`, no Makefile, no pre-commit.
- Don't invent `pytest`/`ruff run`/`mypy` steps. Verify code by reading it + running the CLI.
- `uv.lock` exists, `uv sync` is the only setup step needed.

## Repo quirks
- **No test suite.** Live API calls only. Smoke-test with `uv run clickup-cli auth whoami` (no config needed beyond token).
- **Custom task IDs require `team.id` in config.** `task show/summary/update` use ClickUp's `custom_task_ids` lookup; falls back to `--team` flag if config missing (`cli.py:436-447`).
- **Task ref parsing** (`cli.py:87-97`): accepts `abc12345`, `CU-abc12345`, or `CU-abc12345_Name_Assignee` (first `_` segment, strip `CU-` prefix).
- **List ref parsing** (`cli.py:75-84`): accepts raw ID, name, or `SPACE/FOLDER/LIST` / `SPACE/LIST` path. `--space`/`--folder` flags supplement name-only refs.
- **Defaults:** `defaults.space` / `defaults.folder` in config fill in when flags omitted (`cli.py:108-113`).
- **Pagination handled in CLI** (`cli.py:120-132`): ClickUp max 100/page; `_paginate_list_tasks` loops on `last_page`.
- **Config file is workspace structure, not secrets**, but still gitignored. Members/IDs leak via this file.
- **Token sent only to** `https://api.clickup.com/api/v2/` (`client.py:11`). `CLICKUP_TOKEN` is read in `client.py:23` after `load_dotenv()` at module import.

## Adding commands
Edit `src/clickup_cli/cli.py`. Use `ClickUpClient.get/put` for HTTP, `resolve_*` helpers from `config.py` for name -> ID, `_parse_path`/`_parse_task_ref` for refs, `typer.Option` for flags, `--raw` for JSON output. Mirror existing `*_app.command(...)` blocks per resource.
