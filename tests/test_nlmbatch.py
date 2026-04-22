from pathlib import Path

import pytest

import nlmbatch


def _write_config(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_nlmbatch_parser_run_command() -> None:
    parser = nlmbatch.build_parser()
    args = parser.parse_args(
        [
            "run",
            "--notebook-id",
            "nb-123",
            "--config-file",
            "batch.csv",
        ]
    )
    assert args.command == "run"
    assert args.notebook_id == "nb-123"
    assert args.config_file == "batch.csv"


def test_load_batch_config_missing_required_header(tmp_path: Path) -> None:
    config_file = _write_config(
        tmp_path / "batch.csv",
        "pdf_path,query_file,output_directory\n"
        "paper.pdf,query.md,out\n",
    )

    with pytest.raises(SystemExit, match="missing required headers"):
        nlmbatch.load_batch_config(config_file)


def test_load_batch_config_missing_pdf_or_query_paths(tmp_path: Path) -> None:
    query_file = tmp_path / "query.md"
    query_file.write_text("test query", encoding="utf-8")

    config_file = _write_config(
        tmp_path / "batch.csv",
        "pdf_path,query_file,query_type,output_directory\n"
        "missing.pdf,query.md,each,out\n",
    )

    with pytest.raises(SystemExit, match="pdf_path not found"):
        nlmbatch.load_batch_config(config_file)


def test_load_batch_config_invalid_query_type(tmp_path: Path) -> None:
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n")
    query_file = tmp_path / "query.md"
    query_file.write_text("test query", encoding="utf-8")

    config_file = _write_config(
        tmp_path / "batch.csv",
        "pdf_path,query_file,query_type,output_directory\n"
        "paper.pdf,query.md,single,out\n",
    )

    with pytest.raises(SystemExit, match="invalid query_type"):
        nlmbatch.load_batch_config(config_file)


def test_load_batch_config_success_resolves_relative_paths(tmp_path: Path) -> None:
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n")
    query_file = tmp_path / "query.md"
    query_file.write_text("test query", encoding="utf-8")

    config_file = _write_config(
        tmp_path / "batch.csv",
        "pdf_path,query_file,query_type,output_directory\n"
        "paper.pdf,query.md,all,outputs\n",
    )

    rows = nlmbatch.load_batch_config(config_file)

    assert len(rows) == 1
    assert rows[0].pdf_path == pdf_file.resolve()
    assert rows[0].query_file == query_file.resolve()
    assert rows[0].query_type == "all"
    assert rows[0].output_directory == (tmp_path / "outputs").resolve()


def test_load_batch_config_expands_directory_pdf_path(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_a = pdf_dir / "a.pdf"
    pdf_b = pdf_dir / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")

    query_file = tmp_path / "query.md"
    query_file.write_text("test query", encoding="utf-8")

    config_file = _write_config(
        tmp_path / "batch.csv",
        "pdf_path,query_file,query_type,output_directory\n"
        "pdfs,query.md,each,outputs\n",
    )

    rows = nlmbatch.load_batch_config(config_file)

    assert len(rows) == 2
    assert {row.pdf_path for row in rows} == {pdf_a.resolve(), pdf_b.resolve()}
    assert all(row.query_type == "each" for row in rows)
