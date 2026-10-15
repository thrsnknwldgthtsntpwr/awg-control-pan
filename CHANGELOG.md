# Changelog

Формат: `## [версия] - дата` + списки `Added / Fixed / Changed / Security`.
Теги: `v0.1.1`–`v0.1.18`. Релизы `.deb` на GitHub — с `0.1.8` (старые удалены, теги оставлены).

## [0.1.18] - 2026-10-16

### Added

- «Клиенты»: сортировка кликом по заголовкам — Имя, IP (числовая через `ipaddress`), Статус (ранг `active/recent/…`), RX/TX (сумма `rx+tx` из `stats`), Срок (бессрочные `None` = `inf`). Параметры `?sort=name|ip|status|traffic|expires&dir=asc|desc`, дефолт `name/asc`, тайбрейкер — имя.
- «Система»: блок «Действия» — «Перезагрузить сервер» (`systemctl reboot` с задержкой 2с в daemon-потоке) и «Перезапустить awg» (`systemctl restart awg-quick@awg0`). Оба через GET-подтверждение («Перезагрузка сервера: Вы уверены?» / «Перезапуск AWG: Вы уверены?») + POST с CSRF, без инлайн-JS (CSP `script-src 'self'`, SSR).
- «Справка» (`/help`): пункт меню + блок «Github» со ссылками на `awg-control-pan` и `amneziawg-installer` (новая вкладка).
- Удаление клиентов двухшаговое: `POST /clients/delete` показывает «Удаление пользователей: Вы уверены?» со списком, удаляет только `POST /clients/delete/confirm` с CSRF.

### Changed

- Stable-чистка после `0.1.17`: удалён `packaging/sudoers` (в проде не использовался с `0.1.4`, сервис от root) + все упоминания (`conffiles`, `build_deb.sh`, `postinst`/`postrm`, `visudo`-проверки в CI).
- Убраны миграционные шимы: `useradd/userdel awgpanel`, чистка `set-password-internal` + `/etc/awg-panel/password` в `postinst`, чистка `webusername/webpassword` в `awg-panel-set-password` (нужны были только для апгрейда с версий до `0.1.4` / до `0.1.12`).
- Тесты без sudoers-файла: allowlist helper проверяется кодом (`run_helper`).
- Страница «Статус» переименована в «Система»: нав `Система (/system)`, вкладки убраны, всё на одной странице сверху вниз — Система → Интерфейсы → AWG → Действия → Журнал входов. Старый `/status` редиректит `303 → /system`, `/` и логин ведут на `/system`.
- `manage.py`: новые `cmd_awg_restart()` / `cmd_reboot_host()` через фиксированный `systemctl` (direct от root, `sudo -n` fallback для dev). Helper allowlist не тронут (`reboot` по-прежнему `ValueError`).
- Тесты: обновлены нав/редиректор на `/system`, добавлены `TestClientsSorting` (6 сортировок + заголовки-ссылки + порядок строк) и `TestSystemPage` (порядок блоков без табов, тексты подтверждений, `systemctl`-вызовы), `TestHelpPage` (блок Github, обе ссылки, активный нав), `TestClientsDeleteConfirm` (текст подтверждения, первый POST не удаляет, confirm удаляет), всего 77/77 OK.

## [0.1.17] - 2026-10-14

### Fixed

- Экран входа: фокус ввода теперь в поле «Логин» (`autofocus` перенесён с «Пароля»).

### Tests

- `test_autofocus_on_username`, всего 61/61 OK.

## [0.1.16] - 2026-10-14

### Changed

- Кнопка «Выход» всегда видна внизу сайдбара: `nav` — flex-колонка с `margin-top:auto` и разделителем, а сам сайдбар привязан к вьюпорту (`position:sticky; height:100vh`) — низ меню совпадает с низом видимой части страницы, скролл не нужен.

### Tests

- `test_logout_pinned_to_bottom`, всего 60/60 OK.

## [0.1.15] - 2026-10-14

### Changed

- Экран входа без меню: синий сайдбар (заголовок + версия) остался, пункты «Статус» / «Клиенты» / «Выход» убраны (`_layout(..., nav=False)`).
- Номер версии в сайдбаре — ссылка на GitHub проекта (открывается в новой вкладке).

### Tests

- `TestLoginPage` (пустой nav на входе, nav на остальных страницах, ссылка версии, CSS), всего 59/59 OK.

## [0.1.14] - 2026-10-14

### Added

