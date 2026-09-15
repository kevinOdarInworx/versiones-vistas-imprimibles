# versiones-vistas-imprimibles

App web (Flask, un solo usuario, `python app.py` en `127.0.0.1:5002`) con dos
pestañas: comparar el SQL de una vista de INSOR entre ambientes GDS/RAWDB, y
explorar que vistas consume cada imprimible (reporte Jasper).

## Pestaña "Comparar vistas"

Lee el `TEXT` de `DBA_VIEWS`/`ALL_VIEWS` — el SELECT con el que quedo creada
la vista, no un DBMS_METADATA.GET_DDL completo (evita ruido de storage
clauses / grants). No filtra por un owner fijo: el usuario dijo inicialmente
que el esquema era `INSOR_DM`, pero en la practica se vieron vistas con
`OWNER = INSOR_GDS`; `get_view_source` busca por `VIEW_NAME` en todo el
catalogo y devuelve el owner que encuentra.

1. El usuario escribe el nombre de una vista (con autocompletar opcional,
   cargado on-demand desde un ambiente vía `/views?env=`).
2. `/versions` trae el texto de la vista en los 5 ambientes a la vez
   (DEV/UAT/SIT/STST/PROD — todos por igual, sin pre-descartar DEV aunque
   suela estar abajo), agrupa los ambientes que tienen el mismo hash (misma
   "version") y muestra un resumen de un vistazo.
3. El usuario elige dos ambientes (por defecto, dos de grupos distintos si
   los hay) y `/diff` calcula un diff lado a lado (stdlib `difflib.HtmlDiff`)
   sobre el texto ya traido — no vuelve a golpear la base. Cada linea se
   normaliza a espacios simples antes de comparar (el SQL de esta base usa
   corridas de espacios, a veces de decenas de caracteres, para alinear
   visualmente AND/ON/AS/comentarios; si no se normalizan, una linea
   resaltada como cambiada arrastra ese padding y se ve como una barra solida
   al ajustar por ancho de pantalla).

## Pestaña "Imprimibles → vistas"

No toca la base: analiza en disco los `.jrxml` (definiciones Jasper) bajo
`PRINTOUTS_DIR` (`.env`, por defecto `../INSOR/shared_workspace/PRINTOUTS/FASE_1`).
Cada carpeta de primer nivel es una "familia" de imprimibles (Car_Ind,
Cot_Mul, etc.); dentro, el `queryString` de cada reporte trae el SQL crudo, y
`subreportExpression` referencia (por nombre de archivo, mismo directorio)
los subreportes hijos — `printouts.py` sigue esas referencias recursivamente
armando un arbol, y por cada nodo extrae que tablas/vistas toca (regex sobre
FROM/JOIN, heuristica: termina en `_VIEW` => es vista). El frontend lo
renderiza como arbol colapsable (`<details>` anidados) con un resumen de
todas las vistas unicas usadas en el arbol completo.

## Archivos clave

- `app.py` — rutas Flask: `/`, `/views`, `/versions`, `/diff`,
  `/imprimibles/families`, `/imprimibles/reports`, `/imprimibles/tree`.
- `views.py` — `list_views` / `get_view_source` (lectura de DBA_VIEWS.TEXT)
  y `build_diff` (diff con `difflib`).
- `printouts.py` — analisis de `.jrxml` (arbol de subreportes + objetos SQL
  por nodo), sin dependencia de la base.
- `db.py` — tunel SSH + conexion Oracle (modo thick), copiado tal cual de
  `generar-imprimibles`.
- `config/environments.py` — misma topologia de ambientes que
  `generar-imprimibles` (puertos locales distintos para poder correr ambas
  apps a la vez).
- `templates/index.html` — frontend unico, sin dependencias externas (dos
  pestañas con JS plano, tema claro/oscuro via `prefers-color-scheme`). El
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
