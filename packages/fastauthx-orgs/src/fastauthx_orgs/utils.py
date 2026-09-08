import re


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug. Not guaranteed unique — callers
    that need uniqueness (e.g. organization slugs) must check and retry."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "org"
