# utils.py
import os

def make_sqlite_url(path: str) -> str:
    """
    Convert windows path to sqlite URL if needed.
    Example: C:\path\db.sqlite -> sqlite:///C:/path/db.sqlite
    """
    if path.startswith("sqlite://"):
        return path
    path = path.replace("\\", "/")
    if path.startswith("/"):
        return f"sqlite:///{path}"
    # if drive letter
    if ":" in path:
        return f"sqlite:///{path}"
    return f"sqlite:///{os.path.abspath(path)}"
