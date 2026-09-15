"""Analiza los reportes Jasper (.jrxml) de PRINTOUTS/FASE_1: para un
imprimible (tipicamente su "master") arma el arbol de subreportes y, para
cada nodo, que vistas/tablas consulta su queryString.

No toca la base de datos: es puro analisis de archivos locales. La deteccion
de "es vista" es heuristica (el objeto termina en _VIEW, convencion usada en
todo el esquema INSOR_GDS) y la extraccion de tablas es un scan de texto
sobre FROM/JOIN, no un parser SQL completo (no falla con esto, pero no
captura FROM con listas separadas por coma al viejo estilo).
"""
from __future__ import annotations

import os
import re
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _resolve(path: str) -> str:
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))


PRINTOUTS_DIR = _resolve(
    os.getenv("PRINTOUTS_DIR", os.path.join("..", "INSOR", "shared_workspace", "PRINTOUTS", "FASE_1"))
)

# Carpetas que no son familias de imprimibles (assets, no reportes).
_SKIP_DIRS = {"images"}

_NS_RE = re.compile(r'\sxmlns="[^"]+"')
_FROM_JOIN_RE = re.compile(
    r'(?i)\b(?:from|join)\s+("?[A-Za-z_][\w$]*"?(?:\."?[A-Za-z_][\w$]*"?)?)'
)


def _safe_segment(value: str) -> str:
    """Valida un segmento de ruta que viene de un query param (sin .. ni separadores)."""
    value = (value or "").strip()
    if not value or value in (".", "..") or "/" in value or "\\" in value:
        raise ValueError(f"Valor invalido: {value!r}")
    return value


def list_families() -> list[dict]:
    """Carpetas bajo PRINTOUTS_DIR que tienen al menos un .jrxml propio."""
    families = []
    if not os.path.isdir(PRINTOUTS_DIR):
        return families
    for entry in sorted(os.listdir(PRINTOUTS_DIR), key=str.lower):
        full = os.path.join(PRINTOUTS_DIR, entry)
        if not os.path.isdir(full) or entry.lower() in _SKIP_DIRS:
            continue
        try:
            count = sum(1 for f in os.listdir(full) if f.lower().endswith(".jrxml"))
        except OSError:
            continue
        if count:
            families.append({"name": entry, "report_count": count})
    return families


def list_reports(family: str) -> list[dict]:
    """.jrxml de nivel superior en una familia, los "master" primero."""
    family = _safe_segment(family)
    directory = os.path.join(PRINTOUTS_DIR, family)
    if not os.path.isdir(directory):
        raise ValueError(f"Familia desconocida: {family}")
    reports = []
    for f in os.listdir(directory):
        if not f.lower().endswith(".jrxml"):
            continue
        base = os.path.splitext(f)[0]
        reports.append({"name": base, "is_master": "master" in base.lower()})
    reports.sort(key=lambda r: (not r["is_master"], r["name"].lower()))
    return reports


def _strip_default_ns(xml_text: str) -> str:
    return _NS_RE.sub("", xml_text, count=1)


def _extract_objects(sql_texts: list[str]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for sql in sql_texts:
        for m in _FROM_JOIN_RE.finditer(sql or ""):
            ref = m.group(1).replace('"', "")
            parts = ref.split(".")
            schema = parts[0] if len(parts) > 1 else None
            obj = parts[-1]
            key = ((schema or "").lower(), obj.lower())
            if key in seen:
                continue
            seen[key] = {
                "schema": schema,
                "object": obj,
                "is_view": obj.lower().endswith("_view"),
            }
    return sorted(seen.values(), key=lambda o: (not o["is_view"], (o["schema"] or "").lower(), o["object"].lower()))


def _find_sibling_jrxml(directory: str, base_noext: str) -> str | None:
    target = (base_noext + ".jrxml").lower()
    try:
        for entry in os.listdir(directory):
            if entry.lower() == target:
                return os.path.join(directory, entry)
    except OSError:
        return None
    return None


def _parse_report(path: str, seen_paths: frozenset[str] = frozenset()) -> dict:
    name = os.path.splitext(os.path.basename(path))[0]
    if not os.path.isfile(path):
        return {"name": name, "file": os.path.basename(path), "missing": True, "queries": [], "children": []}

    real = os.path.normcase(os.path.abspath(path))
    if real in seen_paths:
        return {"name": name, "file": os.path.basename(path), "cycle": True, "queries": [], "children": []}
    seen_paths = seen_paths | {real}

    with open(path, encoding="utf-8", errors="replace") as fh:
        text = _strip_default_ns(fh.read())
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {"name": name, "file": os.path.basename(path), "error": str(exc), "queries": [], "children": []}

    query_texts = [qs.text or "" for qs in root.iter("queryString")]
    queries = _extract_objects(query_texts)

    directory = os.path.dirname(path)
    children = []
    for se in root.iter("subreportExpression"):
        raw = (se.text or "").strip().strip('"')
        if not raw:
            continue
        base_noext = os.path.splitext(os.path.basename(raw))[0]
        sub_path = _find_sibling_jrxml(directory, base_noext)
        if sub_path:
            children.append(_parse_report(sub_path, seen_paths))
        else:
            children.append({"name": base_noext, "file": os.path.basename(raw), "missing": True, "queries": [], "children": []})

    return {"name": name, "file": os.path.basename(path), "queries": queries, "children": children}


def get_tree(family: str, report: str) -> dict:
    family = _safe_segment(family)
    report = _safe_segment(report)
    path = os.path.join(PRINTOUTS_DIR, family, report + ".jrxml")
    if not os.path.isfile(path):
        raise ValueError(f"No se encontro {report}.jrxml en {family}.")
    return _parse_report(path)
