# lightrag-mcp-connect

[English](README.md) | **Русский** | [Español](README.es.md)

MCP-сервер для подключения Claude и других MCP-клиентов к базе знаний
[LightRAG](https://github.com/HKUDS/LightRAG).

Этот форк поддерживает загрузку документов из локальных файлов, URL и текста,
а также отдельные команды для полной замены документа и добавления текста.

## Требования

- работающий сервер LightRAG
- API-ключ LightRAG
- [`uv`](https://docs.astral.sh/uv/) для локального запуска

## Локальная настройка

Добавьте сервер в конфигурацию MCP-клиента:

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

`LIGHTRAG_FILE_PATH_ROOT` необязателен. Указывайте его только для чтения
локальных файлов. Файлы за пределами этого каталога будут отклонены.

После изменения конфигурации перезапустите MCP-клиент.

## Команды для документов

### Создание документа

Используйте один источник:

```text
upload_document(file_path)
upload_document(file_url)
upload_document(filename, text_content)
```

### Полная замена документа

Документ с таким же именем удаляется и индексируется заново с новым
содержимым:

```text
update_document(file_path)
update_document(file_url)
update_document(filename, text_content)
```

### Добавление текста в конец

```text
append_text(filename, text_content)
```

`append_text` работает с текстовыми документами, которыми управляет этот
MCP-сервер. Для ранее загруженного внешнего документа сначала один раз вызовите
`update_document` с полным текстом.

После изменения документа LightRAG автоматически перестраивает внутренний граф
знаний. Этот MCP не публикует команды управления графом.

## Другие команды

Сервер также поддерживает:

- просмотр, сканирование, удаление и проверку статуса документов
- запросы к базе знаний
- проверку состояния LightRAG и очереди обработки

Устаревшие команды `insert_text` и `insert_texts` не публикуются.

## Удалённая настройка

В каталоге `deploy/` находятся готовые конфигурации удалённого MCP-доступа
через HTTPS и OAuth.

```bash
git clone https://github.com/alexbic/lightrag-mcp-connect.git
cd lightrag-mcp-connect/deploy
cp .env.example .env
```

Заполните в `.env` переменные `DOMAIN`, `LIGHTRAG_URL`, `LIGHTRAG_API_KEY` и
`MCP_AUTH_PASSWORD`, затем запустите подходящую конфигурацию:

```bash
# Caddy
docker compose -f docker-compose.yml up -d --build

# Существующий Traefik
docker compose -f docker-compose.traefik.yml up -d --build
```

Для совместного запуска LightRAG и MCP-шлюза используйте
`docker-compose.full-example.yml`.

Добавьте в MCP-клиент адрес удалённого коннектора:

```text
https://mcp.example.com/mcp
```

## Настройки

| Переменная | Назначение |
|---|---|
| `LIGHTRAG_BASE_URL` | Адрес сервера LightRAG |
| `LIGHTRAG_API_KEY` | API-ключ LightRAG |
| `LIGHTRAG_FILE_PATH_ROOT` | Разрешённый каталог для `file_path` |
| `LIGHTRAG_MCP_CONTENT_DB` | Необязательный путь к SQLite для `append_text` |
| `LIGHTRAG_TIMEOUT` | Тайм-аут запросов в секундах |

Загрузка по URL запрещает адреса частных сетей и ограничена размером 50 МБ.

## Происхождение

Форк проекта
[desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp).
Он создан для поддержки удалённой загрузки документов и проверенного
удалённого MCP-развёртывания с сохранением простого локального запуска.

## Лицензия

MIT. См. [LICENSE](LICENSE).
