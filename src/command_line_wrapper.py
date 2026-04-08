import sys
import os
import argparse
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Upload PDFs to NotebookLM using nlm source add command"
    )
    
    # Print help if no arguments provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    parser.add_argument(
        "--notebook-id",
        type=str,
        required=True,
        help="NotebookLM notebook ID (required)"
    )
    parser.add_argument(
        "--pdf-folder",
        type=str,
        required=True,
        help="Path to the folder containing PDF files (required)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Profile name to use (default: 'default')"
    )
    
    args = parser.parse_args()
    
    # Get PDF folder path
    pdf_folder = Path(args.pdf_folder)
    
    # Validate that the folder exists
    if not pdf_folder.exists():
        print(f"Error: PDF folder '{pdf_folder}' does not exist")
        sys.exit(1)
    
    if not pdf_folder.is_dir():
        print(f"Error: '{pdf_folder}' is not a directory")
        sys.exit(1)
    
    # Find all PDF files
    pdf_files = list(pdf_folder.glob("*.pdf"))
    
    # Check if at least one PDF exists
    if not pdf_files:
        print(f"Error: No PDF files found in '{pdf_folder}'")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF(s) to upload")
    print(f"Using notebook ID: {args.notebook_id}")
    print(f"Using profile: {args.profile}")
    print()
    
    # Upload PDFs one by one
    for pdf_file in sorted(pdf_files):
        print(f"Uploading: {pdf_file.name}")
        try:
            command = [
                "nlm",
                "source",
                "add",
                args.notebook_id,
                "--file",
                str(pdf_file),
                "--wait",
                "--profile",
                args.profile,
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            print(f"  ✓ Successfully uploaded {pdf_file.name}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to upload {pdf_file.name}")
            print(f"    Error: {e.stderr}")
        except Exception as e:
            print(f"  ✗ Error uploading {pdf_file.name}: {str(e)}")
    
    print("\nUpload process completed!")


if __name__ == "__main__":
    main()