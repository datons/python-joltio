# Joltio · librería Python y CLI

`pip install joltio` instala `import joltio` y el comando `joltio`. Los módulos de la CLI se derivan del OpenAPI del backend y de Data. MCP es opcional (`joltio[mcp]`); el motor de apps se descarga desde `cdn.joltio.app` la primera vez que se usa y se verifica con SHA-256.

## Primer uso

- **Python o cuaderno personal:** `pip install joltio`, `joltio login` y `from joltio import Client; j = Client()`. `joltio data quickstart mi-carpeta` descarga el mismo cuaderno, README y plantillas `.env` del panel. Si prefieres clave, define `JOLTIO_API_KEY` en tu entorno o `.env`.
- **Terminal:** `uv tool install joltio`, `joltio login` y `joltio data query "SELECT max(datetime) FROM omie.prices"`.
- **Agentes:** el MCP alojado en `https://api.joltio.app/mcp` no requiere instalación. Para MCP local: `uv tool install 'joltio[mcp]'`, `joltio login` y `claude mcp add joltio -- joltio mcp`.
- **Apps:** `uv tool install joltio`, `joltio login` y `joltio artifacts init`; continúa con `artifacts dev` y `artifacts publish`. El motor se descarga automáticamente por plataforma.
- **CI:** instala `joltio` en el entorno del job y pasa una clave específica por `JOLTIO_API_KEY`; no uses una sesión interactiva compartida.
- **Personal de Datons:** cuando exista la entrada del catálogo (issue CRM `130d8591`), instala o sincroniza con `zm package sync joltio`. Hasta entonces usa `uv tool install joltio`.

La precedencia de credenciales para la librería y la CLI es argumento explícito, `JOLTIO_API_KEY` o `JOLTIO_TOKEN`, clave conservada en `~/.config/joltio/config.toml` y sesión de `joltio login` en `session.json`. La sesión se renueva al usarla y `joltio logout` la revoca. Las claves son preferibles para CI, servidores y cuadernos compartidos. En redes corporativas con inspección HTTPS, define `SSL_CERT_FILE` para la librería y la CLI; `REQUESTS_CA_BUNDLE` cubre pip y otras bibliotecas basadas en requests.

## Uso

`joltio --help` muestra `workspace`, `data`, `pulse`, `fleet`, `scopes`, `measures`, `ledger`, `studio`, `artifacts`, `admin` y `self`, además de `login`, `logout`, `whoami` y `mcp`. Las operaciones REST siguen `joltio <módulo> <recurso> <verbo>`; las operaciones del módulo completo usan `joltio <módulo> <verbo>`. `--workspace <slug|id>` y `--json` se pasan antes del módulo.

`joltio workspace list`, `joltio workspace use <slug>`, `joltio workspace show` y `joltio workspace invite <email> [--role member|admin] [--product PRODUCTO]` usan el token guardado en `~/.config/joltio/session.json`. `joltio fleet assets import archivo.json --dry-run` acepta una lista JSON de activos o un objeto con `assets`; el resultado contiene una fila por activo. `joltio artifacts init|dev|build|validate|preview|publish|pull|versions` delega al motor TypeScript.

`joltio data query "select 1" --format json|csv|parquet` consulta `https://api.joltio.app/data/query`. Usa `JOLTIO_API_KEY` o `JOLTIO_DATA_API_KEY` si está definido; en su ausencia usa el Bearer de `joltio login`. `JOLTIO_DATA_API_URL` cambia el origen de Data y `X-Joltio-Workspace` lleva el workspace efectivo. No se almacena ninguna clave compartida. Para los comandos de Data generados desde el OpenAPI se usa la misma resolución de identidad. `--format csv` escribe CSV en stdout; `parquet` convierte el flujo CSV a Parquet en stdout.

`joltio self sync-spec` está oculto y actualiza los dos OpenAPI empaquetados en `~/.config/joltio/`; reabre la CLI después. `joltio self update` actualiza instalaciones de `uv tool` y muestra el comando para instalaciones de pip o proyectos uv. El catálogo CRM queda en la issue `130d8591`. La instalación de desarrollo desde este checkout es `uv tool install ./toolkit`; `JOLTIO_APP_ENGINE` permite usar un motor local.

## Compatibilidad

La API de `joltio` 0.1.0 conserva `Client`, `data`, `esios`, modelos y excepciones. Sus comandos `data query|search|coverage|metadata` y `auth set|show|remove` se aceptan como alias; los renombrados muestran aviso. La clave TOML de 0.1.0 sigue leyéndose.

