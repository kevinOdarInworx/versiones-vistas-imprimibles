"""Lectura del texto fuente (el SELECT del CREATE VIEW) de vistas Oracle y
construccion del diff visual entre dos versiones.

El owner real de las vistas puede variar (se vio INSOR_GDS ademas del
INSOR_DM esperado), asi que get_view_source busca por VIEW_NAME sin fijar
owner y devuelve el owner encontrado. list_views si acota a los esquemas
conocidos (para no listar vistas de todo el catalogo). Se lee de
DBA_VIEWS.TEXT (con fallback a ALL_VIEWS si el usuario no tiene privilegio
DBA) porque es exactamente el texto del SELECT con el que se definio la
vista, sin el ruido de DBMS_METADATA (storage clauses, grants, etc).
"""
from __future__ import annotations

import difflib
import hashlib

from db import get_connection

# Esquemas conocidos donde viven las vistas de negocio INSOR (para acotar el
# autocompletar). get_view_source, en cambio, no filtra por owner: busca por
# nombre en todo el catalogo por si aparece bajo otro esquema.
KNOWN_SCHEMAS = ("INSOR_GDS", "INSOR_DM")
_SCHEMA_LIST_SQL = ", ".join(f"'{s}'" for s in KNOWN_SCHEMAS)


def list_views(env_key: str) -> list[str]:
    """Nombres de vistas de los esquemas INSOR conocidos, para autocompletar."""
    conn = get_connection(env_key)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT view_name FROM dba_views WHERE owner IN ({_SCHEMA_LIST_SQL}) "
                "ORDER BY view_name"
            )
        except Exception:
            cur.execute(
                f"SELECT view_name FROM all_views WHERE owner IN ({_SCHEMA_LIST_SQL}) "
                "ORDER BY view_name"
            )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_view_source(env_key: str, view_name: str) -> dict:
    """Texto del SELECT de la vista en un ambiente. {"found": False} si no existe.

    Busca por VIEW_NAME en todo el catalogo (sin fijar owner) porque el
    esquema dueno de una vista puede no ser el esperado.
    """
    view_name = (view_name or "").strip().upper()
    if not view_name:
        raise ValueError("Falta el nombre de la vista.")
    conn = get_connection(env_key)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT owner, text FROM dba_views WHERE view_name = :vname ORDER BY owner",
                {"vname": view_name},
            )
            rows = cur.fetchall()
        except Exception:
            cur.execute(
                "SELECT owner, text FROM all_views WHERE view_name = :vname ORDER BY owner",
                {"vname": view_name},
            )
            rows = cur.fetchall()
        if not rows:
            return {"found": False}
        owner, text = rows[0]
        sql = (text or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        lines = sql.split("\n")
        return {
            "found": True,
            "owner": owner,
            "other_owners": [r[0] for r in rows[1:]],  # rara ambiguedad: mismo nombre en +1 schema
            "sql": sql,
            "line_count": len(lines),
            "char_count": len(sql),
            "md5": hashlib.md5(sql.encode("utf-8", "ignore")).hexdigest(),
        }
    finally:
        conn.close()


def build_diff(sql_a: str, sql_b: str, label_a: str, label_b: str) -> dict:
    """Diff lado a lado (HTML) + estadisticas entre dos textos de vista.

    El SQL de estas vistas suele usar corridas de espacios (a veces decenas)
    tanto al inicio de linea como en el medio, para alinear visualmente un
    AND/ON bajo una columna lejana o un AS/comentario. Si se preservan tal
    cual, una linea marcada como cambiada arrastra ese espacio invisible
    dentro del <span> resaltado y, al ajustar por ancho de pantalla, se pinta
    como una barra solida enorme. Por eso cada linea se normaliza a espacios
    simples (sin importar donde caiga el espacio de mas) antes de comparar:
    la indentacion exacta no es informacion relevante para este diff.
    """
    lines_a = (sql_a or "").replace("\r\n", "\n").split("\n")
    lines_b = (sql_b or "").replace("\r\n", "\n").split("\n")

    def norm(line: str) -> str:
        return " ".join(line.split())

    cmp_a = [norm(l) for l in lines_a]
    cmp_b = [norm(l) for l in lines_b]

    sm = difflib.SequenceMatcher(a=cmp_a, b=cmp_b, autojunk=False)
    identical = cmp_a == cmp_b
    stats = {
        "identical": identical,
        "lines_a": len(lines_a),
        "lines_b": len(lines_b),
        "similarity": round(sm.ratio() * 100, 1),
    }

    if identical:
        return {"html": "", "stats": stats}

    hd = difflib.HtmlDiff(tabsize=4)
    # context=True: solo muestra las lineas afectadas (agregadas/eliminadas/
    # modificadas) mas un par de lineas de contexto alrededor, no la vista completa.
    table = hd.make_table(cmp_a, cmp_b, fromdesc=label_a, todesc=label_b, context=True, numlines=2)
    # difflib reemplaza cada espacio por &nbsp; (no separable). Con lineas de
    # SQL largas eso impide que el navegador corte la linea en los espacios;
    # se vuelve a espacio normal para que ajuste bien al ancho de pantalla
    # (el contenedor usa white-space: pre-wrap, que preserva la indentacion).
    table = table.replace("&nbsp;", " ")
    return {"html": table, "stats": stats}
