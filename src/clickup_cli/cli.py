from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from clickup_cli.client import ClickUpClient, ClickUpError
from clickup_cli.config import (
    ConfigError,
    get_team_id,
    load_config,
    resolve_folder,
    resolve_list as resolve_list_id,
    resolve_space,
    template as config_template,
)

app = typer.Typer(help="ClickUp CLI", no_args_is_help=True)
console = Console()

team_app = typer.Typer(help="Team (workspace) operations", no_args_is_help=True)
space_app = typer.Typer(help="Space operations", no_args_is_help=True)
folder_app = typer.Typer(help="Folder operations", no_args_is_help=True)
lists_app = typer.Typer(help="List operations", no_args_is_help=True)
task_app = typer.Typer(help="Task operations", no_args_is_help=True)
auth_app = typer.Typer(help="Authentication operations", no_args_is_help=True)
config_app = typer.Typer(help="Config file operations", no_args_is_help=True)

app.add_typer(team_app, name="team")
app.add_typer(space_app, name="space")
app.add_typer(folder_app, name="folder")
app.add_typer(lists_app, name="lists")
app.add_typer(task_app, name="task")
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")


def _client() -> ClickUpClient:
    try:
        return ClickUpClient()
    except ClickUpError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from None


def _print(data: Any, *, raw: bool) -> None:
    if raw:
        console.print_json(json.dumps(data, default=str))
    else:
        console.print(data)


def _table(title: str, columns: list[tuple[str, str, str]]) -> Table:
    t = Table(title=title, show_lines=False)
    for name, style, justify in columns:
        t.add_column(name, style=style, justify=justify)
    return t


@lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    return load_config()


def _die(msg: str) -> None:
    console.print(f"[red]{msg}[/red]")
    raise typer.Exit(code=1)


