import nlmquery
import nlmsource


def test_nlmsource_parser_has_expected_commands() -> None:
    parser = nlmsource.build_parser()
    args = parser.parse_args(["list", "--notebook-id", "nb-123"])
    assert args.command == "list"
    assert args.notebook_id == "nb-123"


def test_nlmquery_parser_single_mode_requires_notebook_id() -> None:
    parser = nlmquery.build_parser()
    args = parser.parse_args(
        [
            "query",
            "--notebook-id",
            "nb-123",
            "--mode",
            "single",
            "--source-id",
            "src-1",
        ]
    )
    assert args.command == "query"
    assert args.mode == "single"
    assert args.source_id == "src-1"
