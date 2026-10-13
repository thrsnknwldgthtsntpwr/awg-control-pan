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
- [x] e2e на VPS частично: установка 0.1.1 показала 2 проблемы — (1) нет инструкции что дальше, (2a) безвредное _apt-предупреждение про песочницу, (2b) КРИТ: sudoers с владельцем uid 1001 ломает весь sudo
- [x] выпустить 0.1.2: push master (10 коммитов) + тег v0.1.2 → CI build-deb.yml собирает релиз; локальная сборка в WSL OK (18222 байт, sha256 db112316…, все файлы root/root, sudoers 440, visudo parsed OK, postinst с баннером)
- [x] e2e-повтор 0.1.2 на VPS: КРИТ — сервис в restart-loop `TLS load failed Permission denied` (журнал 152→161 рестарты); причина — postinst делал key.pem 600 при owner root:awgpanel, сервис User=awgpanel читать не может
- [ ] выпустить 0.1.3: key.pem 640 + self-heal owner/perms при каждом configure (тест 16/16 OK), нужен push+тег и проверка на VPS
- [x] push 0.1.3: master 5fe8046..912d23b + тег v0.1.3 → CI build-deb.yml собирает .deb и Release; remote отчищен от токена, дерево в sync; токен был показан в чате — отозвать/перевыпустить
- [x] push 0.1.4: master 912d23b..c89ee38 + тег v0.1.4 → CI build-deb.yml собирает .deb и Release; локальная сборка в WSL OK (18538 байт, sha256 88d8d4ed…, тесты 23/23 OK); остался e2e на VPS (upgrade поверх 0.1.3)

## Решения
- 2026-10-13: Память ведётся в этом файле (`MEMORY.md`) в корне каталога для работы в нескольких сессиях.
- 2026-10-13: Проверены доступы: чтение / запись / удаление — OK. Каталог пуст, полные права есть.
- 2026-10-13: Стек: Python stdlib http.server+ssl (без nginx), SSR+HTMX через CDN с деградацией без JS, один admin (PBKDF2, сессии в памяти, журнал в файл), HTTPS self-signed из postinst, сервис awgpanel+sudoers точечно, UFW не трогать, .deb arch=all с релизом на GitHub.
- 2026-10-13: Underlay-контракт: list/stats/check/add/remove/regen через manage --json; show/dump целиком не показываем (PSK); server PrivateKey никогда в браузер; клиентские conf/vpnuri/png — через helper с валидацией имён; /proc только для вкладки Сервер.
- 2026-10-13: 0.1.4 — упрощение auth: логин/пароль только `webusername`/`webpassword` в `[server]` config.ini (дефолт admin/admin, 600 root:root). Отдельный password-файл, PBKDF2 и `awg-panel-set-password-internal` удалены; `awg-panel-set-password` теперь правит config.ini. postinst мигрирует старые конфиги (дописывает дефолты) и чистит legacy.
- 2026-10-13: 0.1.4 — фикс `manage check failed (rc=1)` / `list failed rc=1` + `sudo: unable to change to root gid` / `sudoers_audit`: причина — песочница service (CapabilityBoundingSet= пустой резал setuid для sudo; ProtectSystem=strict + ReadOnlyPaths делали /root/awg и /etc/amnezia read-only). Решение — сервис от root без sudo и строгой песочницы (только PrivateTmp); manage/helper вызываются напрямую; sudoers оставлен как legacy-conffile; из Depends убран sudo; key.pem снова 600 root:root.

