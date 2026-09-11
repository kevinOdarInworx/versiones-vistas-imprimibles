"""App web para comparar el SQL (el SELECT del CREATE VIEW) de una misma
vista del esquema INSOR_DM entre distintos ambientes GDS/RAWDB.

- /versions: intenta traer el texto de la vista en TODOS los ambientes (DEV
  incluida) de una sola vez y los agrupa por contenido identico (para ver de
  un vistazo que ambientes comparten "version" y cuales difieren). Si un
  ambiente no responde (p.ej. DEV apagada) se reporta el error solo despues
  de intentar la conexion, nunca antes.
- /diff: calcula el diff lado a lado (difflib) entre dos textos ya traidos
  por el frontend (no vuelve a golpear la base).
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config.environments import ENVIRONMENTS
from views import build_diff, get_view_source, list_views

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.json.sort_keys = False


@app.route("/")
def index():
    envs = [{"key": k, "label": v["label"]} for k, v in ENVIRONMENTS.items()]
    return render_template("index.html", environments=envs)


@app.route("/views")
def views_route():
    env = request.args.get("env", "")
    if env not in ENVIRONMENTS:
        return jsonify({"error": "Ambiente invalido."}), 400
    try:
        return jsonify({"views": list_views(env)})
    except Exception as exc:  # tunel / conexion / oracle
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502


@app.route("/versions", methods=["POST"])
def versions():
    data = request.get_json(silent=True) or {}
    view_name = (data.get("view_name") or "").strip()
    if not view_name:
        return jsonify({"error": "Falta el nombre de la vista."}), 400

    result = {}
    for key in ENVIRONMENTS:
        try:
            result[key] = get_view_source(key, view_name)
        except Exception as exc:
            result[key] = {"found": False, "error": f"{type(exc).__name__}: {exc}"}
    return jsonify({"view_name": view_name.upper(), "environments": result})


@app.route("/diff", methods=["POST"])
def diff():
    data = request.get_json(silent=True) or {}
    sql_a = data.get("sql_a") or ""
    sql_b = data.get("sql_b") or ""
    label_a = data.get("label_a") or "A"
    label_b = data.get("label_b") or "B"
    return jsonify(build_diff(sql_a, sql_b, label_a, label_b))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
