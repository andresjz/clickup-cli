# ClickUp CLI

Tiny Python CLI for ClickUp API. Built with `uv`, `typer`, `httpx`, `rich`, `pyyaml`.

## Setup

```bash
cp .env.example .env
# edit .env: CLICKUP_TOKEN=pk_your_personal_api_token_here
uv sync

# Scaffold a config file with your workspace IDs
uv run clickup-cli config init
uv run clickup-cli config show
```

The config file (`.clickup-cli.yaml`) maps **names → IDs** so you don't have
to walk the hierarchy every time. **This file is gitignored** because it
contains workspace structure (team/space/folder/list IDs and member info).
Use `config init` to scaffold it locally and edit with your own IDs:

```yaml
team:
  id: "<TEAM_ID>"
  name: "<WORKSPACE_NAME>"

spaces:
  <SPACE_NAME>:
    id: "<SPACE_ID>"
    folders:
      <FOLDER_NAME>:
        id: "<FOLDER_ID>"
        lists:
          <LIST_NAME>: "<LIST_ID>"
```

Resolution order: `$CLICKUP_CONFIG` > `./.clickup-cli.yaml` >
`~/.config/clickup-cli/config.yaml`.

## Usage

```bash
# Walk the hierarchy (no config needed)
uv run clickup-cli auth whoami
uv run clickup-cli team list
uv run clickup-cli space list <TEAM_ID>
uv run clickup-cli folder list <SPACE_ID>
uv run clickup-cli lists list <FOLDER_ID>
uv run clickup-cli task list <LIST_ID>

# Or use names (config-resolved, no IDs to remember)
uv run clickup-cli task list Backlog --space <SPACE_NAME> --folder <FOLDER_NAME>

# Path shortcut: SPACE/FOLDER/LIST
uv run clickup-cli task list <SPACE_NAME>/<FOLDER_NAME>/Backlog
uv run clickup-cli task search "keyword" --list "<SPACE_NAME>/<FOLDER_NAME>/Backlog"

# Find tasks workspace-wide (uses team.id from config)
uv run clickup-cli task find --status "in progress"
uv run clickup-cli task find --status "in progress" --assignee <username>

# Content-focused view of a single ticket
uv run clickup-cli task summary <CUSTOM_ID>

# Look up / update a ticket
uv run clickup-cli task show <CUSTOM_ID>
uv run clickup-cli task update <CUSTOM_ID> --status "in progress"
```

### Task reference formats

The CLI accepts task IDs in any of these forms (auto-stripped):

| Input | Resolved |
|---|---|
| `86ajc6cd9` | `86ajc6cd9` |
| `CU-86ajc6cd9` | `86ajc6cd9` |
| `CU-86ajc6cd9_Name_Assignee` | `86ajc6cd9` |

## Hierarchy

```
Workspace (team)
└── Space (project)
    ├── Folder (sprint container, optional)
    │   └── List (sprint / board)
    │       └── Task (ticket)
    └── List (no folder)
        └── Task
```

## Commands

```bash
uv run clickup-cli auth whoami            # verify token
uv run clickup-cli config init|show|path   # manage .clickup-cli.yaml
uv run clickup-cli team list|show
uv run clickup-cli space list|show
uv run clickup-cli folder list|show
uv run clickup-cli lists list|show
uv run clickup-cli task list|show|summary|search|find|update

# Common flags
--raw    # raw JSON output
--subtasks  # include subtasks in task list (deduplicated)
--status   # filter by status (repeatable)
```

## Security

- **Never commit `.env`** — it holds your `CLICKUP_TOKEN`.
- **`.clickup-cli.yaml` is gitignored** — it leaks workspace structure
  (team/space IDs, member user IDs). Keep it local; share via your
  password manager if you must.
- The CLI sends the token only to `https://api.clickup.com/api/v2/`.

## Add more endpoints

Edit `src/clickup_cli/cli.py` and add a new typer command. Use
`ClickUpClient` for HTTP calls. See ClickUp API docs: https://clickup.com/api
