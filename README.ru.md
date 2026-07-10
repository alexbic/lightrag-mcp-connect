# lightrag-mcp-remote

[English](README.md) | **Русский** | [Español](README.es.md)

Удалённый доступ к базе знаний [LightRAG](https://github.com/HKUDS/LightRAG)
по MCP-протоколу, защищённый OAuth 2.1 — подключайся из claude.ai
(веб/мобильное приложение), Claude Desktop или Claude Code откуда угодно,
а не только с машины, на которой физически крутится LightRAG.

Это форк [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp)
(лицензия MIT, сохранена в `LICENSE`), плюс полный рецепт деплоя в
`deploy/` для запуска в виде удалённого MCP-сервера:
[supergateway](https://github.com/supercorp-ai/supergateway)
(stdio → streamable-HTTP), защищённый через
[mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) (OAuth 2.1).
Каждая часть этой связки собрана и проверена на реальном production
LightRAG-деплое — файлы compose в `deploy/` это то, что реально
работает, а не непроверенный набросок.

## Зачем это нужно

У LightRAG самого по себе очень скромная MCP-история — нет нативного
MCP-эндпоинта, а community-обёртка (`daniel-lightrag-mcp`) работает
только тогда, когда MCP-клиент и MCP-сервер делят одну файловую систему
(то есть локальный stdio, одна машина). Это нормально для Claude Desktop
на твоём ноутбуке, говорящего с локальным LightRAG. Но всё разваливается
в момент, когда ты хочешь достучаться до той же базы знаний с телефона
через claude.ai — между инфраструктурой Anthropic и твоим сервером нет
общей файловой системы, и инструмент `upload_document` буквально падает
с ошибкой `File does not exist`, какой бы путь ты ни передал — потому что
он пытается открыть этот путь *локально на MCP-сервере*, а не на машине
вызывающего.

Чтобы это заработало end-to-end, пришлось исправить (и задокументировать
ниже) несколько неочевидных проблем по пути:

- У `supercorp/supergateway:uvx` нет бинарника `git`, поэтому `uvx --from
  git+URL` падает при старте контейнера — см. `deploy/mcp-gw/Dockerfile`.
- `--stateful` режим supergateway требует, чтобы клиент пересылал
  session-заголовок на каждый запрос; клиент Claude не делает это
  надёжно, из-за чего каждое соединение умирало сразу после `initialize`
  с непонятной надписью "no tools available" в интерфейсе Claude.
  Исправлено отказом от `--stateful`.
- Встроенный MCP SDK в supergateway распознаёт версии протокола только
  до `2025-06-18` и жёстко отклоняет заголовок
  `MCP-Protocol-Version: 2025-11-25`, который Claude шлёт на каждый
  запрос после `initialize` — тот же симптом "no tools available", но
  другая причина. Исправлено перезаписью заголовка на уровне
  reverse-proxy (Caddy или Traefik, см. `deploy/`).
- `upload_document` принимал только серверный `file_path` — см. ниже,
  это и есть реальный фикс кода в этом форке.

Ничего из этого не вина LightRAG, да и не совсем вина
`daniel-lightrag-mcp` — это то, что происходит, когда инструмент,
рассчитанный на локальный stdio, растягивают через границу сети. Этот
репозиторий — результат того, что кто-то один раз сделал это растягивание
как следует, чтобы тебе не пришлось.

## Что исправлено здесь по сравнению с апстримом

`upload_document` в апстримовском `daniel-lightrag-mcp` принимает только
`file_path`, который читается **локально в процессе MCP-сервера** — не
на машине того, кто вызывает инструмент. Через stdio на твоём собственном
ноутбуке это одна и та же машина, поэтому проблема невидима. Через
удалённое MCP-соединение (Claude web/mobile/Desktop → этот гейтвей,
работающий на сервере) это никогда не одна и та же машина, и инструмент
просто падает.

Этот форк добавляет две альтернативы:

- **`file_url`** — публичная http(s)-ссылка (например, на загруженное
  вложение или артефакт). MCP-сервер сам скачивает файл по ней; ничего
  из содержимого файла не проходит через контекст или выходные токены
  вызывающего агента. Защита от SSRF: запросы к приватным, loopback,
  link-local и зарезервированным адресам (включая cloud metadata
  endpoint) отклоняются до попытки соединения, размер ограничен 50MB.
- **`file_content`** (base64) + `filename` — когда ссылки нет. Контент
  едет прямо внутри вызова инструмента, общая файловая система не нужна.
  Должно генерироваться скриптом/инструментом (например, командой shell
  `base64`), а не пословным переписыванием моделью — кроме затрат
  токенов, большой base64-блок в тексте ещё и может ложно сработать на
  классификаторе безопасности контента, приняв его за обфусцированные
  данные.

`file_path` оставлен для случаев, когда MCP-сервер и клиент на одной
машине (локальный stdio) — там он бесплатный (сервер читает файл
напрямую, ничего скачивать или кодировать не нужно).

```jsonc
// До (работает, только если MCP-сервер сам может прочитать этот путь):
{ "file_path": "/some/local/path.pdf" }

// После — выбирай подходящее, в порядке предпочтения:
{ "file_url": "https://example.com/report.pdf" }
{ "file_content": "<base64 bytes>", "filename": "report.pdf" }
```

## Архитектура

```
claude.ai / Claude Desktop / Claude Code / мобильное приложение
  │  https://mcp.example.com/mcp  (OAuth 2.1 Bearer token)
  ▼
Caddy или Traefik  ──  TLS + перезапись заголовка MCP-Protocol-Version
  ▼
lightrag-mcp-auth (mcp-auth-proxy)  ──  OAuth 2.1: DCR, PKCE, discovery,
  │                                     разовый логин по паролю
  ▼  (только приватная сеть, авторизация не нужна — не торчит в интернет)
lightrag-mcp-gw (supergateway)  ──  stdio ⇄ streamable-HTTP, stateless
  ▼
lightrag-mcp-remote (этот репозиторий, через uvx-from-git)  ──  сам MCP-инструмент
  ▼  X-API-Key
твой инстанс LightRAG
```

`lightrag-mcp-gw` никогда не торчит наружу напрямую — в интернет смотрит
только `lightrag-mcp-auth`, и он же пересылает запросы на гейтвей по
приватной docker-сети.

## Деплой

Нужен уже работающий инстанс LightRAG, доступный из этого стека. Ещё нет
своего? Смотри [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — этот
репозиторий только добавляет сверху слой удалённого MCP.

```bash
git clone https://github.com/alexbic/lightrag-mcp-remote.git
cd lightrag-mcp-remote/deploy
cp .env.example .env
# заполни .env: DOMAIN, LIGHTRAG_URL, LIGHTRAG_API_KEY, MCP_AUTH_PASSWORD

# Нет своего reverse-proxy — Caddy сам делает HTTPS:
docker compose -f docker-compose.yml up -d --build

# Уже используешь Traefik? Дополнительно задай TRAEFIK_NETWORK в .env:
docker compose -f docker-compose.traefik.yml up -d --build
```

Используешь другой reverse-proxy? Смотри блок комментариев в начале
`docker-compose.traefik.yml` — там два требования с примерами для nginx и
Caddy.

## Подключение Claude

В claude.ai (или Claude Desktop, или Claude Code): **Settings →
Connectors → Add custom connector**, введи:

```
https://mcp.example.com/mcp
```

Client ID / Client Secret оставь пустыми — `mcp-auth-proxy` сам делает
OAuth Dynamic Client Registration. Тебя перекинет на разовый экран
логина (тот самый `MCP_AUTH_PASSWORD`); после этого Claude сам управляет
обновлением своего OAuth-токена, и пароль больше не понадобится — пока
не будешь авторизовывать нового клиента.

## Инструменты

Через `tools/list` доступно 20 инструментов — управление документами
(вставка, загрузка, сканирование, получение, удаление), запросы (обычные
и потоковые), граф знаний (сущности, связи, метки) и статус системы.

Ещё два (`clear_documents`, `clear_cache`) реализованы в апстриме, но
закомментированы в объявлении `tools/list`, так что ни один
конформный MCP-клиент их не видит — их обработчики всё ещё существуют на
сервере и технически доступны через прямой `tools/call` в обход
discovery. В этом форке не тронуто; упомянуто здесь, чтобы не стало
сюрпризом.

## Заметки по безопасности

- `file_url` у `upload_document` заставляет MCP-сервер скачивать URL,
  переданный вызывающим. Отклоняет приватные/loopback/link-local/
  зарезервированные адреса (включая cloud metadata endpoint) до
  соединения, ограничивает скачивание 50MB — базовая защита от SSRF, не
  исчерпывающая (не защищает от DNS rebinding между проверкой и самим
  запросом). Любой с валидным OAuth-токеном может заставить твой сервер
  делать исходящие HTTP-запросы на произвольные публичные адреса.
- Деструктивные инструменты (`delete_document`, `delete_entity`,
  `delete_relation`, `update_entity`, `update_relation`) активны и
  доступны любому, у кого есть валидный OAuth-токен для твоего инстанса.
  Ни `supergateway`, ни `mcp-auth-proxy` не фильтруют отдельные
  инструменты — контроль доступа работает по принципу всё-или-ничего на
  уровне соединения.
- Режим пароля в `mcp-auth-proxy` рассчитан на одного владельца, а не на
  многопользовательский доступ. Если нужны отдельные аккаунты —
  подключи Google/GitHub/OIDC (`mcp-auth-proxy` поддерживает все три, см.
  его [документацию](https://sigbit.github.io/mcp-auth-proxy/)), а не
  раздавай один общий пароль.
- Смена пароля: сгенерируй новый, задай `MCP_AUTH_PASSWORD`, передеплой.
  Уже выданные OAuth-токены для существующих подключений продолжат
  работать — новый пароль понадобится только для *новых* авторизаций
  клиентов.

## Благодарности

- [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp) —
  оригинальный MCP-инструмент, от которого сделан этот форк (MIT).
- [supercorp-ai/supergateway](https://github.com/supercorp-ai/supergateway) —
  мост stdio ⇄ streamable-HTTP.
- [sigbit/mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) —
  готовый OAuth 2.1 шлюз для MCP-серверов.
- [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — база знаний,
  перед которой всё это стоит.

## Лицензия

MIT — см. `LICENSE`. Оригинальные авторские права принадлежат Daniel
Simpkins; изменения в этом форке — Alex Bic.
