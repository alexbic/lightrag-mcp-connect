# lightrag-mcp-connect

[English](README.md) | [Русский](README.ru.md) | **Español**

Acceso MCP a una base de conocimiento [LightRAG](https://github.com/HKUDS/LightRAG)
que funciona en ambos sentidos: **localmente** vía `uvx` (sin
configuración, acceso directo a archivos) cuando Claude corre en la
misma máquina que LightRAG, y **remotamente** vía un gateway protegido
con OAuth (ver `deploy/`) cuando quieres que claude.ai en tu teléfono, o
cualquier otro dispositivo, acceda a la misma base de conocimiento.
Misma herramienta, mismo `tools/list`, mismo código — solo elige el
transporte que corresponda a desde dónde llamas. Nada impide correr
ambos a la vez (ver "Usando ambos a la vez" más abajo).

Este es un fork de [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp)
(licencia MIT, conservada en `LICENSE`), más una receta completa en
`deploy/` para ejecutarlo como servidor MCP remoto:
[supergateway](https://github.com/supercorp-ai/supergateway)
(stdio → streamable-HTTP) protegido por
[mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) (OAuth 2.1).
Cada pieza de esto se construyó y verificó contra un despliegue real de
LightRAG en producción — los archivos compose bajo `deploy/` son lo que
realmente está en ejecución, no un boceto sin probar.

## Por qué existe esto

La propia historia de LightRAG con MCP es escueta — no hay un endpoint
MCP nativo, y el wrapper de la comunidad (`daniel-lightrag-mcp`) solo
funciona cuando el cliente MCP y el servidor MCP comparten un sistema de
archivos (es decir, stdio local, una sola máquina). Eso está bien para
Claude Desktop en tu propia laptop hablando con un LightRAG local. Se
rompe en el momento en que quieres que claude.ai en tu teléfono acceda a
la misma base de conocimiento — no hay sistema de archivos compartido
entre la infraestructura de Anthropic y tu servidor, y la herramienta
`upload_document` falla literalmente con `File does not exist` sin
importar qué ruta le des, porque intenta abrir esa ruta *localmente en el
servidor MCP*, no en la máquina de quien llama.

Conseguir que esto funcionara de extremo a extremo también implicó
arreglar (y documentar, más abajo) varios problemas no evidentes en el
camino:

- `supercorp/supergateway:uvx` no tiene el binario `git`, así que `uvx
  --from git+URL` falla al iniciar el contenedor — ver
  `deploy/mcp-gw/Dockerfile`.
- El modo `--stateful` de supergateway requiere que los clientes reenvíen
  un encabezado de sesión en cada solicitud; el cliente de Claude no lo
  hace de forma confiable, así que cada conexión moría justo después de
  `initialize` con un críptico "no tools available" en la interfaz de
  Claude. Solucionado *no* usando `--stateful`.
- El SDK de MCP incluido en supergateway solo reconoce versiones de
  protocolo hasta `2025-06-18` y rechaza de forma estricta el encabezado
  `MCP-Protocol-Version: 2025-11-25` que Claude envía en cada solicitud
  después de `initialize` — el mismo síntoma "no tools available", pero
  otra causa. Solucionado reescribiendo el encabezado en el reverse
  proxy (Caddy o Traefik, ver `deploy/`).
- `upload_document` solo aceptaba un `file_path` del lado del servidor —
  ver abajo, este es el arreglo de código real en este fork.

Nada de esto es culpa de LightRAG, y tampoco es realmente culpa de
`daniel-lightrag-mcp` — es lo que pasa cuando tomas una herramienta
pensada para stdio local y la estiras a través de una red. Este
repositorio es el resultado de hacer ese estiramiento una vez, bien
hecho, para que tú no tengas que hacerlo.

## Qué se arregló aquí frente al upstream

`upload_document` en el `daniel-lightrag-mcp` original solo acepta
`file_path`, que lee **localmente en el proceso del servidor MCP** — no
en la máquina de quien llama a la herramienta. Sobre stdio en tu propia
laptop, es la misma máquina, así que el problema es invisible. Sobre una
conexión MCP remota (Claude web/móvil/Desktop → este gateway, corriendo
en un servidor), nunca es la misma máquina, y la herramienta simplemente
falla.

Este fork agrega dos alternativas:

- **`file_url`** — un enlace público http(s) (por ejemplo, un archivo
  adjunto subido o una URL de artifact). El servidor MCP lo obtiene él
  mismo; nada del contenido del archivo pasa por el contexto ni los
  tokens de salida del agente que llama. Protegido contra SSRF:
  las solicitudes a direcciones privadas, loopback, link-local y
  reservadas (incluido el endpoint de metadatos de la nube) se rechazan
  antes de intentar cualquier conexión, y las descargas están limitadas
  a 50MB.
- **`file_content`** (base64) + `filename` — cuando no hay URL. El
  contenido viaja dentro de la propia llamada a la herramienta, sin
  necesidad de sistema de archivos compartido. Debería generarse con una
  llamada a un script/herramienta (por ejemplo, el comando `base64` de
  shell), no transcrito token por token por el modelo — además del costo
  en tokens, un bloque base64 grande incrustado también puede activar
  falsos positivos en clasificadores de seguridad de contenido, que lo
  interpretan como datos ofuscados.

`file_path` se mantiene para configuraciones de stdio local / misma
máquina, donde es gratis (el servidor lee el archivo directamente, sin
nada que descargar o codificar).

```jsonc
// Antes (solo funciona si el servidor MCP puede leer esta ruta él mismo):
{ "file_path": "/some/local/path.pdf" }

// Después — elige la que aplique, en este orden de preferencia:
{ "file_url": "https://example.com/report.pdf" }
{ "file_content": "<base64 bytes>", "filename": "report.pdf" }
```

## Arquitectura

```
claude.ai / Claude Desktop / Claude Code / app móvil
  │  https://mcp.example.com/mcp  (token Bearer OAuth 2.1)
  ▼
Caddy o Traefik  ──  TLS + reescribe el encabezado MCP-Protocol-Version
  ▼
lightrag-mcp-auth (mcp-auth-proxy)  ──  OAuth 2.1: DCR, PKCE, discovery,
  │                                     login único con contraseña
  ▼  (solo red privada, sin autenticación — no accesible desde internet)
lightrag-mcp-gw (supergateway)  ──  stdio ⇄ streamable-HTTP, sin estado
  ▼
lightrag-mcp-connect (este repositorio, vía uvx-from-git)  ──  la herramienta MCP real
  ▼  X-API-Key
tu instancia de LightRAG
```

`lightrag-mcp-gw` nunca queda expuesto directamente — solo
`lightrag-mcp-auth` da a internet, y reenvía al gateway por una red
docker privada.

## Uso local (sin configuración)

Si Claude corre en la misma máquina que tu instancia de LightRAG
(Claude Desktop o Claude Code en tu propia laptop, hablando con un
LightRAG local o en el mismo host), sáltate todo lo anterior — no hace
falta gateway OAuth, ni `deploy/`, ni `git clone`, ni entorno virtual.
Apunta un cliente MCP directamente a este paquete vía
[`uvx`](https://docs.astral.sh/uv/) de `uv`:

```json
{
  "mcpServers": {
    "lightrag": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "tu-api-key-de-lightrag"
      }
    }
  }
}
```

`uvx` se instala una vez (`curl -LsSf https://astral.sh/uv/install.sh |
sh`), y luego obtiene este paquete en un entorno aislado y cacheado en
la primera ejecución — sin clonar manualmente ni `pip install`. Corriendo
así también obtienes soporte de `file_path` gratis: el servidor MCP lee
los archivos directamente desde tu disco, ya que es la misma máquina que
la herramienta que llama.

Para fijar un commit específico en vez de seguir siempre `main`, añade
`@<commit>` a la URL:
`git+https://github.com/alexbic/lightrag-mcp-connect.git@<commit>`.

## Despliegue (remoto)

Necesitas una instancia de LightRAG ya en ejecución, accesible desde este
stack. ¿Aún no tienes una? Ver
[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — este repositorio
solo añade la capa de MCP remoto encima.

```bash
git clone https://github.com/alexbic/lightrag-mcp-connect.git
cd lightrag-mcp-connect/deploy
cp .env.example .env
# edita .env: DOMAIN, LIGHTRAG_URL, LIGHTRAG_API_KEY, MCP_AUTH_PASSWORD

# Sin reverse proxy existente — Caddy gestiona el TLS automáticamente:
docker compose -f docker-compose.yml up -d --build

# ¿Ya usas Traefik? Configura también TRAEFIK_NETWORK en .env:
docker compose -f docker-compose.traefik.yml up -d --build
```

¿Usas un reverse proxy distinto? Ver el bloque de comentarios al inicio
de `docker-compose.traefik.yml` — dos requisitos, con ejemplos para
nginx y Caddy.

## Conectar Claude (remoto)

En claude.ai (o Claude Desktop, o Claude Code): **Settings → Connectors →
Add custom connector**, introduce:

```
https://mcp.example.com/mcp
```

Deja Client ID / Client Secret en blanco — `mcp-auth-proxy` gestiona la
Dynamic Client Registration de OAuth por sí mismo. Se te redirigirá a una
pantalla de login única (la `MCP_AUTH_PASSWORD` que configuraste);
después de eso, Claude gestiona la renovación de su propio token OAuth y
no necesitarás la contraseña de nuevo hasta que autorices un nuevo
cliente.

## Usando ambos a la vez

Nada impide configurar el setup local (`uvx`) y el remoto (gateway
OAuth) al mismo tiempo, con nombres de servidor distintos, en el mismo
cliente MCP:

```json
{
  "mcpServers": {
    "lightrag-local": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "tu-api-key-de-lightrag"
      }
    }
  }
}
```

más el gateway remoto agregado como custom connector (ver "Conectar
Claude (remoto)" arriba), con otro nombre. Usa `lightrag-local` cuando
quieras que `file_path` funcione con archivos que están realmente en tu
máquina; usa el conector remoto desde tu teléfono, o desde cualquier
dispositivo donde no vivan los archivos de LightRAG. Es la misma base de
conocimiento y el mismo código de la herramienta MCP en ambos casos —
solo dos transportes distintos (stdio vs. streamable-HTTP-sobre-OAuth)
apuntando a ella.

## Herramientas

Se exponen 20 herramientas vía `tools/list` — gestión de documentos
(insertar, subir, escanear, recuperar, eliminar), consultas (normales y
en streaming), grafo de conocimiento (entidades, relaciones, etiquetas) y
estado del sistema.

Otras dos (`clear_documents`, `clear_cache`) están implementadas en el
upstream pero comentadas en la declaración de `tools/list`, así que
ningún cliente MCP conforme las ve — sus manejadores siguen existiendo en
el servidor, y técnicamente son accesibles mediante un `tools/call`
directo que evita el discovery. No se modificó en este fork; se menciona
aquí para que no sea una sorpresa.

## Notas de seguridad

- El `file_url` de `upload_document` hace que el servidor MCP obtenga
  una URL proporcionada por quien llama. Rechaza direcciones privadas/
  loopback/link-local/reservadas (incluido el endpoint de metadatos de
  la nube) antes de conectar, y limita las descargas a 50MB — una
  defensa SSRF básica, no completa (no protege contra DNS rebinding
  entre la verificación y la solicitud). Cualquiera con un token OAuth
  válido puede usarlo para hacer que tu servidor emita solicitudes HTTP
  salientes a URLs públicas arbitrarias.
- Las herramientas destructivas (`delete_document`, `delete_entity`,
  `delete_relation`, `update_entity`, `update_relation`) están activas y
  accesibles para cualquiera que tenga un token OAuth válido para tu
  instancia. Ni `supergateway` ni `mcp-auth-proxy` filtran herramientas
  individuales — el control de acceso es todo-o-nada a nivel de conexión.
- El modo de contraseña de `mcp-auth-proxy` está pensado para un único
  propietario, no para acceso multiusuario. Si necesitas cuentas por
  usuario, apúntalo a Google/GitHub/OIDC en su lugar (`mcp-auth-proxy`
  soporta los tres — ver su propia
  [documentación](https://sigbit.github.io/mcp-auth-proxy/)) en vez de
  compartir una sola contraseña.
- Rotar la contraseña: genera una nueva, configura `MCP_AUTH_PASSWORD`,
  redespliega. Los tokens OAuth ya emitidos para conexiones existentes
  seguirán funcionando — la nueva contraseña solo se necesita para
  autorizar clientes *nuevos*.

## Créditos

- [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp) —
  la herramienta MCP original de la que se hizo este fork (MIT).
- [supercorp-ai/supergateway](https://github.com/supercorp-ai/supergateway) —
  puente stdio ⇄ streamable-HTTP.
- [sigbit/mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) —
  gateway OAuth 2.1 listo para usar en servidores MCP.
- [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — la base de
  conocimiento frente a la que se sitúa todo esto.

## Licencia

MIT — ver `LICENSE`. Copyright original de Daniel Simpkins; cambios en
este fork de Alex Bic.
