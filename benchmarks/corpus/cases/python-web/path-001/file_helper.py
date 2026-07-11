"""Synthetic local path helper with an intentionally missing containment check."""


def candidate_path(base, user_name):
    return base / user_name
