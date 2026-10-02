# Cambios de `joltio`

## 0.3.0

- **Las columnas de fecha y hora conservan su zona horaria.** `data.query` devuelve cada `DateTime('Europe/Madrid')` como `Datetime(time_zone="Europe/Madrid")` en Polars y `datetime64[…, Europe/Madrid]` en pandas, con la hora de Madrid (23:45+02:00). Antes salía la hora en UTC sin zona (21:45), que se confundía con hora local, y en pandas los días de cambio de hora la columna quedaba como texto. La hora repetida al atrasar el reloj se distingue (02:30+02:00 y 02:30+01:00).
- **Cambio de comportamiento:** una columna con zona no se compara con un `datetime` sin zona. Usa `datetime(2026, 10, 1, tzinfo=ZoneInfo("Europe/Madrid"))`, o `pl.col("datetime").dt.replace_time_zone(None)` si necesitas la hora local sin zona.

## 0.2.3

- Los checksums del motor de apps viajan dentro del paquete publicado en PyPI y la CLI verifica la descarga solo contra ellos: manipular el CDN (binario y `SHA256SUMS` a la vez) ya no basta para ejecutar otro motor.

## 0.2.2

- Con la sesión de `joltio login`, todas las peticiones fallaban con un 400 de Cloudflare: la credencial salía en dos cabeceras (`authorization` y `Authorization`). Ahora se envía una sola.
- La Data API acepta la sesión de la CLI (requería permiso de lectura sobre `cli_session`, que llega con la migración 0049 del servidor).

## 0.2.1

- `joltio mcp` expone también la Data API: `data_query` (SQL sobre el mercado), indicadores, recetas, revisiones y búsqueda por facetas, con la misma credencial y workspace. Lo que el backend ya ofrece como proxy de Data (claves, plan, uso, cobertura…) no se duplica. El servidor informa la versión de `joltio`.
- `joltio artifacts …` descarga el motor con el User-Agent de `joltio`. Con 0.2.0 la descarga usaba el de urllib, que Cloudflare rechaza (403, error 1010), y la autoría de apps no funcionaba fuera del monorepo.
- `joltio data query --format csv|parquet` escribe en stdout solo la tabla: la línea de metadatos `# row_count=…` que Data antepone al CSV pasa a stderr. Con 0.2.0, `--format csv > fichero.csv` dejaba esa línea dentro del fichero y Parquet la tomaba por la cabecera.

## 0.2.0

- Un solo paquete incluye la librería Python 0.1.0 y la CLI generada del OpenAPI. `joltio-toolkit` deja de ser el nombre de distribución.
- Los comandos de Data y `auth` de 0.1.0 conservan alias. La clave guardada en `~/.config/joltio/config.toml` sigue funcionando.
- Las credenciales se resuelven por argumento explícito, `JOLTIO_API_KEY` o `JOLTIO_TOKEN`, clave TOML existente y sesión de `joltio login`; la sesión se renueva mientras se usa y `logout` la revoca.
- MCP es un extra opcional. El motor de apps se descarga por versión y plataforma con verificación SHA-256. `data quickstart` reutiliza el ZIP público del panel.
- Funciona en Python 3.10 o superior, como 0.1.0.
- El código fuente público es el espejo de solo lectura https://github.com/datons/python-joltio, con una instantánea por versión.