def _parse_path(path: str) -> tuple[str, Optional[str], Optional[str]]:
    """Parse 'UTEM/DESARROLLO/Backlog' or 'UTEM//Backlog' (no-folder) into (space, folder, list)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], None, parts[1]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    _die(f"Invalid --path (expected SPACE/FOLDER/LIST or SPACE/LIST): {path}")


def _parse_task_ref(ref: str) -> str:
    """Strip ClickUp reference decoration: take first '_' segment, drop 'CU-' prefix.

    Examples:
      'abc12345'                          -> 'abc12345'
      'CU-abc12345'                       -> 'abc12345'
      'CU-abc12345_Task-Name_Assignee'    -> 'abc12345'
    """
    if "_" in ref:
        ref = ref.split("_", 1)[0]
    return ref[3:] if ref.upper().startswith("CU-") else ref


def _resolve_list(space: str | None, folder: str | None, list_ref: str) -> str:
    cfg = _cfg()
    if space:
        try:
            space_id = resolve_space(cfg, space)
        except ConfigError as e:
            _die(str(e))
    else:
        defaults = cfg.get("defaults") or {}
        space = defaults.get("space")
        space_id = resolve_space(cfg, space) if space else _die("--space required (or set defaults.space in config)")
    if not folder:
        defaults = cfg.get("defaults") or {}
        folder = defaults.get("folder")
    try:
        return resolve_list_id(cfg, space_id, folder, list_ref)
    except ConfigError as e:
        _die(str(e))


def _paginate_list_tasks(c: ClickUpClient, list_id: str, base_params: list[tuple[str, str]], limit: int) -> list[dict[str, Any]]:
    """ClickUp returns max 100 tasks per page. Loop until last_page."""
    all_tasks: list[dict[str, Any]] = []
    page = 0
    while len(all_tasks) < limit:
        params = list(base_params) + [("page", str(page))]
        data = c.get(f"/list/{list_id}/task", params=params)
        batch = data.get("tasks", [])
        all_tasks.extend(batch)
        if data.get("last_page", True) or not batch:
            break
        page += 1
    return all_tasks[:limit]


# ── config ────────────────────────────────────────────────────────────────────


@config_app.command("init")
def config_init(
    path: Path = typer.Option(".clickup-cli.yaml", "--path", "-p", help="Where to write the config"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing file"),
) -> None:
    """Scaffold a config file with the standard structure."""
    if path.exists() and not force:
        _die(f"{path} already exists. Use --force to overwrite.")
    path.write_text(config_template())
    console.print(f"[green]Wrote {path}[/green]")


@config_app.command("show")
def config_show(
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw YAML"),
) -> None:
    """Show the loaded config (or path if not found)."""
    cfg = _cfg()
    if not cfg:
        console.print("[yellow]No config loaded. Run `clickup-cli config init` first.[/yellow]")
        raise typer.Exit()
    console.print(f"[dim]Loaded from: {cfg.get('_path')}[/dim]")
    if raw:
        console.print_json(json.dumps({k: v for k, v in cfg.items() if k != "_path"}, default=str))
        return
    team = cfg.get("team") or {}
    spaces = cfg.get("spaces") or {}
    console.print(f"\n[bold]Team:[/bold] {team.get('name', '?')} ({team.get('id', '?')})")
    for sname, s in spaces.items():
        console.print(f"\n[bold cyan]Space:[/bold cyan] {sname} ({s.get('id')})")
        for fobj in (s.get("folders") or {}).items():
            fname, f = fobj
            console.print(f"  [bold]Folder:[/bold] {fname} ({f.get('id')})")
            for lname, l in (f.get("lists") or {}).items():
                lid = l["id"] if isinstance(l, dict) else l
                console.print(f"    • {lname} → {lid}")
        for lname, l in (s.get("lists") or {}).items():
            lid = l["id"] if isinstance(l, dict) else l
            console.print(f"  [bold]List:[/bold] {lname} → {lid}")


@config_app.command("path")
def config_path() -> None:
    """Show the config file path actually being used."""
    cfg = _cfg()
    if cfg.get("_path"):
        console.print(cfg["_path"])
    else:
        console.print("[yellow]No config file found[/yellow]")
        raise typer.Exit(code=1)


# ── team ──────────────────────────────────────────────────────────────────────


@team_app.command("list")
def team_list(
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """List all teams (workspaces) the token has access to."""
    with _client() as c:
        data = c.get("/team")
    if raw:
        _print(data, raw=True)
        return
    table = _table("Teams", [("ID", "cyan", "left"), ("Name", "bold", "left"), ("Members", "", "right")])
    for t in data.get("teams", []):
        table.add_row(str(t["id"]), t["name"], str(len(t.get("members", []))))
    console.print(table)


@team_app.command("show")
def team_show(
    team_id: str = typer.Argument(..., help="Team/Workspace ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show full team details including members."""
    with _client() as c:
        data = c.get(f"/team/{team_id}")
    _print(data, raw=raw)


# ── space ─────────────────────────────────────────────────────────────────────


