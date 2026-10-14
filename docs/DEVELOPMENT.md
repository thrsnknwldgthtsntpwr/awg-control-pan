# Разработка (Development)

## Быстрый цикл

```bash
git clone https://github.com/thrsnknwldgthtsntpwr/awg-control-pan.git
cd awg-control-pan

# тесты — только stdlib, pip/venv не нужен
python3 -m unittest discover -s tests -v
# ожидаемо: 61/61 OK (на 0.1.17)
```

Полный e2e — только на VPS с установленным инсталлером (нужны
`/root/awg/manage_amneziawg.sh` и `/etc/amnezia/.../awg0.conf`).
На dev-машине `manage`-пути отсутствуют — это нормально, их покрывают моки в тестах.

## Проверки перед коммитом

```bash
python3 -m py_compile src/awg_panel/*.py bin/awg-panel-set-password
python3 -m unittest discover -s tests -v
bash -n bin/awg-panel-helper packaging/DEBIAN/postinst build_deb.sh
```

Те же проверки гоняет CI ([ci.yml](../.github/workflows/ci.yml)) на каждый push/PR.

## Кодстайл (коротко)

- Python: stdlib only, без внешних зависимостей. Импорты сверху, типы — по вкусу, но без `Any`-каши.
- HTML собирается в `server.py` f-строками + `html.escape` через `e()`. Инлайн-`<script>` запрещён (CSP `script-src 'self'`) — JS только в `COPY_JS` → `/static/copy.js` и `CLIENTS_JS` → `/static/clients.js`.
- CSS — в `STYLE_CSS` (`server.py`). Кнопки `<button>` и `<a class=btn>` должны выглядеть одинаково (`font:inherit`).
- Bash (`helper`, `postinst`, `build_deb.sh`): `set -euo pipefail`, `PATH` зажат, без `eval`, LF-окончания обязательны (следит `.gitattributes`).
- Имена клиентов: `^[A-Za-z0-9_-]{1,63}$` (`validate.py`). Новую валидацию — туда же + тесты.
- Ошибки `manage/helper` в UI — обобщённые, детали — в `stderr`. Не теките `stderr`/`PSK`/`PrivateKey` в браузер.

## Структура тестов

Все тесты — `tests/test_panel.py` (unittest):

| Класс | Что покрывает |
|-------|---------------|
| `TestValidate` | имена, `parse_names`, `expires_flag` (только дни, `1..3650`) |
| `TestAuth` | verify (мульти), сессии (+username), rate-limit настраиваемый, GC |
| `TestConfig` | clamp портов/TTL/лимитов, обязательная секция `[users]` (отказ без неё), парсинг и валидация `[users]` (пары, лимит 254, отказ) |
| `TestManage` | JSON-парсер, порядок `--expires` между `--yes` и `add`, прямой вызов без sudo от root |
| `TestSystemInfo` | устойчивость к битому `/proc` |
| `TestPackaging` | root-owned `.deb`, `postinst` (права, next-steps без legacy), `service User=root`, `control` без sudo |
| `TestClientPage` | порядок блоков Пир/Конфиг/vpn/QR, кнопки, copy.js-роут, CSS без page-h-scroll |
| `TestLoginPage` | вход без меню, ссылка версии на GitHub |
| `TestClientsListPage` | «Удалить выбранные» disabled без выбора, «Добавить»/«Удалить» в одном ряду, «Сгенерировать имя» + data-атрибуты, clients.js-роут |
| `TestClientNames` | дефолты/кастом `[client_names]`, clamp `rand_bytes`, fallback плохого префикса, лимит длины 63 |
| `TestHttpRedirect` | `http://:80 → 301 https://:port` (URL, Host-валидация, live-редирект без кук) |

Новый фикс = новый регресс-тест. Правило простое: «упало на VPS → тест, потом фикс».

## Сборка .deb

```bash
./build_deb.sh 0.1.17
# → dist/awg-panel_0.1.17_all.deb (dist/ — в .gitignore)
```

Что делает скрипт:

1. Раскладывает `src/`, `bin/`, `packaging/` в `dist/awg-panel_<VER>_all/`.
2. Чистит `__pycache__`/`*.pyc` (протухший байткод под `/usr` затенял бы фиксы при upgrade).
3. Кладёт `control` с подставленной версией, `conffiles`, `postinst/prerm/postrm` (`755`), `service`, дефолтный `config.ini`.
4. Делает `chown -R 0:0` + `dpkg-deb --root-owner-group` (иначе повторение бага `0.1.1` с `uid 1001` в файлах пакета).

На Windows сборка — в WSL. Если репозиторий на `/mnt/d` с правами `777`, собирайте через `/tmp` (иначе `dpkg-deb` ругается на права staging-каталога).

## Релизный цикл

```bash
# 1. Поднять версию
# src/awg_panel/__init__.py (__version__), README-бейдж, CHANGELOG.md

# 2. Коммит + тег + push
git commit -am "release 0.1.X: ..."
git tag v0.1.X
git push origin master --tags
# CI build-deb.yml: lint → unittest → build → Release с .deb
```

Старые нерабочие релизы до `0.1.8` удалены с GitHub; теги оставлены. Новые релизы — только по тегу `v*`.

## LF-правило (важно)

`.gitattributes` держит LF для `*.sh`, `bin/*`, `packaging/*`, `*.py`, `*.md`, `*.yml`.
CRLF ломает `#!/bin/bash` (`postinst/helper/build`) на сервере. Редактор — с `LF`, без BOM.
