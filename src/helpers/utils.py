"""Shared utilities for notebooklm_automation."""

import re
from datetime import datetime
from pathlib import Path


PLAN_LIMITS = {
    "standard": 50,
    "pro": 300,
    "ultra": 600,
}


# ==================== File Path & I/O Functions ====================


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing invalid characters."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()
    cleaned = cleaned.strip(".")
    return cleaned or "untitled"


def ensure_unique_path(path: Path) -> Path:
    """Return a unique path by appending a counter if the path already exists."""
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
    """Build the output path for a source query result."""
    filename = f"{sanitize_filename(source_file_name)}__{sanitize_filename(source_id)}.md"
    return output_dir / filename


def build_notebook_output_path(output_dir: Path, notebook_id: str) -> Path:
    """Build the output path for a notebook query result."""
    return output_dir / f"{sanitize_filename(notebook_id)}.md"


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_query_file(query_file: Path) -> str:
    """Read and validate a query file."""
    if not query_file.exists() or not query_file.is_file():
        raise SystemExit(f"Error: Query file not found: {query_file}")

    content = query_file.read_text(encoding="utf-8").strip()
    if not content:
        raise SystemExit(f"Error: Query file is empty: {query_file}")
    return content


def create_output_dir(output_folder: str | None) -> Path:
    """Create output directory if it doesn't exist."""
    output_dir = Path(output_folder) if output_folder else Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_source_file_name(source: dict) -> str:
    """Extract the file name from a source object."""
    title = str(source.get("title") or source.get("name") or source.get("id") or "source")
    return Path(title).stem or "source"


def get_source_display_name(source: dict) -> str:
    """Extract the display name from a source object."""
    title = str(source.get("title") or source.get("name") or source.get("id") or "source")
    return title or "source"


def collect_pdf_files(folder: Path) -> list[Path]:
    """Collect all PDF files from a folder."""
    resolved = folder.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Folder not found: {resolved}")
    if not resolved.is_dir():
        raise SystemExit(f"Not a directory: {resolved}")

    pdf_files = sorted(resolved.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"No PDF files found in: {resolved}")

    return pdf_files


# ==================== Query Result Functions ====================


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
    """Save query result to markdown file."""
    from .formatter import format_query_result
    
    body = format_query_result(
        notebook_id,
        source_ids,
        source_file_names,
        answer_text,
        run_timestamp,
        query_id=query_id,
        response_id=response_id,
        model_version=model_version,
    )
    output_path.write_text(body, encoding="utf-8")
