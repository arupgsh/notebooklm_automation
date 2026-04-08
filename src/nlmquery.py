import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.core.errors import ClientAuthenticationError
from notebooklm_tools.services.chat import query_start, query_status


console = Console()


def print_auth_error(profile_name: str, error: Exception) -> None:
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


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()
    cleaned = cleaned.strip(".")
    return cleaned or "untitled"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_source_output_path(output_dir: Path, source_file_name: str, source_id: str) -> Path:
    filename = f"{sanitize_filename(source_file_name)}__{sanitize_filename(source_id)}.md"
    return output_dir / filename


def build_notebook_output_path(output_dir: Path, notebook_id: str) -> Path:
    return output_dir / f"{sanitize_filename(notebook_id)}.md"


def get_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_query_file(query_file: Path) -> str:
    if not query_file.exists() or not query_file.is_file():
        raise SystemExit(f"Error: Query file not found: {query_file}")

    content = query_file.read_text(encoding="utf-8").strip()
    if not content:
        raise SystemExit(f"Error: Query file is empty: {query_file}")
    return content


def create_output_dir(output_folder: str | None) -> Path:
    output_dir = Path(output_folder) if output_folder else Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_source_file_name(source: dict) -> str:
    title = str(source.get("title") or source.get("name") or source.get("id") or "source")
    return Path(title).stem or "source"


def get_source_display_name(source: dict) -> str:
    title = str(source.get("title") or source.get("name") or source.get("id") or "source")
    return title or "source"


def get_model_version(result: Any) -> str | None:
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


def get_authenticated_profile(profile_name: str):
    manager = AuthManager(profile_name)
    if not manager.profile_exists():
        raise SystemExit(
            f"Error: Profile '{profile_name}' not found. Run: nlm login --profile {profile_name}"
        )

    try:
        profile = manager.load_profile()
    except Exception as exc:
        raise SystemExit(
            f"Error: Failed to load profile '{profile_name}': {exc}\n"
            f"Run: nlm login --profile {profile_name}"
        ) from exc

    if not profile.cookies:
        raise SystemExit(
            f"Error: Profile '{profile_name}' has no cookies. "
            f"Run: nlm login --profile {profile_name}"
        )

    return profile


def create_client(profile_name: str) -> NotebookLMClient:
    profile = get_authenticated_profile(profile_name)
    return NotebookLMClient(
        cookies=profile.cookies,
        csrf_token=profile.csrf_token or "",
        session_id=profile.session_id or "",
        build_label=profile.build_label or "",
    )


def extract_answer_text(result: Any) -> str:
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


def save_query_result(
    output_path: Path,
    notebook_id: str,
    source_ids: list[str],
    source_file_names: list[str],
    answer_text: str,
    run_timestamp: str,
    query_id: str | None = None,
    response_id: str | None = None,
    model_version: str | None = None,
) -> None:
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
    output_path.write_text(body, encoding="utf-8")


def wait_for_query_result(query_id: str) -> dict[str, Any]:
    while True:
        try:
            status = query_status(query_id)
        except Exception as exc:
            raise SystemExit(f"Error: {exc}") from exc
        if status["status"] == "completed":
            return status["result"] or {}
        if status["status"] == "error":
            error_message = status.get("error") or f"Query {query_id} failed"
            raise SystemExit(f"Error: {error_message}")
        time.sleep(1)


def query_single_source(
    client: NotebookLMClient,
    notebook_id: str,
    source: dict,
    query_text: str,
    output_dir: Path,
    run_timestamp: str,
) -> Path | None:
    source_id = str(source.get("id", ""))
    source_file_name = get_source_file_name(source)
    output_path = build_source_output_path(output_dir, source_file_name, source_id)

    if output_path.exists():
        console.print(f"[yellow]Skipping[/yellow] existing output: {output_path.name}")
        return None

    start_result = query_start(
        client,
        notebook_id,
        query_text,
        source_ids=[source_id],
    )
    query_id = start_result["query_id"]
    console.print(f"[dim]Started query {query_id} for {source_file_name}[/dim]")

    with console.status(f"[dim]Waiting for {source_file_name}...[/dim]", spinner="dots"):
        result = wait_for_query_result(query_id)

    answer = extract_answer_text(result)
    model_version = get_model_version(result)
    response_id = None
    if isinstance(result, dict):
        response_id = result.get("conversation_id") or result.get("response_id")

    save_query_result(
        output_path,
        notebook_id,
        [source_id],
        [get_source_display_name(source)],
        answer,
        run_timestamp,
        query_id=query_id,
        response_id=response_id,
        model_version=model_version,
    )
    return output_path


