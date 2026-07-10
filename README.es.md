# lightrag-mcp-remote

[English](README.md) | [Русский](README.ru.md) | **Español**

Acceso remoto vía MCP, protegido con OAuth 2.1, a una base de conocimiento
[LightRAG](https://github.com/HKUDS/LightRAG) — conéctate desde claude.ai
(web/móvil), Claude Desktop o Claude Code desde cualquier lugar, no solo
desde la máquina que ejecuta LightRAG localmente.

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

Este fork agrega `file_content` (base64) + `filename` como alternativa:
el contenido viaja dentro de la propia llamada a la herramienta, sin
necesidad de sistema de archivos compartido. `file_path` se mantiene para
configuraciones de stdio local / misma máquina, donde todavía tiene
sentido.

```jsonc
// Antes (solo funciona si el servidor MCP puede leer esta ruta él mismo):
{ "file_path": "/some/local/path.pdf" }

// Después (funciona sin importar dónde se ejecute el agente que llama):
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
lightrag-mcp-remote (este repositorio, vía uvx-from-git)  ──  la herramienta MCP real
  ▼  X-API-Key
tu instancia de LightRAG
```

`lightrag-mcp-gw` nunca queda expuesto directamente — solo
`lightrag-mcp-auth` da a internet, y reenvía al gateway por una red
docker privada.

## Despliegue

Necesitas una instancia de LightRAG ya en ejecución, accesible desde este
stack. ¿Aún no tienes una? Ver
[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — este repositorio
solo añade la capa de MCP remoto encima.

```bash
git clone https://github.com/alexbic/lightrag-mcp-remote.git
cd lightrag-mcp-remote/deploy
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

## Conectar Claude

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
