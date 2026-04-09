"""Output formatting and display utilities for notebooklm_automation."""

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()
err_console = Console(stderr=True)


READY_STATUSES = {"ready", "available", "success", "present", "1", "2", "true", "yes"}


# ==================== Display Functions ====================


def print_section(title: str, message: str) -> None:
    """Print a formatted section with title."""
    console.print(Panel(message, title=title, border_style="blue"))


def print_error(message: str) -> None:
    """Print error message to stderr."""
    err_console.print(f"[red]Error:[/red] {message}")


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[green]OK[/green] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[yellow]WARN[/yellow] {message}")


def print_auth_error(profile_name: str, error: Exception) -> None:
    """Print authentication error message."""
    console.print(
        Panel(
            f"[bold red]Authentication expired[/bold red]\n\n"
            f"Profile: [cyan]{profile_name}[/cyan]\n"
            f"Details: {error}\n\n"
            f"Run [bold]nlm login --profile {profile_name}[/bold] and retry.",
            title="Auth Error",
            border_style="red",
        )
    )


def print_quota_check(
    profile_name: str,
    notebook_id: str,
    plan_name: str,
    plan_limit: int,
    existing_count: int,
    requested_count: int | None = None,
) -> None:
    """Print quota check information."""
    projected_total = existing_count + (requested_count or 0)
    available_quota = max(plan_limit - existing_count, 0)

    body_lines = [
        f"[bold]Profile:[/bold] {profile_name}",
        f"[bold]Notebook ID:[/bold] {notebook_id}",
        f"[bold]Plan:[/bold] {plan_name} (max {plan_limit} sources)",
        f"[bold]Existing sources:[/bold] {existing_count}",
        f"[bold]Available upload quota:[/bold] {available_quota}",
    ]
    if requested_count is not None:
        body_lines.extend(
            [
                f"[bold]Requested new uploads:[/bold] {requested_count}",
                f"[bold]Projected total:[/bold] {projected_total}",
            ]
        )

    console.print(Panel("\n".join(body_lines), title="Quota Check", border_style="blue"))


def get_status_style(status: str) -> str:
    """Get color style for status."""
    normalized = status.strip().lower()
    if normalized in READY_STATUSES:
        return "green"
    if normalized in {"failed", "fail", "error"}:
        return "red"
    if normalized in {"skipped", "duplicate", "existing"}:
        return "yellow"
    return "cyan"


def render_sources_table(
    sources: list[dict],
    title: str = "Sources",
    status_label: str = "available",
) -> None:
    """Render a formatted table of sources."""
    table = Table(title=title, show_lines=False, header_style="bold magenta")
    table.add_column("Source ID", style="dim", no_wrap=True)
    table.add_column("File Name", style="bold")
    table.add_column("Status", style="green", no_wrap=True)

    if not sources:
        console.print(table)
        return

    for source in sources:
        file_name = str(source.get("title", "Untitled"))
        raw_status = source.get("status", status_label)
        status_value = str(raw_status)
        status_style = get_status_style(status_value)
        if raw_status == 2 or status_value.strip().lower() in READY_STATUSES:
            status_display = "[green]✓[/green]"
        else:
            status_display = f"[{status_style}]{status_value}[/{status_style}]"
        table.add_row(
            str(source.get("id", "unknown")),
            file_name,
            status_display,
        )

    console.print(table)


# ==================== Text Formatting Functions ====================


def get_model_version(result: Any) -> str | None:
    """Extract model version from result."""
    if isinstance(result, dict):
        for key in (
            "model_version",
            "modelVersion",
            "model_name",
            "modelName",
            "version",
        ):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def extract_answer_text(result: Any) -> str:
    """Extract answer text from query result."""
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        for key in ("answer", "response", "text", "content", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value

    try:
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception:
        return str(result)


def format_query_result(
    notebook_id: str,
    source_ids: list[str],
    source_file_names: list[str],
    answer_text: str,
    run_timestamp: str,
    query_id: str | None = None,
    response_id: str | None = None,
    model_version: str | None = None,
) -> str:
    """Format a query result as markdown."""
    source_name_block = "\n".join(f"- {name}" for name in source_file_names) if source_file_names else "- all sources"
    model_version_line = f"- Model version: {model_version}\n" if model_version else ""
    query_id_line = f"- Query ID: {query_id or 'n/a'}\n"
    response_id_line = f"- Response ID: {response_id or 'n/a'}\n"
    body = (
        f"# NotebookLM Query Result\n\n"
        f"- Run timestamp: {run_timestamp}\n"
        f"- Notebook ID: {notebook_id}\n"
        f"{query_id_line}"
        f"{response_id_line}"
        f"- Sources: {', '.join(source_ids) if source_ids else 'all'}\n\n"
        f"- Source file name(s):\n{source_name_block}\n\n"
        f"{model_version_line}"
        f"## Response\n\n{answer_text}\n"
    )
    return body
