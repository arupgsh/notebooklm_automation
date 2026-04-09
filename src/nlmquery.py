import argparse
import sys
import time
from pathlib import Path
from typing import Any

from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.services.chat import query_start, query_status

from helpers.auth import create_client
from helpers.cli import run_cli_command
from helpers.formatter import (
    console,
    extract_answer_text,
    get_model_version,
)
from helpers.utils import (
    build_notebook_output_path,
    build_source_output_path,
    create_output_dir,
    get_source_display_name,
    get_source_file_name,
    get_timestamp,
    read_query_file,
    save_query_result,
)




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
    run_cli_command(parser)


if __name__ == "__main__":
    main()