Los nombres anteriores se mantienen como alias ocultos. Cada alias renombrado emite un aviso en stderr y ejecuta la misma operación, conservando el código de salida y stdout. La excepción son las seis rutas de vistas Fleet retiradas aguas arriba en `9a477e2`: sus equivalentes se redirigen a ámbitos y medidas; crear, actualizar o alternar una vista falla con una indicación de los comandos nuevos. Las operaciones que no cambiaron de ruta conservan el nombre sin aviso. La copia OpenAPI anterior contenía 137 operaciones; las rutas nuevas de invitaciones, importación de Fleet, ámbitos y medidas no forman parte de esta tabla.

### Comandos de la CLI TypeScript anterior

#### joltio login
- Nuevo: `joltio login`.

#### joltio mcp
- Nuevo: `joltio mcp`.

#### joltio functions
- Nuevo: `joltio artifacts functions list`.

#### joltio init
- Nuevo: `joltio artifacts init`.

#### joltio validate
- Nuevo: `joltio artifacts validate`.

#### joltio dev
- Nuevo: `joltio artifacts dev`.

#### joltio preview --remote
- Nuevo: `joltio artifacts preview --remote`.

#### joltio publish
- Nuevo: `joltio artifacts publish`.

#### joltio pull
- Nuevo: `joltio artifacts pull`.

#### joltio versions
- Nuevo: `joltio artifacts versions`.

#### joltio build
- Nuevo: `joltio artifacts build`.

#### joltio ls
- Nuevo: `joltio artifacts list`.

#### joltio open
- Nuevo: `joltio artifacts open`.

#### joltio share
- Nuevo: `joltio artifacts share`.

#### joltio invite
- Nuevo: `joltio workspace invite`.

### Comandos generados desde el OpenAPI anterior

#### joltio admin provision
- Nuevo: `joltio admin workspace provision`.

#### joltio artifacts create-artifact
- Nuevo: `joltio artifacts artifact create`.

#### joltio artifacts create-function
- Nuevo: `joltio artifacts function create`.

#### joltio artifacts create-project
- Nuevo: `joltio artifacts project create`.

#### joltio artifacts create-view
- Nuevo: `joltio artifacts view create`.

#### joltio artifacts get-project
- Nuevo: `joltio artifacts project get`.

#### joltio artifacts get-release
- Nuevo: `joltio artifacts release get`.

#### joltio artifacts list-artifacts
- Nuevo: `joltio artifacts artifacts list`.

#### joltio artifacts list-catalog
- Nuevo: `joltio artifacts catalog list`.

#### joltio artifacts list-functions
- Nuevo: `joltio artifacts functions list`.

#### joltio artifacts list-project-releases
- Nuevo: `joltio artifacts project-releases list`.

#### joltio artifacts list-views
- Nuevo: `joltio artifacts views list`.

#### joltio artifacts publish-project
- Nuevo: `joltio artifacts project publish`.

#### joltio artifacts render-artifact
- Nuevo: `joltio artifacts artifact render`.

#### joltio artifacts render-report
- Nuevo: `joltio artifacts report render`.

#### joltio artifacts render-view
- Nuevo: `joltio artifacts view render`.

#### joltio artifacts run-function
- Nuevo: `joltio artifacts function run`.

#### joltio artifacts set-favorite
- Nuevo: `joltio artifacts favorite set`.

#### joltio artifacts set-release-visibility
- Nuevo: `joltio artifacts release-visibility set`.

#### joltio artifacts set-visibility
- Nuevo: `joltio artifacts visibility set`.

#### joltio artifacts sync-project
- Nuevo: `joltio artifacts project sync`.

#### joltio artifacts update-project-layout
- Nuevo: `joltio artifacts project-layout update`.

#### joltio artifacts update-view
- Nuevo: `joltio artifacts view update`.

#### joltio artifacts validate-project
- Nuevo: `joltio artifacts project validate`.

#### joltio core health
- Nuevo: `joltio core health`.

#### joltio data coverage
- Nuevo: `joltio data coverage`.

#### joltio data create-key
- Nuevo: `joltio data key create`.

#### joltio data create-reingest
- Nuevo: `joltio data reingest create`.

#### joltio data example-query
- Nuevo: `joltio data example query`.

#### joltio data keys
- Nuevo: `joltio data keys list`.

#### joltio data move-seat
- Nuevo: `joltio data seat move`.

#### joltio data plan
- Nuevo: `joltio data plan`.

#### joltio data reingests
- Nuevo: `joltio data reingests list`.

#### joltio data revision-values
- Nuevo: `joltio data revision-values get`.