@space_app.command("list")
def space_list(
    team_id: str = typer.Argument(..., help="Team/Workspace ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """List all spaces in a team (projects live here)."""
    with _client() as c:
        data = c.get(f"/team/{team_id}/space", params={"archived": "false"})
    if raw:
        _print(data, raw=True)
        return
    table = _table(
        "Spaces",
        [("ID", "cyan", "left"), ("Name", "bold", "left"), ("Private", "", "left")],
    )
    for s in data.get("spaces", []):
        table.add_row(str(s["id"]), s["name"], "yes" if s.get("private") else "no")
    console.print(table)


@space_app.command("show")
def space_show(
    space_id: str = typer.Argument(..., help="Space ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show full space details."""
    with _client() as c:
        data = c.get(f"/space/{space_id}")
    _print(data, raw=raw)


# ── folder ────────────────────────────────────────────────────────────────────


@folder_app.command("list")
def folder_list(
    space_id: str = typer.Argument(..., help="Space ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """List folders in a space (sprint containers)."""
    with _client() as c:
        data = c.get(f"/space/{space_id}/folder", params={"archived": "false"})
    if raw:
        _print(data, raw=True)
        return
    table = _table(
        "Folders",
        [("ID", "cyan", "left"), ("Name", "bold", "left"), ("Lists", "", "right")],
    )
    for f in data.get("folders", []):
        table.add_row(str(f["id"]), f["name"], str(len(f.get("lists", []))))
    console.print(table)


@folder_app.command("show")
def folder_show(
    folder_id: str = typer.Argument(..., help="Folder ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show folder details with all its lists."""
    with _client() as c:
        data = c.get(f"/folder/{folder_id}")
    _print(data, raw=raw)


# ── lists ─────────────────────────────────────────────────────────────────────


@lists_app.command("list")
def lists_list(
    folder_id: str = typer.Argument(..., help="Folder ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """List all lists (boards) in a folder."""
    with _client() as c:
        data = c.get(f"/folder/{folder_id}/list", params={"archived": "false"})
    if raw:
        _print(data, raw=True)
        return
    table = _table(
        "Lists",
        [
            ("ID", "cyan", "left"),
            ("Name", "bold", "left"),
            ("Task count", "", "right"),
            ("Status", "", "left"),
        ],
    )
    for lst in data.get("lists", []):
        statuses = ",".join(s.get("status", "") for s in lst.get("statuses", [])) or "-"
        table.add_row(str(lst["id"]), lst["name"], "-", statuses)
    console.print(table)


@lists_app.command("show")
def lists_show(
    list_id: str = typer.Argument(..., help="List ID"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show list details."""
    with _client() as c:
        data = c.get(f"/list/{list_id}")
    _print(data, raw=raw)


# ── auth ──────────────────────────────────────────────────────────────────────


@auth_app.command("whoami")
def auth_whoami(
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show the authenticated user (verifies token works)."""
    with _client() as c:
        data = c.get("/user")
    if raw:
        _print(data, raw=True)
        return
    console.print(
        f"[bold]{data.get('username', '?')}[/bold] <{data.get('email', '?')}>\n"
        f"ID: {data.get('id')}    Color: {data.get('color', '-')}"
    )


# ── task ──────────────────────────────────────────────────────────────────────


@task_app.command("list")
def task_list(
    list_ref: str = typer.Argument(..., help="List ID, name (e.g. Backlog), or path (UTEM/DESARROLLO/Backlog). Quote paths with spaces: \"UTEM/DESARROLLO/Weed Abatement\""),
    space: str = typer.Option(None, "--space", "-S", help="Space name (resolves via config)"),
    folder: str = typer.Option(None, "--folder", "-F", help="Folder name (resolves via config)"),
    statuses: list[str] = typer.Option(
        None, "--status", "-s", help="Filter by status (repeatable). e.g. --status open"
    ),
    subtasks: bool = typer.Option(False, "--subtasks", help="Include subtasks in the output"),
    limit: int = typer.Option(500, "--limit", help="Max tasks to fetch (auto-paginates 100/page)"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """List tasks in a list. Accepts list ID, name, or 'SPACE/FOLDER/LIST' path. Shows all statuses by default."""
    cfg = _cfg()
    if cfg and (not list_ref.isdigit() or "/" in list_ref or space or folder):
        if "/" in list_ref:
            sp, fo, lst = _parse_path(list_ref)
            list_id = _resolve_list(sp, fo, lst)
        else:
            list_id = _resolve_list(space, folder, list_ref)
    else:
        list_id = list_ref
    base_params: list[tuple[str, str]] = [("subtasks", "true")] if subtasks else []
    if statuses:
        base_params.extend([("statuses[]", s) for s in statuses])
    with _client() as c:
        tasks = _paginate_list_tasks(c, list_id, base_params, limit)
    if raw:
        console.print_json(json.dumps(tasks, default=str))
        return
    subtask_ids: set[str] = set()
    for t in tasks:
        for st in t.get("subtasks") or []:
            sid = st.get("id")
            if sid is not None:
                subtask_ids.add(str(sid))
    parents = [t for t in tasks if str(t.get("id")) not in subtask_ids]
    total_subtasks = sum(len(t.get("subtasks") or []) for t in parents)
    rows: list[tuple[str, str, str, str, str]] = []
    for t in parents:
        assignee = (t.get("assignees") or [{}])[0].get("username", "-") if t.get("assignees") else "-"
        due = t.get("due_date") or "-"
        if due != "-" and due is not None:
            from datetime import datetime, timezone

            due = datetime.fromtimestamp(int(due) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((str(t["id"]), t["name"], t.get("status", {}).get("status", "-"), assignee, str(due)))
        if subtasks:
            for st in t.get("subtasks") or []:
                st_assignee = (st.get("assignees") or [{}])[0].get("username", "-") if st.get("assignees") else "-"
                st_due = st.get("due_date") or "-"
                if st_due != "-" and st_due is not None:
                    from datetime import datetime, timezone

                    st_due = datetime.fromtimestamp(int(st_due) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append(
                    (str(st["id"]), f"  └ {st['name']}", st.get("status", {}).get("status", "-"), st_assignee, str(st_due))
                )
    title = f"Tasks ({len(parents)} parents" + (f", {total_subtasks} subtasks" if subtasks else "") + f") — list {list_id}"
    table = _table(
        title,
        [
            ("ID", "cyan", "left"),
            ("Name", "bold", "left"),
            ("Status", "", "left"),
            ("Assignee", "", "left"),
            ("Due", "", "left"),
        ],
    )
    for r in rows:
        table.add_row(*r)
    console.print(table)


@task_app.command("show")
def task_show(
    task_id: str = typer.Argument(
        ...,
        help="Task ID. Numeric (e.g. 901312345) or with CU- prefix (CU-86ajc6cd9 — auto-stripped)",
    ),
    team_id: str = typer.Option(
        None, "--team", "-t", help="Team ID (defaults to config team.id for custom task IDs)"
    ),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Show full task details. Strips CU- prefix and CU-XXX_Name_Assignee decoration automatically."""
    clean_id = _parse_task_ref(task_id)
    is_custom = not clean_id.isdigit()
    params: list[tuple[str, str]] = []
    if is_custom:
        if not team_id:
            team_id = get_team_id(_cfg())
        if not team_id:
            _die("--team required for custom task IDs (or set team.id in config)")
        params = [("custom_task_ids", "true"), ("team_id", team_id)]
    with _client() as c:
        data = c.get(f"/task/{clean_id}", params=params or None)
    _print(data, raw=raw)


@task_app.command("summary")
def task_summary(
    task_id: str = typer.Argument(
        ...,
        help="Task ID. Numeric (e.g. 901312345) or custom (CU-86ajc6cd9 — auto-stripped)",
    ),
    team_id: str = typer.Option(
        None, "--team", "-t", help="Team ID (defaults to config team.id for custom task IDs)"
    ),
) -> None:
    """Compact content-focused view: priority, dates, custom fields, description."""
    from datetime import datetime, timezone

    clean_id = _parse_task_ref(task_id)
    is_custom = not clean_id.isdigit()
    params: list[tuple[str, str]] = []
    if is_custom:
        if not team_id:
            team_id = get_team_id(_cfg())
        if not team_id:
            _die("--team required for custom task IDs (or set team.id in config)")
        params = [("custom_task_ids", "true"), ("team_id", team_id)]
    with _client() as c:
        data = c.get(f"/task/{clean_id}", params=params or None)
    creator = data.get("creator") or {}
    assignees = data.get("assignees") or []
    parent = data.get("parent")
    parent_str = str(parent) if parent else "-"
    list_ = data.get("list") or {}
    folder = data.get("folder") or {}
    priority = (data.get("priority") or {}).get("priority") or "-"
    assignees_str = ", ".join(a.get("username", "?") for a in assignees) or "-"
    tags = data.get("tags") or []
    tags_str = ", ".join(t.get("name", "?") for t in tags) or "-"

    def _ts(ms: Any) -> str:
        if not ms:
            return "-"
        try:
            return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return "-"

    due = _ts(data.get("due_date"))
    start = _ts(data.get("start_date"))
    created = _ts(data.get("date_created"))
    updated = _ts(data.get("date_updated"))
    closed = _ts(data.get("date_closed"))

    console.print(
        f"\n[bold]Task:[/bold] {data.get('id')}    [dim]URL:[/dim] {data.get('url', '-')}\n"
        f"[bold]Name:[/bold] {data.get('name', '?')}\n"
        f"[bold]Status:[/bold] {data.get('status', {}).get('status', '-')}    "
        f"[bold]Priority:[/bold] {priority}\n"
        f"[bold]Parent:[/bold] {parent_str}\n"
        f"[bold]Creator:[/bold] {creator.get('username', '-')} <{creator.get('email', '-')}>\n"
        f"[bold]Assignees:[/bold] {assignees_str}\n"
        f"[bold]Tags:[/bold] {tags_str}\n"
        f"[bold]Location:[/bold] {folder.get('name', '?')} / {list_.get('name', '?')}\n"
        f"[bold]Due:[/bold] {due}    [bold]Start:[/bold] {start}    "
        f"[bold]Created:[/bold] {created}    [bold]Updated:[/bold] {updated}"
        + (f"    [bold]Closed:[/bold] {closed}" if closed != "-" else "")
        + "\n"
    )

    cfs = data.get("custom_fields") or []
    populated = []
    for cf in cfs:
        name = cf.get("name", "?")
        ctype = cf.get("type")
        val = cf.get("value")
        if val is None or val == "":
            continue
        if ctype == "drop_down":
            options = (cf.get("type_config") or {}).get("options") or []
            try:
                resolved = options[int(val)]["name"]
            except (IndexError, ValueError, KeyError):
                resolved = str(val)
            populated.append(f"  • {name}: {resolved}")
        elif ctype in ("number", "currency"):
            populated.append(f"  • {name}: {val}")
        elif ctype == "date":
            populated.append(f"  • {name}: {_ts(val)}")
        else:
            populated.append(f"  • {name}: {val}")
    if populated:
        console.print("[bold]Custom fields:[/bold]")
        console.print("\n".join(populated))
        console.print()

    desc = (data.get("text_content") or data.get("description") or "").strip()
    if desc:
        console.print("[bold]Description:[/bold]")
        console.print("─" * 60)
        console.print(desc)
        console.print("─" * 60)


@task_app.command("update")
def task_update(
    task_id: str = typer.Argument(
        ...,
        help="Task ID. Numeric (e.g. 901312345) or custom (CU-86ajc6cd9 — auto-stripped)",
    ),
    status: str = typer.Option(None, "--status", "-s", help="New status name (must exist in the task's list)"),
    name: str = typer.Option(None, "--name", help="Rename the task"),
    team_id: str = typer.Option(
        None, "--team", "-t", help="Team ID (defaults to config team.id for custom task IDs)"
    ),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON response"),
) -> None:
    """Update task fields (status, name, ...). Strips CU- prefix and CU-XXX_Name_Assignee decoration."""
    clean_id = _parse_task_ref(task_id)
    is_custom = not clean_id.isdigit()
    params: list[tuple[str, str]] = []
    if is_custom:
        if not team_id:
            team_id = get_team_id(_cfg())
        if not team_id:
            _die("--team required for custom task IDs (or set team.id in config)")
        params = [("custom_task_ids", "true"), ("team_id", team_id)]
    body: dict[str, Any] = {}
    if status:
        body["status"] = status
    if name:
        body["name"] = name
    if not body:
        _die("Nothing to update. Pass --status and/or --name.")
    with _client() as c:
        data = c.put(f"/task/{clean_id}", json=body, params=params or None)
    console.print(
        f"[green]Updated {data.get('id')}[/green] → status: [bold]{data.get('status', {}).get('status', '-')}[/bold]"
    )
    if raw:
        _print(data, raw=True)


@task_app.command("search")
def task_search(
    name: str = typer.Argument(..., help="Substring to match in task name (case-insensitive)"),
    list_ref: str = typer.Option(..., "--list", "-l", help="List ID, name, or path (SPACE/FOLDER/LIST). Quote paths with spaces."),
    space: str = typer.Option(None, "--space", "-S", help="Space name (resolves via config)"),
    folder: str = typer.Option(None, "--folder", "-F", help="Folder name (resolves via config)"),
    include_closed: bool = typer.Option(False, "--closed", help="Include closed tasks"),
    limit: int = typer.Option(500, "--limit", help="Max tasks to scan (auto-paginates 100/page)"),
) -> None:
    """Search tasks by name substring within a list (client-side filter)."""
    cfg = _cfg()
    if cfg and (not list_ref.isdigit() or "/" in list_ref or space or folder):
        if "/" in list_ref:
            sp, fo, lst = _parse_path(list_ref)
            list_id = _resolve_list(sp, fo, lst)
        else:
            list_id = _resolve_list(space, folder, list_ref)
    else:
        list_id = list_ref
    base_params: list[tuple[str, str]] = [("include_closed", "true")] if include_closed else []
    with _client() as c:
        tasks = _paginate_list_tasks(c, list_id, base_params, limit)
    needle = name.lower()
    matches = [t for t in tasks if needle in t.get("name", "").lower()]
    if not matches:
        console.print(f"[yellow]No tasks matching '{name}' in list {list_id}[/yellow]")
        raise typer.Exit()
    table = _table(
        f"Matches ({len(matches)}) — list {list_id}",
        [
            ("ID", "cyan", "left"),
            ("Name", "bold", "left"),
            ("Status", "", "left"),
            ("Assignee", "", "left"),
        ],
    )
    for t in matches:
        assignee = (t.get("assignees") or [{}])[0].get("username", "-") if t.get("assignees") else "-"
        table.add_row(str(t["id"]), t["name"], t.get("status", {}).get("status", "-"), assignee)
    console.print(table)


@task_app.command("find")
def task_find(
    team_id: str = typer.Option(
        None,
        "--team",
        "-t",
        help="Team/Workspace ID (defaults to team.id in config)",
    ),
    status: str = typer.Option(
        "in progress",
        "--status",
        "-s",
        help="Status to filter (e.g. 'in progress', 'to do', 'open')",
    ),
    name: str = typer.Option(None, "--name", "-n", help="Substring to match in task name"),
    assignee: str = typer.Option(None, "--assignee", "-a", help="Assignee username (substring)"),
    limit: int = typer.Option(100, "--limit", help="Max tasks to fetch across all pages"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON"),
) -> None:
    """Exploratory: list in-progress (or any status) tasks workspace-wide with full location."""
    if not team_id:
        team_id = get_team_id(_cfg())
    if not team_id:
        _die("--team required (or set team.id in config)")
    needle_name = name.lower() if name else None
    needle_user = assignee.lower() if assignee else None
    all_tasks: list[dict[str, Any]] = []
    with _client() as c:
        page = 0
        while len(all_tasks) < limit:
            params: list[tuple[str, str]] = [
                ("statuses[]", status),
                ("page", str(page)),
                ("include_closed", "true"),
                ("custom_task_ids", "true"),
            ]
            data = c.get(f"/team/{team_id}/task", params=params)
            batch = data.get("tasks", [])
            all_tasks.extend(batch)
            if data.get("last_page", True) or not batch:
                break
            page += 1
    all_tasks = all_tasks[:limit]
    if needle_name:
        all_tasks = [t for t in all_tasks if needle_name in t.get("name", "").lower()]
    if needle_user:
        all_tasks = [
            t
            for t in all_tasks
            if any(needle_user in (a.get("username", "") or "").lower() for a in t.get("assignees", []) or [])
        ]
    if not all_tasks:
        console.print(
            f"[yellow]No tasks matched (status={status}, name={name}, assignee={assignee})[/yellow]"
        )
        raise typer.Exit()
    if raw:
        _print(all_tasks, raw=True)
        return
    table = _table(
        f"In-progress tasks ({len(all_tasks)}) — workspace: {team_id}",
        [
            ("Custom ID", "magenta", "left"),
            ("Name", "bold", "left"),
            ("List", "cyan", "left"),
            ("Folder", "cyan", "left"),
            ("Assignee", "", "left"),
        ],
    )
    for t in all_tasks:
        lst = t.get("list") or {}
        folder = lst.get("folder") or {}
        folder_name = folder.get("name", "—") if folder else "—"
        assignee = "-"
        if t.get("assignees"):
            assignee = t["assignees"][0].get("username", "-")
        table.add_row(
            t.get("custom_id", "-") or "-",
            t["name"],
            lst.get("name", "-"),
            folder_name,
            assignee,
        )
    console.print(table)


if __name__ == "__main__":
    app()