- «Сгенерировать имя» дописывает новое имя через пробел, не затирая поле: так быстро готовится пачка имён за несколько кликов (разделители пробел/запятая разбирает `parse_names`).

### Changed

- Неактивные кнопки видно: `button:disabled` — серый текст (`#9ca3af`) + `cursor:not-allowed`, без подсветки по hover.
- Кнопки «Скопировать» в карточке клиента после успеха показывают «Скопировано» серым (класс `copied`, снимается при возврате текста); «Не скопировалось» цвет не меняет.

### Tests

- `test_generate_appends_with_space`, `test_disabled_and_copied_styles` + asserts класса `copied` в `test_copy_buttons_conf_and_vpn`, всего 55/55 OK.

## [0.1.13] - 2026-10-14

### Added

- Генератор имён на странице «Клиенты»: кнопка «Сгенерировать имя» подставляет `prefix` + случайный hex из `2*rand_bytes` символов (новая необязательная секция `[client_names]`, дефолт `prefix = user_`, `rand_bytes = 8` — аналог `user_$(openssl rand -hex N)`). Ошибки секции не роняют старт (fallback/clamp), итоговая длина `<= 63`.
- Тесты `TestClientNames` + `TestClientsListPage` (конфиг, `disabled` без выбора, ряд кнопок, `clients.js`-роут), всего 53/53 OK.

### Changed

- «Клиенты»: кнопки «Добавить» и «Удалить выбранные» в одном горизонтальном ряду (сабмитят свои формы через атрибут `form=`).
- Кнопка «Удалить выбранные» неактивна, пока не выбран ни один клиент (`/static/clients.js`, без инлайн-скриптов — CSP `script-src 'self'`).

### Fixed

- `AuthStore` с пустым `users` — сразу `ValueError` (fail-closed), без тихого fallback на `admin/admin`.

## [0.1.12] - 2026-10-14

### Added

- HTTP-редиректор: `http://<IP>:http_redirect_port/` отвечает только `301 Location: https://<IP>:<port>/` (путь/query сохраняются). Новый ключ `http_redirect_port` (дефолт `80`, `0` — выкл). Контент панели по HTTP никогда не отдаётся.
- Тесты `TestHttpRedirect` (URL-сборка, Host-валидация, live-`301` без кук).

### Changed

- **BREAKING:** авторизация только через `[users]` (`user.N/password.N`). Ключи `webusername`/`webpassword` больше не читаются (игнорируются); нет `[users]` — отказ старта. `awg-panel-set-password` пишет только `[users]` и чистит остатки legacy-ключей.
- Документация приведена к релизу (конфиг, установка, диагностика, безопасность).

### Fixed

- Нет тихого fallback на `admin/admin`: отсутствующий/битый конфиг — отказ старта с сообщением в `journalctl`.

## [0.1.11] - 2026-10-14

### Fixed

- `apt purge` теперь чистит всё: `postrm purge` удаляет `cert.pem`/`key.pem` (их создаёт `postinst`, dpkg бы их оставил), `config.ini`, пустой `/etc/awg-panel` и `/var/log/awg-panel`. `remove` по-прежнему оставляет конфиг и логи. `/root/awg` и `/etc/amnezia` не трогаются никогда.
- README приведён к релизу: актуальные конфиг (`[users]`, лимиты), fail-closed поведение, purge, тесты 40/40, FAQ без «один админ».

### Added

- Регресс-тест `test_postrm_purge_full_cleanup`.

## [0.1.10] - 2026-10-14

### Added

- Мультипользователь: секция `[users]` (`user.N/password.N`, `N=1..254`, max 254). При наличии `[users]` она важнее legacy `webusername/webpassword`; без неё — fallback на одного пользователя как раньше.
- Проверка при старте (fail-closed): дубль опции, `password.N` без `user.N` (и наоборот), плохой логин, пустой пароль, дубль логина, `>254` пользователей, неизвестные ключи в `[users]` — отказ старта с сообщением в `journalctl`, а не тихий fallback на `admin/admin`.
- Настраиваемый лимит входа: `auth_max_attempts` (`1..100`, дефолт 5) и `auth_lock_minutes` (`1..1440`, дефолт 5). Блокировка — средствами сервиса (ответ `429` с этого IP), без `iptables/ufw/nftables`.
- `awg-panel-set-password` правит `user.1/password.1` в `[users]` (+ зеркалит в legacy), остальных пользователей не трогает.
- Сессии хранят имя пользователя (`Session.username`).
- Тесты: мульти-юзер, валидация `[users]`, настраиваемый rate-limit, всего 39/39 OK.

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