#### joltio data revisions
- Nuevo: `joltio data revisions list`.

#### joltio data revoke-key
- Nuevo: `joltio data key revoke`.

#### joltio data state
- Nuevo: `joltio data state`.

#### joltio data usage
- Nuevo: `joltio data usage`.

#### joltio entitlements access
- Nuevo: `joltio workspace access`.

#### joltio entitlements assign-seat
- Nuevo: `joltio workspace seat assign`.

#### joltio entitlements cancel-invitation
- Nuevo: `joltio workspace invitation cancel`.

#### joltio entitlements remove-member
- Nuevo: `joltio workspace member remove`.

#### joltio entitlements revoke-seat
- Nuevo: `joltio workspace seat revoke`.

#### joltio entitlements seats
- Nuevo: `joltio workspace seats list`.

#### joltio entitlements start-trial
- Nuevo: `joltio workspace trial start`.

#### joltio entitlements trial-status
- Nuevo: `joltio workspace trial-status get`.

#### joltio entitlements update-member-role
- Nuevo: `joltio workspace member-role update`.

#### joltio entitlements workspace-access
- Nuevo: `joltio workspace workspace-access get`.

#### joltio fleet asset
- Nuevo: `joltio fleet asset`.

#### joltio fleet catalog-search
- Nuevo: `joltio fleet catalog-search get`.

#### joltio fleet create-asset
- Nuevo: `joltio fleet asset create`.

#### joltio fleet create-simulation
- Nuevo: `joltio fleet simulation create`.

#### joltio fleet create-view
- Retirado aguas arriba (9a477e2): `joltio scopes create / joltio measures create`.

#### joltio fleet delete-asset
- Nuevo: `joltio fleet asset delete`.

#### joltio fleet delete-view
- Retirado aguas arriba (9a477e2): `joltio scopes delete / joltio measures delete`.

#### joltio fleet latest-simulation
- Nuevo: `joltio fleet simulation latest`.

#### joltio fleet performance
- Nuevo: `joltio fleet performance`.

#### joltio fleet portfolio
- Nuevo: `joltio fleet portfolio`.

#### joltio fleet realtime
- Nuevo: `joltio fleet realtime`.

#### joltio fleet reconciled-periods
- Nuevo: `joltio fleet reconciled-periods get`.

#### joltio fleet relink-unit
- Nuevo: `joltio fleet unit relink`.

#### joltio fleet set-preference
- Nuevo: `joltio fleet preference set`.

#### joltio fleet set-status
- Nuevo: `joltio fleet status set`.

#### joltio fleet set-view-members
- Retirado aguas arriba (9a477e2): `joltio scopes members set`.

#### joltio fleet summary
- Nuevo: `joltio fleet summary`.

#### joltio fleet toggle-view-member
- Retirado aguas arriba (9a477e2): `joltio scopes members add / joltio scopes members remove`.

#### joltio fleet update-asset
- Nuevo: `joltio fleet asset update`.

#### joltio fleet update-view
- Retirado aguas arriba (9a477e2): `joltio scopes update / joltio measures update`.

#### joltio fleet views
- Retirado aguas arriba (9a477e2): `joltio scopes list`.

#### joltio leads create-lead
- Nuevo: `joltio leads lead create`.

#### joltio ledger assets
- Nuevo: `joltio ledger assets list`.

#### joltio ledger catalog-search
- Nuevo: `joltio ledger catalog-search get`.

#### joltio ledger create-asset
- Nuevo: `joltio ledger asset create`.

#### joltio ledger delete-asset
- Nuevo: `joltio ledger asset delete`.

#### joltio ledger export-reconciliation
- Nuevo: `joltio ledger reconciliation export`.

#### joltio ledger helper
- Nuevo: `joltio ledger helper`.

#### joltio ledger latest
- Nuevo: `joltio ledger units latest`.

#### joltio ledger overview
- Nuevo: `joltio ledger overview`.

#### joltio ledger periods
- Nuevo: `joltio ledger periods list`.

#### joltio ledger reconciliation
- Nuevo: `joltio ledger reconciliation`.

#### joltio ledger representantes
- Nuevo: `joltio ledger representantes list`.

#### joltio ledger template
- Nuevo: `joltio ledger template`.

#### joltio ledger trend
- Nuevo: `joltio ledger trend`.

#### joltio ledger update-discrepancy
- Nuevo: `joltio ledger discrepancy update`.

#### joltio ledger upload-import
- Nuevo: `joltio ledger import upload`.

#### joltio pulse activate-reservation
- Nuevo: `joltio pulse reservation activate`.

