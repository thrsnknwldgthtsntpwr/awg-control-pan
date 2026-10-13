# MEMORY.md — общая память проекта

> Этот файл — единый источник контекста для всех сессий.
> Все изменения фиксировать здесь. Читать в начале каждой сессии, обновлять в конце.

## Проект
- Каталог: `D:\awg-control-pan-project-folder`
- Название: awg-panel — веб-интерфейс поверх bivlked/amneziawg-installer
- Статус: MVP написан (2026-10-13), тесты OK, e2e только на VPS
- Назначение: управление уже установленным AWG-сервером: Статус (Сервер/AWG), Клиенты (таблица list --verbose, add/del/regen, карточка с conf/vpnuri/QR), без своей БД VPN

## Правила работы в нескольких сессиях
1. В начале сессии — прочитать этот файл целиком.
2. В конце сессии — дописать в `## Журнал изменений` что сделано, какими файлами, какой результат.
3. Важные решения и договорённости — в `## Решения`.
4. Активные задачи — в `## Текущее состояние`.

## Текущее состояние
- [x] Решения по стеку собраны: Python stdlib, SSR+HTMX(CDN), один админ, HTTPS self-signed
- [x] Ответы пп.1-10 получены (sudo-вариант б, меню Статус/Клиенты/Выход, срок только днями, порт в конфиге, UFW не трогать, журнал входов да, .deb на GitHub, только RU, версию/поколение показывать)
- [x] MVP написан: src/awg_panel (server/manage/system_info/auth/config/validate), bin helper+set-password, packaging (.deb, service, sudoers, postinst), build_deb.sh, workflow, tests 6/6 OK, smoke рендера OK
- [x] Фидбэк применён: host 0.0.0.0:8443, массовый regen убран, журнал как есть
- [x] Локальный git: init + первый коммит (2026-10-13)
- [x] Ревью проведено (2026-10-13): найдены критичные баги service (NoNewPrivileges/ProtectHome) и sudoers (--expires), плюс 10+ средних
- [x] Правки ревью внесены (2026-10-13): service/sudoers/helper/postinst/server/auth/config/manage/system_info/build, tests 12/12 OK
- [ ] e2e на VPS с живым manage (list/add/remove/check/stats/regen, QR/conf/vpnuri, sudoers, postinst, service)

## Решения
- 2026-10-13: Память ведётся в этом файле (`MEMORY.md`) в корне каталога для работы в нескольких сессиях.
- 2026-10-13: Проверены доступы: чтение / запись / удаление — OK. Каталог пуст, полные права есть.
- 2026-10-13: Стек: Python stdlib http.server+ssl (без nginx), SSR+HTMX через CDN с деградацией без JS, один admin (PBKDF2, сессии в памяти, журнал в файл), HTTPS self-signed из postinst, сервис awgpanel+sudoers точечно, UFW не трогать, .deb arch=all с релизом на GitHub.
- 2026-10-13: Underlay-контракт: list/stats/check/add/remove/regen через manage --json; show/dump целиком не показываем (PSK); server PrivateKey никогда в браузер; клиентские conf/vpnuri/png — через helper с валидацией имён; /proc только для вкладки Сервер.

## Журнал изменений
- 2026-10-13: Инициализация памяти. Проверка доступов: `read` OK, `write` OK (` .access_test.tmp` создан и удалён), `icacls` — полные права. Каталог пуст.
- 2026-10-13: MVP awg-panel: src/awg_panel/{server,manage,system_info,auth,config,validate}, bin/{helper,set-password}, packaging/{DEBIAN,service,sudoers}, build_deb.sh, workflow, README. Проверки: py_compile OK, unittest 6/6 OK, smoke рендера OK (layout/server/table), bash -n helper/postinst/build OK. disk_usage починен для Windows-dev (statvfs guard).
- 2026-10-13: По фидбэку: host по дефолту 0.0.0.0:8443 (без изменений), массовый regen убран из списка клиентов (только в карточке), журнал = файл + последние 10 на Статусе. Перепроверено: py_compile + unittest 6/6 OK.
- 2026-10-13: Локальный git: init, коммит MVP (674ddbb), коммит чистки pycache+.gitignore (6bdf404). Дерево чистое.
- 2026-10-13: Ревью + правки: критично — service NoNewPrivileges=no/ProtectHome=read-only+ReadOnlyPaths+Restart (packaging/awg-panel.service), sudoers --expires=* add * + helper по командам + Defaults env_reset (packaging/sudoers); безопасность — пароль только через stdin (bin/awg-panel-set-password-internal + postinst printf|internal + unset), Cache-Control: no-store (server._send/_send_auth), HTMX SRI sha384 (server.HTMX), logout только POST+confirm (server do_GET/do_POST/_layout), helper хардкод путей + $# guard, stderr helper больше не течёт в браузер; среднее — refresh cookie (_send_auth), лимит форм 1МБ/413, sel invalid→ошибка, regen→/client?name=, параллельные manage (ThreadPool), mem_info guard, config clamp host/ttl/paths, manage единый парсер, log errors в stderr, run() понятные ошибки TLS, build без pycache + ship config.ini + проверка VER. Проверки: py_compile OK, unittest 12/12 OK, smoke layout/SRI OK.
