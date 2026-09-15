"""Indice de vistas definidas en el repo INSOR (GitHub Inworx/INSOR, rama
develop, carpeta GDS/FASE 1) para poder compararlas contra los ambientes de
base de datos como si fuera un ambiente mas.

Trabaja sobre el clon local del repo (no golpea la API de GitHub). Cada
archivo .sql suele traer, como comentario o como DDL real, la linea
"CREATE OR REPLACE ... VIEW owner.view_name (...) AS" seguida del SELECT;
de ahi se saca tanto el nombre de la vista como el punto donde empieza el
SELECT real (para no arrastrar el encabezado, los comentarios de
"Aclaraciones" ni un ';' final al comparar contra DBA_VIEWS.TEXT).
"""
from __future__ import annotations

import hashlib
import os
import re

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _resolve(path: str) -> str:
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))


REPO_VIEWS_DIR = _resolve(
    os.getenv("REPO_VIEWS_DIR", os.path.join("..", "INSOR", "GDS", "FASE 1"))
)

# Los .sql de este repo estan guardados en Windows-1252 (mismo encoding que
# se usa en SQL Developer para abrirlos), no UTF-8: leerlos como UTF-8
# corrompe las tildes/ene y hace que el diff marque diferencias falsas.
REPO_FILE_ENCODING = os.getenv("REPO_FILE_ENCODING", "cp1252")

# Carpetas con versiones viejas: se usan solo si no hay una version mejor
# (de nivel superior) para esa vista.
_LOW_PRIORITY_DIRS = {"deprecadas", "versiones en prod"}

_HEADER_RE = re.compile(
    r"(?is)CREATE\s+OR\s+REPLACE\s+(?:FORCE\s+)?(?:EDITIONABLE\s+)?VIEW\s+"
    r'"?(?P<a>[A-Za-z0-9_]+)"?(?:\s*\.\s*"?(?P<b>[A-Za-z0-9_]+)"?)?'
    r"\s*(?:\([^)]*\))?\s*AS\b"
)
_LEADING_COMMENT_RE = re.compile(r"\A(?:\s*(?:/\*.*?\*/|--[^\n]*)\s*)*", re.DOTALL)


def _extract_view_name(text: str) -> str | None:
    m = _HEADER_RE.search(text)
    if not m:
        return None
    return (m.group("b") or m.group("a")).upper()


def _extract_select(text: str) -> str:
    m = _HEADER_RE.search(text)
    remainder = text[m.end():] if m else text
    lead = _LEADING_COMMENT_RE.match(remainder)
    if lead:
        remainder = remainder[lead.end():]
    remainder = remainder.rstrip()
    if remainder.endswith(";"):
        remainder = remainder[:-1].rstrip()
    return remainder


def _priority(path: str) -> int:
    rel_dir = os.path.dirname(os.path.relpath(path, REPO_VIEWS_DIR)).lower()
    parts = rel_dir.split(os.sep) if rel_dir else []
    return 1 if any(p in _LOW_PRIORITY_DIRS for p in parts) else 0


def _build_index() -> dict[str, str]:
    """view_name (MAYUSCULA) -> mejor archivo .sql que la define."""
    best: dict[str, tuple[int, str]] = {}
    if not os.path.isdir(REPO_VIEWS_DIR):
        return {}
    for root, _dirs, files in os.walk(REPO_VIEWS_DIR):
        for f in files:
            if not f.lower().endswith(".sql"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding=REPO_FILE_ENCODING, errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            name = _extract_view_name(text)
            if not name:
                continue
            prio = _priority(path)
            current = best.get(name)
            if current is None or prio < current[0]:
                best[name] = (prio, path)
    return {name: path for name, (prio, path) in best.items()}


_index_cache: dict[str, str] | None = None


def get_index(force_refresh: bool = False) -> dict[str, str]:
    global _index_cache
    if _index_cache is None or force_refresh:
        _index_cache = _build_index()
    return _index_cache


def get_repo_source(view_name: str) -> dict:
    """Texto del SELECT de la vista segun el repo. {"found": False} si no
    hay ningun .sql que declare esa vista en su encabezado CREATE VIEW."""
    view_name = (view_name or "").strip().upper()
    path = get_index().get(view_name)
    if not path:
        return {"found": False}
    with open(path, encoding=REPO_FILE_ENCODING, errors="replace") as fh:
        text = fh.read()
    sql = _extract_select(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = sql.split("\n")
    return {
        "found": True,
        "file": os.path.relpath(path, REPO_VIEWS_DIR).replace(os.sep, "/"),
        "sql": sql,
        "line_count": len(lines),
        "char_count": len(sql),
        "md5": hashlib.md5(sql.encode("utf-8", "ignore")).hexdigest(),
    }
