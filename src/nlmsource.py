import argparse
import sys
from pathlib import Path

from notebooklm_tools.core.exceptions import NLMError
from notebooklm_tools.services import sources as sources_service

from helpers.auth import create_client
from helpers.cli import run_cli_command
from helpers.formatter import (
    console,
    err_console,
    print_error,
    print_quota_check,
    print_section,
    print_success,
    print_warning,
    render_sources_table,
)
from helpers.utils import PLAN_LIMITS, collect_pdf_files


def cmd_upload(args: argparse.Namespace) -> None:
    pdf_files = collect_pdf_files(Path(args.pdf_folder))
    plan_limit = PLAN_LIMITS[args.plan]

    print_section(
        "Upload",
        f"[bold]PDFs found:[/bold] {len(pdf_files)}",
    )

    with create_client(args.profile) as client:
        existing_sources = client.get_notebook_sources_with_types(args.notebook_id)
        existing_ids = {str(source.get("id")) for source in existing_sources if source.get("id")}
        existing_by_title = {
            str(source.get("title", "")).strip().lower(): source
            for source in existing_sources
            if source.get("title")
        }

        files_to_upload: list[Path] = []
        skipped_files: list[Path] = []
        already_present_sources: list[dict] = []
        for file_path in pdf_files:
            existing_match = existing_by_title.get(file_path.name.strip().lower())
            if existing_match:
                skipped_files.append(file_path)
                already_present_sources.append(existing_match)
            else:
                files_to_upload.append(file_path)

        existing_count = len(existing_sources)
        requested_count = len(files_to_upload)
        projected_total = existing_count + requested_count
        available_quota = max(plan_limit - existing_count, 0)

        print_quota_check(
            args.profile,
            args.notebook_id,
            args.plan,
            plan_limit,
            existing_count,
            requested_count,
        )
        if skipped_files:
            print_section("Already Present", f"Matched files already in the notebook: {len(skipped_files)}")
            render_sources_table(already_present_sources, title="Already Present", status_label="present")

        if projected_total > plan_limit:
            print_error(
                "Upload would exceed the plan limit. "
                f"Limit={plan_limit}, projected={projected_total}."
            )
            print_warning(
                "Reduce files to upload, remove existing sources, or use --plan pro/ultra."
            )
            sys.exit(1)

        if not files_to_upload:
            print_success("No new files to upload.")
            return

        console.print()
        success_count = 0
        success_ids: set[str] = set()
        failed_files: list[Path] = []
        for file_path in files_to_upload:
            console.print(f"[bold blue]Uploading:[/bold blue] {file_path.name}")
            try:
                result = sources_service.add_source(
                    client,
                    notebook_id=args.notebook_id,
                    source_type="file",
                    file_path=str(file_path),
                    wait=True,
                )
                source_id = result.get("source_id", "unknown")
                title = result.get("title", file_path.name)
                print_success(f"{title} is ready")
                console.print(f"  [dim]Source ID:[/dim] {source_id}")
                if source_id != "unknown":
                    success_ids.add(str(source_id))
                success_count += 1
            except NLMError as exc:
                print_error(f"{file_path.name}")
                err_console.print(f"  [red]Details:[/red] {exc}")
                failed_files.append(file_path)
            except Exception as exc:
                print_error(f"{file_path.name}")
                err_console.print(f"  [red]Details:[/red] {exc}")
                failed_files.append(file_path)

        # Cleanup stage after all uploads: remove any newly-created source
        # that did not complete successfully.
        if failed_files:
            console.print()
            print_section("Cleanup", "Running cleanup for failed uploads")
            try:
                post_sources = client.get_notebook_sources_with_types(args.notebook_id)
                post_by_id = {
                    str(source.get("id")): source
                    for source in post_sources
                    if source.get("id")
                }
                new_ids = set(post_by_id.keys()) - existing_ids
                cleanup_ids = new_ids - success_ids

                if not cleanup_ids:
                    print("  No cleanup targets found")
                else:
                    cleaned = 0
                    for source_id in sorted(cleanup_ids):
                        try:
                            client.delete_source(source_id)
                            cleaned += 1
                            title = post_by_id.get(source_id, {}).get("title", "Untitled")
                            print_success(f"Cleanup removed {title} ({source_id})")
                        except Exception as exc:
                            print_error(f"Cleanup failed for {source_id}: {exc}")
                    console.print(f"[bold]Cleanup complete:[/bold] {cleaned}/{len(cleanup_ids)} removed")
            except Exception as exc:
                print_error(f"Cleanup stage failed: {exc}")

        console.print()
        print_section(
            "Upload Summary",
            f"[bold]Ready:[/bold] {success_count}/{len(files_to_upload)}\n"
            f"[bold]Skipped:[/bold] {len(skipped_files)}\n"
            f"[bold]Failed:[/bold] {len(failed_files)}",
        )

        # List all sources currently available in the notebook.
        console.print()
        print_section("Notebook Sources", "Current sources in the notebook")
        sources = client.get_notebook_sources_with_types(args.notebook_id)
        render_sources_table(sources, title="Sources currently in notebook", status_label="available")


