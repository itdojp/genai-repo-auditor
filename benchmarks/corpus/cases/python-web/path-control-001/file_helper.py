"""Synthetic local path helper with normalized-base containment enforcement."""


def candidate_path(base, user_name):
    approved_base = base.resolve()
    candidate = (base / user_name).resolve()
    candidate.relative_to(approved_base)
    return candidate