def cmd_query(args: argparse.Namespace) -> None:
    query_file = Path(args.query_file)
    query_text = read_query_file(query_file)
    output_dir = create_output_dir(args.output_folder)
    run_timestamp = get_timestamp()

    with create_client(args.profile) as client:
        sources = client.get_notebook_sources_with_types(args.notebook_id)
        source_map = {
            str(source.get("id")): source
            for source in sources
            if source.get("id")
        }

        if args.mode == "single":
            if not args.source_id:
                raise SystemExit("Error: --source-id is required when --mode single")

            source = source_map.get(args.source_id)
            if not source:
                raise SystemExit(f"Error: Source ID not found in notebook: {args.source_id}")

            source_name = get_source_file_name(source)
            console.print(f"Generating output for [bold]{source_name}[/bold]...")
            output_path = query_single_source(
                client,
                args.notebook_id,
                source,
                query_text,
                output_dir,
                run_timestamp,
            )
            if output_path is not None:
                print(f"Saved: {output_path}")
            return

        if args.mode == "each":
            if not source_map:
                raise SystemExit("Error: No sources found in notebook")

            saved_paths: list[Path] = []
            skipped_count = 0
            total_sources = len(source_map)
            for index, source in enumerate(source_map.values(), start=1):
                source_name = get_source_file_name(source)
                console.print(f"[{index}/{total_sources}] Generating output for [bold]{source_name}[/bold]...")
                try:
                    output_path = query_single_source(
                        client,
                        args.notebook_id,
                        source,
                        query_text,
                        output_dir,
                        run_timestamp,
                    )
                    if output_path is None:
                        skipped_count += 1
                    else:
                        saved_paths.append(output_path)
                except Exception as exc:
                    source_id = str(source.get("id", "unknown"))
                    print(f"Failed source {source_id}: {exc}")

            if not saved_paths and skipped_count:
                print(f"All {skipped_count} output file(s) already existed in: {output_dir}")
                return

            if not saved_paths:
                raise SystemExit("Error: No outputs were saved")

            print(f"Saved {len(saved_paths)} file(s) to: {output_dir}")
            return

        # mode == all
        source_ids = list(source_map.keys())
        output_path = build_notebook_output_path(output_dir, args.notebook_id)
        if output_path.exists():
            console.print(f"[yellow]Skipping[/yellow] existing output: {output_path.name}")
            return

        console.print(f"[1/1] Generating output for [bold]{len(source_ids)} source(s) together[/bold]...")
        start_result = query_start(
            client,
            args.notebook_id,
            query_text,
            source_ids=source_ids if source_ids else None,
        )
        query_id = start_result["query_id"]
        console.print(f"[dim]Started query {query_id} for notebook {args.notebook_id}[/dim]")

        with console.status("[dim]Waiting for notebook response...[/dim]", spinner="dots"):
            result = wait_for_query_result(query_id)

        answer = extract_answer_text(result)
        model_version = get_model_version(result)
        response_id = None
        if isinstance(result, dict):
            response_id = result.get("conversation_id") or result.get("response_id")

        save_query_result(
            output_path,
            args.notebook_id,
            source_ids,
            [get_source_display_name(source) for source in source_map.values()],
            answer,
            run_timestamp,
            query_id=query_id,
            response_id=response_id,
            model_version=model_version,
        )
        print(f"Saved: {output_path}")


def cmd_merge(args: argparse.Namespace) -> None:
    output_dir = create_output_dir(args.output_folder)
    output_file = Path(args.output_file) if args.output_file else output_dir / "merged_output.md"

    files = sorted(
        p
        for p in output_dir.glob("*.md")
        if p.is_file() and p.name != output_file.name
    )

    if not files:
        raise SystemExit(f"Error: No markdown files found in {output_dir}")

    sections: list[str] = ["# Merged Query Outputs\n"]
    for path in files:
        content = path.read_text(encoding="utf-8")
        sections.append(f"\n## {path.name}\n\n{content}\n")

    output_file.write_text("\n".join(sections), encoding="utf-8")
    print(f"Merged {len(files)} file(s) into: {output_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nlmquery",
        description="Query NotebookLM sources using instructions from a markdown file",
    )
    subparsers = parser.add_subparsers(dest="command")

    query_parser = subparsers.add_parser("query", help="Run query modes against notebook sources")
    query_parser.add_argument("--notebook-id", required=True, help="Notebook ID")
    query_parser.add_argument("--profile", default="default", help="Auth profile (default: default)")
    query_parser.add_argument(
        "--mode",
        choices=["single", "each", "all"],
        required=True,
        help="single: one source by id, each: all sources one-by-one, all: all sources together",
    )
    query_parser.add_argument("--source-id", help="Source ID (required for --mode single)")
    query_parser.add_argument(
        "--query-file",
        default="query.md",
        help="Path to query instructions markdown file (default: query.md)",
    )
    query_parser.add_argument(
        "--output-folder",
        help="Output folder path (default: ./output)",
    )
    query_parser.set_defaults(func=cmd_query)

    merge_parser = subparsers.add_parser("merge", help="Merge markdown outputs from output folder")
    merge_parser.add_argument(
        "--output-folder",
        help="Folder containing output markdown files (default: ./output)",
    )
    merge_parser.add_argument(
        "--output-file",
        help="Merged output file path (default: <output-folder>/merged_output.md)",
    )
    merge_parser.set_defaults(func=cmd_merge)

    return parser


def main() -> None:
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except ClientAuthenticationError as exc:
        profile_name = getattr(args, "profile", "default")
        print_auth_error(profile_name, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
