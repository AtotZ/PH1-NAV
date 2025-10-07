# General-purpose utilities

import hashlib
import datetime


def sha1_hex(text: str) -> str:
    """Return SHA1 hex digest of text."""
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def timestamp_now() -> str:
    """Current time as 'YYYY-MM-DD HH:MM:SS'."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_heading() -> str:
    """Heading for today's log section."""
    now = datetime.datetime.now()
    return f"==== {now.strftime('%A, %d %B %Y')} ====\n"


def today_date() -> str:
    """Today's date as 'YYYY-MM-DD'."""
    return datetime.datetime.now().strftime("%Y-%m-%d")


def created_str(dt_obj) -> str:
    """Safe stringify of Photos creation_date to 'YYYY-MM-DD HH:MM:SS'."""
    try:
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''