## Журнал изменений
- 2026-10-13: Инициализация памяти. Проверка доступов: `read` OK, `write` OK (` .access_test.tmp` создан и удалён), `icacls` — полные права. Каталог пуст.
- 2026-10-13: MVP awg-panel: src/awg_panel/{server,manage,system_info,auth,config,validate}, bin/{helper,set-password}, packaging/{DEBIAN,service,sudoers}, build_deb.sh, workflow, README. Проверки: py_compile OK, unittest 6/6 OK, smoke рендера OK (layout/server/table), bash -n helper/postinst/build OK. disk_usage починен для Windows-dev (statvfs guard).
- 2026-10-13: По фидбэку: host по дефолту 0.0.0.0:8443 (без изменений), массовый regen убран из списка клиентов (только в карточке), журнал = файл + последние 10 на Статусе. Перепроверено: py_compile + unittest 6/6 OK.
- 2026-10-13: Локальный git: init, коммит MVP (674ddbb), коммит чистки pycache+.gitignore (6bdf404). Дерево чистое.
- 2026-10-13: Ревью + правки: критично — service NoNewPrivileges=no/ProtectHome=read-only+ReadOnlyPaths+Restart (packaging/awg-panel.service), sudoers helper по командам + Defaults env_reset (packaging/sudoers); безопасность — пароль только через stdin (bin/awg-panel-set-password-internal + postinst printf|internal + unset), Cache-Control: no-store (server._send/_send_auth), HTMX SRI sha384 (server.HTMX), logout только POST+confirm (server do_GET/do_POST/_layout), helper хардкод путей + $# guard, stderr helper больше не течёт в браузер; среднее — refresh cookie (_send_auth), лимит форм 1МБ/413, sel invalid→ошибка, regen→/client?name=, параллельные manage (ThreadPool), mem_info guard, config clamp host/ttl/paths, manage единый парсер, log errors в stderr, run() понятные ошибки TLS, build без pycache + ship config.ini + проверка VER. Проверки: py_compile OK, unittest 12/12 OK, smoke layout/SRI OK. Коммит a1f0f4e.
- 2026-10-13: Сборка 0.1.1: bump __init__.py/README до 0.1.1 (955e7a7), +x на скриптах для CI (425b837), portable sudoers для sudo-rs — `--yes *` одной строкой, без requiretty (d8406ee). Чистая сборка в WSL: .deb OK (17572 байт, sha256 1227ed54…), visudo parsed OK, unittest 12/12 OK. Локальный .deb — в dist/ (gitignored).
- 2026-10-13: Push в GitHub: master 460ca10..9fa34f8 (6 коммитов) + тег v0.1.1 → запущен workflow build-deb.yml (CI соберёт .deb и приложит к Release). PAT использован разово, helper отключён, история очищена.
- 2026-10-13: CI-фикс 403: workflow build-deb.yml получил `permissions: contents: write` (a04d570) — без этого softprops/action-gh-release падает «Resource not accessible by integration». Тег v0.1.1 переставлен на a04d570 (релиза ещё не было) и запушен заново для перезапуска сборки.
- 2026-10-13: Фикс замечаний с VPS (0.1.2): (1) postinst теперь печатает RU-инструкцию «что дальше» — пароль /root/.awg-panel-initial-password, смена через awg-panel-set-password, конфиг /etc/awg-panel/config.ini + restart, URL https://IP:PORT/ с реальным портом из конфига, status/journalctl (packaging/DEBIAN/postinst); то же в README. (2a) _apt-предупреждение про песочницу — безвредно (файл в $HOME недоступен _apt), в README рекомендованы `dpkg -i` / копия в /tmp. (2b) КРИТ: .deb 0.1.1 собран не под root и привёз sudoers с uid 1001 → ломает ВЕСЬ sudo: build_deb.sh теперь `chown -R 0:0` + `dpkg-deb --root-owner-group --build` (fallback на plain), postinst сам чинит `chown root:root`+440 перед visudo при каждом upgrade/reinstall. Версия 0.1.2 (src/__init__.py). Регресс-тесты TestPackaging 3 шт (всего 15/15 OK), bash -n postinst/build OK. Файлы: build_deb.sh, packaging/DEBIAN/postinst, README.md, src/__init__.py, tests/test_panel.py.
- 2026-10-13: Push 0.1.4: master 912d23b..c89ee38 (3 коммита) + тег v0.1.4 → CI build-deb.yml собирает .deb и Release; remote без токена, дерево в sync. Локальная сборка в WSL: .deb OK (18538 байт, sha256 88d8d4ed…, Version 0.1.4, Depends без sudo, все файлы root/root, sudoers 440 parsed OK, service User=root, config с webusername/webpassword, без internal-setter), unittest 23/23 OK и в WSL. PAT из чата использован разово в URL пуша, в remote не сохранён — отозвать/перевыпустить. Следующий шаг: проверка на VPS (upgrade поверх 0.1.3, статус AWG/клиенты без rc=1).
- 2026-10-13: КРИТ e2e 0.1.2 (restart-loop): journal `TLS load failed (...cert.pem, ...key.pem): Permission denied`, рестарты 152→161. Причина — postinst делал `chmod 600 key.pem` при `chown root:awgpanel`, сервис `User=awgpanel` прочитать ключ не мог (server.py run→load_cert_chain→SystemExit 1). Фикс 0.1.3: postinst `chmod 640 key.pem` + `chown root:awgpanel`+chmod вне `if` (self-heal существующих установок при upgrade), cert 644. Регресс-тест TestPackaging.test_postinst_tls_key_group_readable (всего 16/16 OK), bash -n OK. Файлы: packaging/DEBIAN/postinst, tests/test_panel.py, src/__init__.py (0.1.3), MEMORY.md.
- 2026-10-13: 0.1.5 клиентская страница: (1) убран page-level h-scroll — body/main overflow-x:hidden, .card min/max-width, .grid>* min-width:0, pre max-width:100%+overflow:auto, img max-width:100% (длинные строки конфига скроллятся внутри pre); (2) блоки сверху вниз отдельными card в .stack: Пир / Конфиг / vpn:// / QR (кнопки Пира: Пересоздать, Скачать .conf, QR.png); (3) кнопка QR.png — target=_blank rel=noopener на /client-qr. Тесты TestClientPage 3 шт (порядок блоков, кнопки+_blank+4 card, CSS-правила), всего 26/26 OK. Файлы: src/awg_panel/server.py, src/awg_panel/__init__.py (0.1.5), tests/test_panel.py.
