# lightrag-mcp-connect

[English](README.md) | [Русский](README.ru.md) | **Español**

Servidor MCP para conectar Claude y otros clientes MCP con una base de
conocimiento [LightRAG](https://github.com/HKUDS/LightRAG).

Este fork permite cargar documentos desde archivos locales, URL y texto, y
ofrece comandos separados para reemplazar documentos y añadir texto.

## Requisitos

- un servidor LightRAG en funcionamiento
- una clave API de LightRAG
- [`uv`](https://docs.astral.sh/uv/) para uso local

## Configuración local

Añade el servidor a la configuración de tu cliente MCP:

```json
{
  "mcpServers": {
    "lightrag": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git@v1.1.1",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "your-api-key",
        "LIGHTRAG_FILE_PATH_ROOT": "/Users/you/Documents"
      }
    }
  }
}
```

`LIGHTRAG_FILE_PATH_ROOT` es opcional. Configúralo solo si el servidor MCP debe
leer archivos locales. Los archivos fuera de este directorio serán rechazados.

Reinicia el cliente MCP después de cambiar la configuración.

## Comandos de documentos

### Crear un documento

Usa una sola fuente:

```text
upload_document(file_path)
upload_document(file_url)
upload_document(filename, text_content)
```

### Reemplazar un documento

El documento con el mismo nombre se elimina y se vuelve a indexar con el nuevo
contenido:

```text
update_document(file_path)
update_document(file_url)
update_document(filename, text_content)
```

### Añadir texto al final

```text
append_text(filename, text_content)
```

`append_text` funciona con documentos de texto administrados por este servidor
MCP. Para un documento externo existente, ejecuta primero `update_document` con
su texto completo.

LightRAG reconstruye automáticamente su grafo de conocimiento interno después
de los cambios. Este MCP no publica comandos para administrar el grafo.

## Otros comandos

El servidor también permite:

- listar, escanear, eliminar y consultar el estado de documentos
- realizar consultas a la base de conocimiento
- consultar el estado de LightRAG y de la cola de procesamiento

Los comandos obsoletos `insert_text` e `insert_texts` no se publican.

## Configuración remota

El directorio `deploy/` contiene configuraciones listas para acceso MCP remoto
mediante HTTPS y OAuth.

```bash
git clone https://github.com/alexbic/lightrag-mcp-connect.git
cd lightrag-mcp-connect/deploy
cp .env.example .env
```

Configura `DOMAIN`, `LIGHTRAG_URL`, `LIGHTRAG_API_KEY` y `MCP_AUTH_PASSWORD` en
`.env`, y ejecuta una configuración:

```bash
# Caddy
docker compose -f docker-compose.yml up -d --build

# Traefik existente
docker compose -f docker-compose.traefik.yml up -d --build
```

Para ejecutar LightRAG y la puerta de enlace MCP juntos, usa
`docker-compose.full-example.yml`.

Añade la URL del conector remoto a tu cliente MCP:

```text
https://mcp.example.com/mcp
```

## Configuración

| Variable | Uso |
|---|---|
| `LIGHTRAG_BASE_URL` | URL del servidor LightRAG |
| `LIGHTRAG_API_KEY` | Clave API de LightRAG |
| `LIGHTRAG_FILE_PATH_ROOT` | Directorio permitido para `file_path` |
| `LIGHTRAG_MCP_CONTENT_DB` | Ruta SQLite opcional usada por `append_text` |
| `LIGHTRAG_TIMEOUT` | Tiempo de espera en segundos |

Las descargas por URL rechazan redes privadas y están limitadas a 50 MB.

## Origen

Fork de
[desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp).
Se creó para admitir cargas remotas de documentos y un despliegue MCP remoto
probado, manteniendo sencillo el uso local mediante stdio.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
