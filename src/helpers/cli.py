"""Common CLI utilities for command handling."""

import sys
from typing import Callable

from notebooklm_tools.core.errors import ClientAuthenticationError

from .formatter import print_auth_error


def run_cli_command(parser, parse_args_handler: Callable | None = None) -> None:
    """
    Generic CLI command runner with error handling.
    
    Args:
        parser: ArgumentParser instance
        parse_args_handler: Optional custom argument parser (defaults to parser.parse_args())
    """
    # Print help if no arguments provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # Parse arguments
    args = parse_args_handler() if parse_args_handler else parser.parse_args()
    
    # Ensure a subcommand function exists
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    # Execute command with error handling
    try:
        args.func(args)
    except ClientAuthenticationError as exc:
        profile_name = getattr(args, "profile", "default")
        print_auth_error(profile_name, exc)
        sys.exit(1)


def remove_duplicate_error_handling(operation_name: str, operation_func: Callable) -> Callable:
    """
    Decorator to standardize error handling for operations.
    
    Args:
        operation_name: Name of the operation for error messages
        operation_func: The operation to wrap
    
    Returns:
        Wrapped function with consistent error handling
    """
    def wrapper(*args, **kwargs):
        try:
            return operation_func(*args, **kwargs)
        except Exception as exc:
            raise SystemExit(f"Error in {operation_name}: {exc}") from exc
    return wrapper