#### joltio pulse activate-template
- Nuevo: `joltio pulse template activate`.

#### joltio pulse alert-templates
- Nuevo: `joltio pulse alert-templates get`.

#### joltio pulse create-dashboard
- Nuevo: `joltio pulse dashboard create`.

#### joltio pulse create-dashboard-app
- Nuevo: `joltio pulse dashboard-app create`.

#### joltio pulse create-pulse-alert
- Nuevo: `joltio pulse pulse-alert create`.

#### joltio pulse data-catalog
- Nuevo: `joltio pulse data-catalog get`.

#### joltio pulse delete-external-reservation
- Nuevo: `joltio pulse external-reservation delete`.

#### joltio pulse entitlements
- Nuevo: `joltio pulse entitlements list`.

#### joltio pulse follows
- Nuevo: `joltio pulse follows list`.

#### joltio pulse get-dashboard
- Nuevo: `joltio pulse dashboard get`.

#### joltio pulse get-digest-setting
- Nuevo: `joltio pulse digest-setting get`.

#### joltio pulse get-public-dashboard-app
- Nuevo: `joltio pulse public-dashboard-app get`.

#### joltio pulse list-dashboards
- Nuevo: `joltio pulse dashboards list`.

#### joltio pulse list-notifications
- Nuevo: `joltio pulse notifications list`.

#### joltio pulse list-public-dashboard-apps
- Nuevo: `joltio pulse public-dashboard-apps list`.

#### joltio pulse list-reservations
- Nuevo: `joltio pulse reservations list`.

#### joltio pulse mark-notifications-read
- Nuevo: `joltio pulse notifications-read mark`.

#### joltio pulse query-dashboard-app
- Nuevo: `joltio pulse dashboard-app query`.

#### joltio pulse query-public-dashboard-app
- Nuevo: `joltio pulse public-dashboard-app query`.

#### joltio pulse release-reservation
- Nuevo: `joltio pulse reservation release`.

#### joltio pulse reserve-alert
- Nuevo: `joltio pulse alert reserve`.

#### joltio pulse set-digest-muted
- Nuevo: `joltio pulse digest-muted set`.

#### joltio pulse set-digest-setting
- Nuevo: `joltio pulse digest-setting set`.

#### joltio pulse set-external-reservation-state
- Nuevo: `joltio pulse external-reservation-state set`.

#### joltio pulse set-follow
- Nuevo: `joltio pulse follow set`.

#### joltio pulse update-dashboard
- Nuevo: `joltio pulse dashboard update`.

#### joltio pulse update-dashboard-app
- Nuevo: `joltio pulse dashboard-app update`.

#### joltio studio add-asset
- Nuevo: `joltio studio asset add`.

#### joltio studio add-profile
- Nuevo: `joltio studio profile add`.

#### joltio studio archive
- Nuevo: `joltio studio assets archive`.

#### joltio studio asset-defaults
- Nuevo: `joltio studio asset-defaults get`.

#### joltio studio assets
- Nuevo: `joltio studio assets list`.

#### joltio studio create-scenario
- Nuevo: `joltio studio scenario create`.

#### joltio studio edit-asset
- Nuevo: `joltio studio asset edit`.

#### joltio studio fork-scenario
- Nuevo: `joltio studio scenario fork`.

#### joltio studio get-run
- Nuevo: `joltio studio run get`.

#### joltio studio get-scenario
- Nuevo: `joltio studio scenario get`.

#### joltio studio history
- Nuevo: `joltio studio history`.

#### joltio studio latest-run
- Nuevo: `joltio studio run latest`.

#### joltio studio launch-search
- Nuevo: `joltio studio search launch`.

#### joltio studio list-runs
- Nuevo: `joltio studio runs list`.

#### joltio studio list-scenarios
- Nuevo: `joltio studio scenarios list`.

#### joltio studio list-searches
- Nuevo: `joltio studio searches list`.

#### joltio studio list-templates
- Nuevo: `joltio studio templates list`.

#### joltio studio load-profiles
- Nuevo: `joltio studio profiles load`.

#### joltio studio publish-run
- Nuevo: `joltio studio run publish`.

#### joltio studio run-scenario
- Nuevo: `joltio studio scenario run`.

#### joltio studio search-status
- Nuevo: `joltio studio status search`.

#### joltio studio update-defaults
- Nuevo: `joltio studio defaults update`.

#### joltio studio update-scenario
- Nuevo: `joltio studio scenario update`.

#### joltio workspaces list-workspaces
- Nuevo: `joltio workspaces workspace-workspaces list`.
