# NotebookLM Automation

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Build](https://img.shields.io/github/actions/workflow/status/arupgsh/notebooklm_automation/ci.yml?label=build)](https://github.com/arupgsh/notebooklm_automation/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/github/actions/workflow/status/arupgsh/notebooklm_automation/ci.yml?label=tests)](https://github.com/arupgsh/notebooklm_automation/actions/workflows/ci.yml)

This repository provides two command-line tools built on top of [notebooklm-mcp-cli](https://github.com/jacob-bd/notebooklm-mcp-cli) to help automate parts of a systematic literature review workflow (for example, data extraction).


## Getting Started

UV package manager installation guide: https://docs.astral.sh/uv/getting-started/installation/


```bash
git clone https://github.com/arupgsh/notebooklm_automation.git

cd notebooklm_automation
```

### Prepare Virtual Environment

```bash
# using uv
uv sync

# using pip
python -m venv .venv
```

### Install Dependencies

```bash
# Activate environment

# PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# macOS/Linux (bash/zsh)
source .venv/bin/activate

# install dependencies (required only for pip setup)
python -m pip install -e .
```

After installation, verify that all commands work.

```bash
nlm --help
nlmsource --help
nlmquery --help
```

## NotebookLM Login

NotebookLM supports multiple auth profiles (for example: `work`, `personal`). If no profile argument is passed, the default profile is used. In the following example, `work` is used as the profile name.

```bash
nlm login --profile work
```
This opens a Chrome window to retrieve authentication tokens. The session usually remains valid for about one week.

### Check Login Status

```bash
nlm login --check --profile work
```

### Switch Profiles

```bash
nlm login profile list
nlm login switch <profile_name>
```

For more authentication details, see the [notebooklm-mcp-cli docs](https://github.com/jacob-bd/notebooklm-mcp-cli?tab=readme-ov-file#authentication).

## Create a Notebook

```bash
nlm notebook create "Research Project" --profile work

nlm notebook list --profile work # this command shows available notebook IDs
```

## Uploading PDFs

The `nlmsource` command has three subcommands: upload all PDFs from a folder to a specified notebook ID, list available notebook sources (PDFs), and remove sources.

```bash
nlmsource upload \
	--notebook-id <notebook_id> \
	--pdf-folder ./data/pdfs \
	--profile work \
	--plan standard
```

Notes:

There are three plan options. The default is `standard` (the free plan).

Limits: `standard`: 50 source files, `pro`: 300 source files, `ultra`: 600 source files.

1. Plan options: `standard`, `pro`, `ultra`.
2. Existing files are skipped when matched by source title.

### List Available Sources

```bash
nlmsource list \
	--notebook-id <notebook_id> \
	--profile work \
	--plan standard
```

### Remove Specific Source Files

```bash
nlmsource remove \
	--source-ids <source_id_1> <source_id_2> \
	--profile work
```

### Remove All Sources

```bash
nlmsource remove \
	--all \
	--notebook-id <notebook_id> \
	--profile work
```

## Query

The `nlmquery` command uses a prompt markdown file (`query.md` by default) to query notebook sources and writes results to a user-defined output folder (`output` by default).

### Modes

1. `single`: Query one source file.
2. `each`: Query all sources one by one.
3. `all`: Query all notebook sources together.

### Single Source

```bash
nlmquery query \
	--notebook-id <notebook_id> \
	--profile work \
	--mode single \
	--source-id <source_id> \
	--query-file query.md \
	--output-folder output
```

### Each Source Separately

```bash
nlmquery query \
	--notebook-id <notebook_id> \
	--profile work \
	--mode each \
	--query-file query.md \
	--output-folder output
```

### All Sources Together

```bash
nlmquery query \
	--notebook-id <notebook_id> \
	--profile work \
	--mode all \
	--query-file query.md \
	--output-folder output
```

### Combine Outputs

```bash
nlmquery merge \
	--output-folder output \
	--output-file output/merged_output.md
```

