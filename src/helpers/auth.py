"""Authentication utilities for notebooklm_automation."""

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.client import NotebookLMClient


def get_authenticated_profile(profile_name: str):
    """Load an auth profile with actionable errors."""
    manager = AuthManager(profile_name)
    if not manager.profile_exists():
        raise SystemExit(
            f"Profile '{profile_name}' not found. Run: nlm login --profile {profile_name}"
        )

    try:
        profile = manager.load_profile()
    except Exception as exc:
        raise SystemExit(
            f"Failed to load profile '{profile_name}': {exc}\n"
            f"Try re-authenticating: nlm login --profile {profile_name}"
        ) from exc

    if not profile.cookies:
        raise SystemExit(
            f"Profile '{profile_name}' has no cookies. "
            f"Run: nlm login --profile {profile_name}"
        )

    return profile


def create_client(profile_name: str) -> NotebookLMClient:
    """Create an authenticated NotebookLMClient."""
    profile = get_authenticated_profile(profile_name)
    return NotebookLMClient(
        cookies=profile.cookies,
        csrf_token=profile.csrf_token or "",
        session_id=profile.session_id or "",
        build_label=profile.build_label or "",
    )
