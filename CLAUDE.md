# versiones-vistas-imprimibles

App web (Flask, un solo usuario, `python app.py` en `127.0.0.1:5002`) para
comparar el SQL de una misma vista del esquema **INSOR_DM** (mismo nombre en
todas las bases INSOR) entre distintos ambientes GDS/RAWDB.

## Que compara

El `TEXT` de `DBA_VIEWS`/`ALL_VIEWS` para `OWNER = 'INSOR_DM'` — es decir, el
SELECT con el que quedo creada la vista, no un DBMS_METADATA.GET_DDL completo
(evita ruido de storage clauses / grants).

## Flujo

1. El usuario escribe el nombre de una vista (con autocompletar opcional,
   cargado on-demand desde un ambiente vía `/views?env=`).
2. `/versions` trae el texto de la vista en los 5 ambientes a la vez
   (DEV/UAT/SIT/STST/PROD), agrupa los ambientes que tienen el mismo hash
   (misma "version") y muestra un resumen de un vistazo.
3. El usuario elige dos ambientes (por defecto, dos de grupos distintos si
   los hay) y `/diff` calcula un diff lado a lado (stdlib `difflib.HtmlDiff`)
   sobre el texto ya traido — no vuelve a golpear la base.

## Archivos clave

- `app.py` — rutas Flask: `/`, `/views`, `/versions`, `/diff`.
- `views.py` — `list_views` / `get_view_source` (lectura de DBA_VIEWS.TEXT)
  y `build_diff` (diff con `difflib`, ver mas abajo).
- `db.py` — tunel SSH + conexion Oracle (modo thick), copiado tal cual de
  `generar-imprimibles`.
- `config/environments.py` — misma topologia de ambientes que
  `generar-imprimibles` (puertos locales distintos para poder correr ambas
  apps a la vez).
- `templates/index.html` — frontend unico, sin dependencias externas. El
  diff se renderiza reusando las clases CSS que genera `difflib.HtmlDiff`
  (`diff_add` / `diff_sub` / `diff_chg` / `diff_header`) con estilos propios.

## Conexion a la base

Reusa el mecanismo de `generar-imprimibles` (tunel SSH nativo + Oracle
Instant Client en modo thick). Por defecto **no** trae su propia copia de la
clave SSH ni del Instant Client (pesado, ~500MB, y la clave es sensible):
`.env` apunta con rutas relativas a los de `generar-imprimibles`
(`SSH_KEY_PATH`, `ORACLE_CLIENT_LIB`). Si esta app se mueve a otra maquina
sin ese proyecto al lado, hay que copiar esos dos recursos o ajustar las
rutas.

## Convenciones

- Comentarios y docstrings en español, estilo conciso.
- Nunca tocar bases INSIS, solo RAWDB (INSOR).
- Secretos en `.env` (no se commitea); ver `.env.example`.
- No hay tests ni build step; para probar cambios correr `python app.py` (o
  `run.bat`) contra un ambiente real.