def cmd_list(args: argparse.Namespace) -> None:
    plan_limit = PLAN_LIMITS[args.plan]
    print_section("List", "Notebook source listing")

    with create_client(args.profile) as client:
        sources = client.get_notebook_sources_with_types(args.notebook_id)
        print_quota_check(
            args.profile,
            args.notebook_id,
            args.plan,
            plan_limit,
            len(sources),
        )

    if not sources:
        print_success("No sources found")
        return

    render_sources_table(sources, title="Sources", status_label="available")


def cmd_remove(args: argparse.Namespace) -> None:
    print_section("Remove", "Source removal")

    with create_client(args.profile) as client:
        source_ids: list[str]
        if args.remove_all:
            if not args.notebook_id:
                print_error("--notebook-id is required when using --all")
                sys.exit(1)

            notebook_sources = client.get_notebook_sources_with_types(args.notebook_id)
            source_ids = [str(source.get("id")) for source in notebook_sources if source.get("id")]
            print_quota_check(
                args.profile,
                args.notebook_id,
                "standard",
                PLAN_LIMITS["standard"],
                len(notebook_sources),
            )
            console.print(f"[bold]Removing all sources:[/bold] {len(source_ids)}")
            if not source_ids:
                print_success("No sources found to remove")
                return
        else:
            source_ids = args.source_ids or []
            console.print(f"[bold]Removing sources:[/bold] {len(source_ids)}")

        removed_count = 0
        for source_id in source_ids:
            console.print(f"[blue]Removing:[/blue] {source_id}")
            try:
                client.delete_source(source_id)
                print_success(f"Removed {source_id}")
                removed_count += 1
            except NLMError as exc:
                print_error(source_id)
                err_console.print(f"  [red]Details:[/red] {exc}")
            except Exception as exc:
                print_error(source_id)
                err_console.print(f"  [red]Details:[/red] {exc}")

    console.print(f"[bold]Remove complete:[/bold] {removed_count}/{len(source_ids)} removed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nlmsource",
        description="Source management CLI for NotebookLM",
    )
    subparsers = parser.add_subparsers(dest="command")

    upload_parser = subparsers.add_parser("upload", help="Upload PDFs from a folder")
    upload_parser.add_argument(
        "--notebook-id",
        type=str,
        required=True,
        help="NotebookLM notebook ID (required)",
    )
    upload_parser.add_argument(
        "--pdf-folder",
        type=str,
        required=True,
        help="Path to folder containing PDF files (required)",
    )
    upload_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Auth profile name (default: default)",
    )
    upload_parser.add_argument(
        "--plan",
        type=str,
        default="standard",
        choices=["standard", "pro", "ultra"],
        help="NotebookLM plan for source limit checks (default: standard)",
    )
    upload_parser.set_defaults(func=cmd_upload)

    list_parser = subparsers.add_parser("list", help="List notebook sources")
    list_parser.add_argument(
        "--notebook-id",
        type=str,
        required=True,
        help="NotebookLM notebook ID (required)",
    )
    list_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Auth profile name (default: default)",
    )
    list_parser.add_argument(
        "--plan",
        type=str,
        default="standard",
        choices=["standard", "pro", "ultra"],
        help="NotebookLM plan for upload quota display (default: standard)",
    )
    list_parser.set_defaults(func=cmd_list)

    remove_parser = subparsers.add_parser("remove", help="Remove one or more sources")
    remove_group = remove_parser.add_mutually_exclusive_group(required=True)
    remove_group.add_argument(
        "--source-ids",
        nargs="+",
        help="One or more source IDs to remove",
    )
    remove_group.add_argument(
        "--all",
        dest="remove_all",
        action="store_true",
        help="Remove all sources from a notebook (requires --notebook-id)",
    )
    remove_parser.add_argument(
        "--notebook-id",
        type=str,
        help="NotebookLM notebook ID (required with --all)",
    )
    remove_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Auth profile name (default: default)",
    )
    remove_parser.set_defaults(func=cmd_remove)

    return parser


def main() -> None:
    parser = build_parser()
    run_cli_command(parser)


if __name__ == "__main__":
    main()