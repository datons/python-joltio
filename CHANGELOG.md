# Cambios de `joltio`

## 0.2.0

- Un solo paquete incluye la librería Python 0.1.0 y la CLI generada del OpenAPI. `joltio-toolkit` deja de ser el nombre de distribución.
- Los comandos de Data y `auth` de 0.1.0 conservan alias. La clave guardada en `~/.config/joltio/config.toml` sigue funcionando.
- Las credenciales se resuelven por argumento explícito, `JOLTIO_API_KEY` o `JOLTIO_TOKEN`, clave TOML existente y sesión de `joltio login`; la sesión se renueva mientras se usa y `logout` la revoca.
- MCP es un extra opcional. El motor de apps se descarga por versión y plataforma con verificación SHA-256. `data quickstart` reutiliza el ZIP público del panel.
- Funciona en Python 3.10 o superior, como 0.1.0.
- El código fuente público es el espejo de solo lectura https://github.com/datons/python-joltio, con una instantánea por versión.
