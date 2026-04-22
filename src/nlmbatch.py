import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from notebooklm_tools.services import sources as sources_service
from notebooklm_tools.services.chat import query_start

from helpers.auth import create_client
from helpers.cli import run_cli_command
from helpers.formatter import console, extract_answer_text, get_model_version
from helpers.utils import (
    create_output_dir,
    get_source_display_name,
    get_timestamp,
    read_query_file,
    save_query_result,
)
from nlmquery import query_single_source, wait_for_query_result

REQUIRED_HEADERS = ["pdf_path", "query_file", "query_type", "output_directory"]
ALLOWED_QUERY_TYPES = {"each", "all"}


@dataclass(frozen=True)
class BatchConfigRow:
    row_number: int
    pdf_path: Path
    query_file: Path
    query_type: str
    output_directory: Path


def _validate_headers(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise SystemExit("Error: CSV config file is empty or missing headers")

    normalized = [name.strip() for name in fieldnames]
    missing = [header for header in REQUIRED_HEADERS if header not in normalized]
    if missing:
        raise SystemExit(f"Error: CSV config missing required headers: {', '.join(missing)}")


def _resolve_cell_path(csv_path: Path, raw_value: str) -> Path:
    candidate = Path(raw_value.strip())
    if candidate.is_absolute():
        return candidate
    return (csv_path.parent / candidate).resolve()


def _expand_pdf_paths(row_number: int, pdf_path: Path) -> list[Path]:
    if not pdf_path.exists():
        raise SystemExit(f"Error: Row {row_number} pdf_path not found: {pdf_path}")

    if pdf_path.is_file():
        if pdf_path.suffix.lower() != ".pdf":
            raise SystemExit(f"Error: Row {row_number} pdf_path is not a PDF file: {pdf_path}")
        return [pdf_path]

    if pdf_path.is_dir():
        pdf_files = sorted(p for p in pdf_path.glob("*.pdf") if p.is_file())
        if not pdf_files:
            raise SystemExit(f"Error: Row {row_number} pdf_path folder contains no PDF files: {pdf_path}")
        return pdf_files

    raise SystemExit(f"Error: Row {row_number} pdf_path is not a file or directory: {pdf_path}")


def load_batch_config(config_file: Path) -> list[BatchConfigRow]:
    config_path = config_file.expanduser().resolve()
    if not config_path.exists() or not config_path.is_file():
        raise SystemExit(f"Error: Config file not found: {config_path}")

    rows: list[BatchConfigRow] = []
    with config_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _validate_headers(reader.fieldnames)

        for row_number, row in enumerate(reader, start=2):
            pdf_raw = (row.get("pdf_path") or "").strip()
            query_raw = (row.get("query_file") or "").strip()
            query_type = (row.get("query_type") or "").strip().lower()
            output_raw = (row.get("output_directory") or "").strip()

            if not pdf_raw:
                raise SystemExit(f"Error: Row {row_number} has empty pdf_path")
            if not query_raw:
                raise SystemExit(f"Error: Row {row_number} has empty query_file")
            if not output_raw:
                raise SystemExit(f"Error: Row {row_number} has empty output_directory")
            if query_type not in ALLOWED_QUERY_TYPES:
                allowed = ", ".join(sorted(ALLOWED_QUERY_TYPES))
                raise SystemExit(
                    f"Error: Row {row_number} has invalid query_type '{query_type}'. "
                    f"Expected one of: {allowed}"
                )

            pdf_path = _resolve_cell_path(config_path, pdf_raw)
            query_file = _resolve_cell_path(config_path, query_raw)
            output_directory = _resolve_cell_path(config_path, output_raw)

            expanded_pdf_paths = _expand_pdf_paths(row_number, pdf_path)
            for expanded_pdf_path in expanded_pdf_paths:
                rows.append(
                    BatchConfigRow(
                        row_number=row_number,
                        pdf_path=expanded_pdf_path,
                        query_file=query_file,
                        query_type=query_type,
                        output_directory=output_directory,
                    )
                )

    if not rows:
        raise SystemExit("Error: CSV config has no data rows")

    _validate_paths(rows)
    return rows


def _validate_paths(rows: list[BatchConfigRow]) -> None:
    missing_pdfs = sorted({str(row.pdf_path) for row in rows if not row.pdf_path.exists()})
    invalid_pdf_types = sorted(
        {
            str(row.pdf_path)
            for row in rows
            if row.pdf_path.exists() and (not row.pdf_path.is_file() or row.pdf_path.suffix.lower() != ".pdf")
        }
    )
    missing_queries = sorted({str(row.query_file) for row in rows if not row.query_file.is_file()})

    if missing_pdfs:
        formatted = "\n".join(f"  - {path}" for path in missing_pdfs)
        raise SystemExit(f"Error: Missing pdf_path entries:\n{formatted}")

    if invalid_pdf_types:
        formatted = "\n".join(f"  - {path}" for path in invalid_pdf_types)
        raise SystemExit(f"Error: Invalid pdf_path entries (expected .pdf files):\n{formatted}")

    if missing_queries:
        formatted = "\n".join(f"  - {path}" for path in missing_queries)
        raise SystemExit(f"Error: Missing query_file entries:\n{formatted}")


def cmd_run(args: argparse.Namespace) -> None:
    rows = load_batch_config(Path(args.config_file))

    # Read query files once before network calls.
    query_text_cache: dict[Path, str] = {}
    for row in rows:
        if row.query_file not in query_text_cache:
            query_text_cache[row.query_file] = read_query_file(row.query_file)

    with create_client(args.profile) as client:
        run_timestamp = get_timestamp()
        all_groups: dict[tuple[Path, Path], list[dict]] = {}

        for row in rows:
            console.print(f"[bold blue]Uploading:[/bold blue] {row.pdf_path.name}")
            result = sources_service.add_source(
                client,
                notebook_id=args.notebook_id,
                source_type="file",
                file_path=str(row.pdf_path),
                wait=True,
            )

            source_id = str(result.get("source_id", ""))
            if not source_id:
                raise SystemExit(
                    f"Error: Upload for row {row.row_number} did not return source_id"
                )

            source_title = str(result.get("title") or row.pdf_path.name)
            source = {"id": source_id, "title": source_title}

            if row.query_type == "each":
                output_dir = create_output_dir(str(row.output_directory))
                query_single_source(
                    client,
                    args.notebook_id,
                    source,
                    query_text_cache[row.query_file],
                    output_dir,
                    run_timestamp,
                )
                continue

            key = (row.query_file, row.output_directory)
            all_groups.setdefault(key, []).append(source)

        for (query_file, output_directory), group_sources in all_groups.items():
            if not group_sources:
                continue

            output_dir = create_output_dir(str(output_directory))
            output_path = output_dir / f"{args.notebook_id}__{query_file.stem}.md"
            if output_path.exists():
                console.print(f"[yellow]Skipping[/yellow] existing output: {output_path.name}")
                continue

            source_ids = [str(source["id"]) for source in group_sources]
            console.print(
                f"[1/1] Generating output for [bold]{len(source_ids)} source(s) together[/bold]..."
            )
            start_result = query_start(
                client,
                args.notebook_id,
                query_text_cache[query_file],
                source_ids=source_ids,
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
                [get_source_display_name(source) for source in group_sources],
                answer,
                run_timestamp,
                query_id=query_id,
                response_id=response_id,
                model_version=model_version,
            )
            print(f"Saved: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nlmbatch",
        description="Batch upload and query using a CSV config file",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run batch upload and query from CSV config")
    run_parser.add_argument("--notebook-id", required=True, help="Notebook ID")
    run_parser.add_argument("--config-file", required=True, help="Path to CSV config file")
    run_parser.add_argument("--profile", default="default", help="Auth profile (default: default)")
    run_parser.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    run_cli_command(parser)


if __name__ == "__main__":
    main()
