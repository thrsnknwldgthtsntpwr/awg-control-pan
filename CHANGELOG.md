# Changelog

Формат: `## [версия] - дата` + списки `Added / Fixed / Changed / Security`.
Теги: `v0.1.1`–`v0.1.9`. Релизы `.deb` на GitHub — с `0.1.8` (старые удалены, теги оставлены).

## [0.1.9] - 2026-10-14

### Fixed

- Кнопки «Скопировать» снова работают: инлайн-`<script>` блокировался CSP `script-src 'self'` (введён в 0.1.8) — JS вынесен в same-origin `/static/copy.js` (`COPY_TAG <script src defer>`).
- `copy.js` переписан устойчиво: Clipboard API → race 3с → `textarea+execCommand` fallback, честные подписи «Скопировано» / «Не скопировалось», привязка через `DOMContentLoaded`.

### Added

- Тесты: `test_copy_js_static_route` (200 + `javascript` + CSP + тело `== COPY_JS`), всего 30/30 OK. Проверено `node --check` + 5 DOM-стаб сценариев.

## [0.1.8] - 2026-10-13

### Security

- Ревью безопасности: игнор `X-Forwarded-For` в rate-limit, `413 + close_connection` на больших формах, `timeout=10 / daemon_threads`, `hmac` без `TypeError`, `FUT_TIMEOUT=40`, `MAX_SEL=100 / MAX_FORM_FIELDS=2000 / MAX_HELPER_BYTES=2MiB`, `fmt` без 500, `try` вокруг статус-блоков.
- Заголовки: `CSP default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'` + `HSTS` + `Permissions-Policy`; `303` после POST; `filename*`; `405` на лишние методы; HTMX/CDN удалён; ошибки manage обобщены.
- Auth: `Lock`, cap 1000 сессий (evict oldest), абсолютный лимит 12 ч, журнал `0600` + санитизация, `repr=False` у пароля.
- Config: `interpolation=None` (`%` в пароле), fallback без падения, пароль не strip'ится.
- Manage/helper: проверка `expires` внутри, allowlist helper, cap stdout/батча.
- Helper/set-password/postinst: `pipefail/PATH/symlink-reject`, атомарная запись `0600+umask 077`, `umask 077` для `key.pem/config`.

### Changed

- README приведён к 0.1.8. Тесты 29/29 OK.

## [0.1.7] - 2026-10-13

### Fixed

- Одинаковые кнопки в карточке клиента: `<button>` рисовался шрифтом браузера, `<a class=btn>` — шрифтом страницы. В общий rule `button,.btn` добавлен `font:inherit (+vertical-align:middle)`.
- Регресс-тест `test_buttons_unified_font`, всего 29/29 OK.

## [0.1.6] - 2026-10-13

### Added

- Три кнопки Пира в одном горизонтальном ряду (`div.actions`, `margin-top:12px`).
- Кнопки «Скопировать» внизу блоков Конфиг (`id=conf-pre`) и `vpn://` (`id=vpn-pre`): `navigator.clipboard.writeText` + fallback `execCommand`, подпись «Скопировано» 1.5с.
- Тесты `TestClientPage` +2, всего 28/28 OK.

## [0.1.5] - 2026-10-13

### Fixed

- Убран page-level h-scroll: `body/main overflow-x:hidden`, `.card min/max-width`, `.grid>* min-width:0`, `pre max-width:100%+overflow:auto`, `img max-width:100%`.

### Changed

- Карточка клиента: блоки отдельными card в `.stack` сверху вниз (Пир / Конфиг / `vpn://` / QR). Кнопка `QR.png` — `target=_blank rel=noopener` на `/client-qr`.
- Тесты `TestClientPage` 3 шт, всего 26/26 OK.

## [0.1.4] - 2026-10-13

### Fixed

- **Крит:** `manage check failed (rc=1)` / `list failed rc=1` + `sudo: unable to change to root gid` / `sudoers_audit`. Причина — песочница service (`CapabilityBoundingSet=` резал setuid для sudo; `ProtectSystem=strict + ReadOnlyPaths` делали `/root/awg` и `/etc/amnezia` read-only).
- Решение — сервис от `root` без sudo и строгой песочницы (только `PrivateTmp`); `manage/helper` напрямую; `sudoers` оставлен как legacy-conffile; из `Depends` убран `sudo`; `key.pem` снова `600 root:root`.

### Changed

- Auth упрощён: только `webusername/webpassword` в `[server]` `config.ini` (дефолт `admin/admin`, `600 root:root`). Отдельный password-файл, PBKDF2 и `awg-panel-set-password-internal` удалены; `awg-panel-set-password` правит `config.ini`. `postinst` мигрирует старые конфиги и чистит legacy.

## [0.1.3] - 2026-10-13

### Fixed

- **Крит e2e 0.1.2:** restart-loop `TLS load failed (...key.pem): Permission denied` — `postinst` делал `key.pem 600` при owner `root:awgpanel`, сервис `User=awgpanel` читать не мог. Фикс: `key.pem 640` + self-heal owner/perms при каждом `configure`.

## [0.1.2] - 2026-10-13

### Added

- `postinst` печатает RU-инструкцию «что дальше»; то же в README.
- Документировано безвредное `_apt`-предупреждение (`dpkg -i` / копия в `/tmp`).

### Fixed

- **Крит:** `.deb 0.1.1` с `uid 1001` привёз sudoers, ломающий весь sudo. `build_deb.sh`: `chown -R 0:0` + `dpkg-deb --root-owner-group`; `postinst` чинит `chown root:root + 440` перед `visudo` при каждом upgrade.

## [0.1.1] - 2026-10-13

- Первый публичный MVP: `src/awg_panel`, `helper+set-password`, `packaging` (`.deb`, service, sudoers, postinst), `build_deb.sh`, workflow, 12 тестов.
- Известная проблема: sudoers с `uid 1001` (починено в 0.1.2), нет «что дальше» (добавлено в 0.1.2).
