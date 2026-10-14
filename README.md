# awg-panel — веб-интерфейс для AmneziaWG

[![build-deb](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/actions/workflows/build-deb.yml/badge.svg)](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/actions/workflows/build-deb.yml)
[![ci](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/actions/workflows/ci.yml/badge.svg)](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-debian%20%7C%20ubuntu-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-0.1.17-blue)

Минималистичная веб-панель в стиле роутера поверх
[bivlked/amneziawg-installer](https://github.com/bivlked/amneziawg-installer).
Без своей базы VPN-пользователей: живой статус читается из `manage_amneziawg.sh --json`
и `/proc`, клиенты создаются/удаляются тем же `manage`-скриптом.

> Язык интерфейса: русский. Язык документов репозитория: русский.

---

## Содержание

- [Возможности](#возможности)
- [Как это выглядит](#как-это-выглядит)
- [Быстрый старт](#быстрый-старт)
- [Требования](#требования)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Использование](#использование)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Безопасность](#безопасность)
- [Разработка](#разработка)
- [Диагностика](#диагностика)
- [FAQ](#faq)
- [Changelog и релизы](#changelog-и-релизы)
- [Участие в разработке](#участие-в-разработке)
- [Лицензия](#лицензия)
- [Благодарности](#благодарности)

---

## Возможности

| Раздел | Что умеет |
|--------|-----------|
| **Статус → Сервер** | Uptime, load average, CPU, RAM, диск `/`, счётчики интерфейсов из `/proc`. Без вызова `manage`. |
| **Статус → AWG** | `manage check --json` + маркеры `AWG_PROTOCOL` / `SCRIPT_VERSION`: юнит, интерфейс `awg0`, порт, модуль, число пиров, UFW (только чтение). |
| **Клиенты** | Таблица как `manage list --verbose`: имя, IP, префикс ключа, статус, RX/TX (`stats --json`), срок. Чекбоксы, массовое удаление (кнопка неактивна без выбора), добавление нескольких имён разом, генератор имён (`[client_names]`). Кнопки «Добавить» и «Удалить выбранные» в одном ряду. |
| **Карточка клиента** | Блоки сверху вниз: **Пир → Конфиг → vpn:// → QR**. Кнопки: Пересоздать, Скачать `.conf`, `QR.png` (в новой вкладке), Скопировать для Конфига и `vpn://`. |
| **Сроки** | При добавлении — только днями (`1..3650`, пусто = бессрочно). Чистку истёкших делает крон инсталлера. |
| **Авторизация** | До 254 пользователей, логин/пароль только из `config.ini` (`[users]` `user.N/password.N`, секция обязательна). Сессии в памяти (sliding TTL + абсолютный лимит 12 ч, в сессии хранится имя), журнал входов в файл. Блок входа — средствами сервиса (`auth_max_attempts/auth_lock_minutes`, без `iptables`). Без 2FA/API — осознанно, см. [SECURITY.md](SECURITY.md). |
| **HTTP→HTTPS** | `http://<IP>/` отвечает только `301 → https://<IP>:<port>/` (`http_redirect_port`, дефолт `80`, `0` — выкл). Контент по HTTP не отдаётся. |
| **Стек** | Только Python 3 stdlib (`http.server` + встроенный HTTPS). SSR: добавление работает без JS. JS только same-origin: `/static/copy.js` (кнопки «Скопировать») и `/static/clients.js` (активация «Удалить выбранные» по чекбоксам + генератор имён). Без nginx, без CDN. |

Что панель **не делает** (и не будет без обсуждения в Issues):

- не хранит VPN-пользователей в своей БД;
- не трогает UFW/iptables;
- не трогает `/root/awg` и `/etc/amnezia` при установке — только свои файлы;
- не показывает `awg show dump` целиком (там PSK) и никогда не отдаёт серверный `PrivateKey` в браузер.

---

## Как это выглядит

Навигация слева: **Статус / Клиенты / Выход** (на экране входа меню скрыто). Справа — контент.

- `/status?tab=server` — две карточки: «Система» и «Интерфейсы» + последние 10 строк журнала входов.
- `/status?tab=awg` — одна карточка «AWG» с таблицей из 8 строк (юнит, интерфейс, порт, модуль, пиры, UFW, поколение, версия установщика).
- `/clients` — форма добавления (`имена через пробел/запятую` + `дней` + «Сгенерировать имя»), ряд «Добавить» / «Удалить выбранные» (удаление неактивно без выбора), таблица. Имя — ссылка в карточку.
- `/client?name=alice` — карточка клиента (Пир / Конфиг / `vpn://` / QR).

Скриншоты пока не приложены — панель ставится за 2 минуты на тестовый VPS, см. [Быстрый старт](#быстрый-старт).

---

## Быстрый старт

На сервере, где уже стоит `amneziawg-installer`:

```bash
# 1. Скачать .deb из Releases (например v0.1.17)
wget https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/releases/download/v0.1.17/awg-panel_0.1.17_all.deb

# 2. Установить (именно dpkg — без предупреждения _apt о песочнице)
sudo dpkg -i awg-panel_0.1.17_all.deb

# 3. Сменить пароль и открыть панель
sudo awg-panel-set-password
sudo systemctl restart awg-panel
# открыть https://<IP-сервера>:8443/ (self-signed — подтвердить исключение)
# или http://<IP-сервера>/ — редирект 301 на https (нужен открытый 80/tcp)
```

Проверка:

```bash
sudo systemctl status awg-panel --no-pager
sudo journalctl -u awg-panel -n 30 --no-pager
```

Подробно со всеми вариантами — [docs/INSTALL.md](docs/INSTALL.md).

---

## Требования

- **ОС:** Debian 11+ / Ubuntu 22.04+ (systemd).
- **Установленный и настроенный** `amneziawg-installer`:
  - `/root/awg/manage_amneziawg.sh` (исполняемый),
  - `/etc/amnezia/amneziawg/awg0.conf`,
  - `/root/awg/awgsetup_cfg.init` (маркеры `AWG_PROTOCOL`, `SCRIPT_VERSION`).
- **Зависимости .deb:** `python3`, `openssl`, `systemd`. Опционально `qrencode` (QR инсталлер генерит сам, панель только отдаёт `.png`).
- **Порты:** `8443/tcp` (HTTPS) + `80/tcp` (редирект на HTTPS; выключается `http_redirect_port = 0`).
- **Для сборки .deb:** `dpkg-deb`. Для dev-проверок: `python3` (тесты — только stdlib, без pip).

---

## Установка

```bash
sudo dpkg -i awg-panel_*_all.deb
```

- `postinst` **не трогает** `/root/awg` и `/etc/amnezia` — только `/etc/awg-panel/`, `/var/log/awg-panel/`, ключи/сертификат, systemd-юнит.
- После установки `postinst` печатает памятку «что дальше» (пароль → URL → проверки).
- Про безвредное предупреждение `N: Загрузка выполняется от лица суперпользователя...` и про восстановление `sudo` после битого `0.1.1` — см. [docs/INSTALL.md](docs/INSTALL.md) и [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Обновление — тем же `dpkg -i` новым `.deb` поверх. Конфиг `/etc/awg-panel/config.ini` сохраняется (conffile); остальное подхватывается дефолтами в коде.

Удаление:

```bash
sudo apt remove awg-panel       # конфиг, ключи и логи остаются
sudo apt purge awg-panel        # удалить всё: конфиг, ключи, логи (VPN-клиенты инсталлера не трогает)
```

---

## Конфигурация

Единственный конфиг: `/etc/awg-panel/config.ini` (`600`, `root:root`). Полный справочник — [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

| Ключ | Дефолт | Что значит |
|-------------------|--------|------------|
| `host` | `0.0.0.0` | На каком адресе слушать (и HTTPS, и HTTP-редирект). |
| `port` | `8443` | Порт HTTPS. `1..65535`. |
| `http_redirect_port` | `80` | `http://:80 → https://:port` (`301`, только редирект). `0` = выкл. |
| `cert` / `key` | `/etc/awg-panel/cert.pem` / `key.pem` | Self-signed создаёт `postinst` (`key.pem` — `600`). |
| `[users]` `user.N` / `password.N` | — | До 254 пользователей (`N=1..254`), секция обязательна. Ошибки — отказ старта. |
| `auth_max_attempts` / `auth_lock_minutes` | `5` / `5` | Блок IP средствами сервиса (`1..100` / `1..1440`), без `iptables/ufw`. |
| `session_ttl_min` | `30` | Sliding TTL сессии, `1..1440`. Абсолютный лимит — 12 ч (в коде). |
| `manage_script` | `/root/awg/manage_amneziawg.sh` | Путь к underlay-скрипту. |
| `server_conf` | `/etc/amnezia/amneziawg/awg0.conf` | Только для чтения префиксов публичных ключей. |
| `helper` | `/usr/sbin/awg-panel-helper` | Безопасные чтения live-файлов. |
| `auth_log` | `/var/log/awg-panel/auth.log` | Журнал входов (`600`, без переводов строк в полях). |

Смена пароля:

```bash
sudo awg-panel-set-password          # интерактивно, атомарная запись 0600
sudo systemctl restart awg-panel     # применить
```

Пример — [packaging/config.ini.example](packaging/config.ini.example).

---

## Использование

### Статус

- **Сервер** — моментальный срез `/proc`: uptime, load, CPU%, RAM used/total, диск `/`, таблица интерфейсов (RX/TX — счётчики с загрузки, не скорость).
- **AWG** — `manage check --json` + `helper init-info`. Если `manage` упал — страница честно пишет `rc=...`, детали только в `journalctl` (не в браузер).

### Клиенты

- Добавление: `имена через пробел/запятую`, имя — `^[A-Za-z0-9_-]{1,63}$`, срок — `дней (пусто=∞)`, max 100 имён за раз. Кнопка «Сгенерировать имя» подставляет `prefix` + случайный hex из `[client_names]` (дефолт `user_` + 16 символов, аналог `openssl rand -hex 8`); повторные нажатия дописывают имена через пробел.
- Удаление: чекбоксы + «Удалить выбранные» (тоже max 100); кнопка неактивна, пока ничего не выбрано. «Добавить» и «Удалить выбранные» — в одном ряду.
- Пересоздание ключей («Пересоздать») — только из карточки клиента, по одному. Эндпоинт технически принимает батч, UI батч-regen не предлагает (защита от случайного слома всех конфигов разом).

### Карточка клиента

```
/client?name=alice
```

1. **Пир** — IP (+IPv6), статус, срок, RX/TX, handshake + ряд кнопок: Пересоздать | Скачать .conf | QR.png.
2. **Конфиг** — `client-conf` + «Скопировать».
3. **vpn://** — `client-uri` + «Скопировать» (если есть `.vpnuri`).
4. **QR** — `<img src=/client-qr>` 260px + ссылка «открыть в новой вкладке».

Скачивание:

```
/download?name=alice&type=conf      # *.conf
/client-qr?name=alice               # *.png (image/png)
```

---

## Архитектура

```text
                    HTTPS :8443 (self-signed) + HTTP :80 -> 301 https
  ┌──────────┐   ─────────────────────────▶   ┌─────────────────────┐
  │ Браузер  │   SSR-формы + 1 same-origin    │  awg-panel (root)   │
  │ (users)  │   JS (/static/copy.js)         │  stdlib http.server │
  └──────────┘   ◀─────────────────────────   └─────────┬───────────┘
                                                       │ argv, без shell
                                        ┌──────────────┼──────────────┐
                                        ▼              ▼              ▼
                                 manage --json   helper reads     /proc
                                 add/del/regen   conf/uri/png     cpu/mem/
                                 list/stats/     pubkeys only     net/dev
                                 check           init-info
                                        │              │              │
                                        ▼              ▼              ▼
                                   /root/awg/*   awg0.conf (RO)   kernel
                                 (инсталлер — источник правды, своей БД нет)
```

Принципы:

- **Underlay-контракт:** `list / stats / check / add / remove / regen` через `manage --json`. Панель не парсит `wg show` сама.
- **Helper с allowlist:** `client-conf | client-uri | client-qr <name> | server-pubkeys | init-info`. Пути захардкожены, symlink отклоняются, `PATH` зажат, серверный `PrivateKey` не отдаётся никогда.
- **Параллелизм с таймаутом:** `list + stats + helper` идут через `ThreadPoolExecutor` с общим `FUT_TIMEOUT=40с`.
- **Fail-closed:** нет файла, битый файл, нет `[users]` или любая ошибка `[users]` — отказ старта (с логом в stderr сервиса); ошибки `manage` в UI обобщены, детали — в stderr сервиса.

---

## Структура проекта

```text
awg-control-pan/
├── src/awg_panel/
│   ├── __init__.py      # версия (__version__)
│   ├── __main__.py      # точка входа (python3 -m awg_panel)
│   ├── server.py        # роуты, сессии, HTML, HTTP→HTTPS редиректор, /static/style.css + /static/copy.js
│   ├── manage.py        # обёртка manage --json (без shell, капы stdout/батча)
│   ├── system_info.py   # /proc: cpu/mem/disk/uptime/load/net
│   ├── auth.py          # пользователи [users], сессии в памяти, rate-limit, журнал
│   ├── config.py        # load_config() с clamp и fail-closed для [users]
│   └── validate.py      # имена, expires, parse_names
├── bin/
│   ├── awg-panel-helper        # безопасные чтения live-файлов (bash, allowlist)
│   └── awg-panel-set-password # смена user.1/password.1 в [users] (атомарно, 0600)
├── packaging/
│   ├── DEBIAN/control, conffiles, postinst, prerm, postrm
│   ├── awg-panel.service        # systemd-юнит (User=root, см. SECURITY.md почему)
│   ├── config.ini.example
│   └── sudoers                  # для non-root/dev вызовов (в проде сервис от root, sudo не используется)
├── tests/test_panel.py  # unittest, только stdlib (61 тест на 0.1.17)
├── build_deb.sh         # сборка .deb (root-owned, без pycache)
├── docs/                # INSTALL, CONFIGURATION, TROUBLESHOOTING, DEVELOPMENT (SECURITY.md — в корне)
├── .github/workflows/
│   ├── build-deb.yml    # сборка .deb + Release по тегу v*
│   └── ci.yml           # py_compile + unittest + bash -n + visudo на push/PR
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE (MIT)
```

---

## Безопасность

Честная сводка (полная — [SECURITY.md](SECURITY.md)):

- Приватный ключ сервера **никогда** не отдаётся в браузер; `awg show dump` целиком не показываем (там PSK); приватные ключи клиентов видят пользователи панели — как root через `manage`.
- Все POST с CSRF (constant-time), редиректы `303`, кука `Secure; HttpOnly; SameSite=Lax`, rate-limit логина (`auth_max_attempts/auth_lock_minutes`, дефолт `5/5мин`) по socket-IP средствами сервиса без `iptables` (`X-Forwarded-For` игнорируется).
- Заголовки: `nosniff / DENY / no-referrer / CSP default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' / HSTS / Permissions-Policy`.
- Лимиты: тело форм 1 МиБ (`413` + разрыв keep-alive), max 2000 полей, max 100 имён в батче, stdout manage 1 МиБ, helper 2 МиБ, socket timeout 10 с.
- Вызовы `manage`/`helper` — списком аргументов без shell; имена `^[A-Za-z0-9_-]{1,63}$`; `expires` — строго `--expires=\d+d`, `1..3650`.
- Пароль в `config.ini` в открытом виде (`600`, `root-only`, атомарная запись `mkstemp+replace`, `umask 077`); `key.pem` создаётся под `umask 077`.
- Сервис работает от **root без sudo** — осознанно: `User=awgpanel + sudo` ломался о песочницу systemd (`unable to change to root gid`, `sudoers_audit`) и давал `rc=1` в UI. Детали и разбор — в [SECURITY.md](SECURITY.md#почему-сервис-работает-от-root).

Нашли уязвимость? Не открывайте Issue — см. [SECURITY.md](SECURITY.md#сообщить-об-уязвимости).

---

## Разработка

```bash
# тесты (только stdlib, без pip/venv)
python3 -m unittest discover -s tests -v

# 61/61 OK на 0.1.17. Полный e2e — только на VPS с инсталлером
# (нужны /root/awg/manage_amneziawg.sh и /etc/amnezia/.../awg0.conf)
```

```bash
# локальная сборка .deb (нужен dpkg-deb; на Windows — в WSL)
./build_deb.sh 0.1.17
# → dist/awg-panel_0.1.17_all.deb
```

Детали кодстайла, тестов, релизного цикла — [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) и [CONTRIBUTING.md](CONTRIBUTING.md).

Релиз: коммит → `git tag vX.Y.Z` → `git push --tags` → CI `build-deb.yml` собирает `.deb` и прикладывает к GitHub Release.

---

## Диагностика

```bash
sudo systemctl status awg-panel --no-pager
sudo journalctl -u awg-panel -n 50 --no-pager
cat /var/log/awg-panel/auth.log
```

Частые случаи — [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md):

| Симптом | Куда смотреть |
|---------|---------------|
| `manage check failed (rc=1)` / `list failed` | `journalctl -u awg-panel`, права `/root/awg/manage_amneziawg.sh`, запущен ли `awg0` |
| `TLS load failed ... Permission denied` (старые версии) | Починено в `0.1.4` (сервис от root, `key.pem 600 root:root` + self-heal). Обновитесь. |
| `sudo ... is owned by uid 1001` (после `0.1.1`) | [TROUBLESHOOTING: sudo сломан](docs/TROUBLESHOOTING.md#sudo-сломан-после-011-is-owned-by-uid-1001) |
| `N: ... недоступен для пользователя _apt` | Безвредно. Ставьте через `dpkg -i`, см. [INSTALL](docs/INSTALL.md#6-про-предупреждение-_apt). |

---

## FAQ

**Это форк инсталлера?**
Нет. Это отдельная панель поверх `bivlked/amneziawg-installer`. Инсталлер — источник правды, панель — тонкий UI.

**Где хранятся клиенты?**
Там же, где их хранит инсталлер (`/root/awg/*.conf`, `awg0.conf`). Своей БД у панели нет — снесли панель, клиенты остались.

**Можно ли открыть панель в интернет?**
Технически да (HTTPS + rate-limit + CSP/HSTS), но пароль из примера (`admin/admin` в `config.ini.example`) смените **до** открытия. Идеально — ограничить по IP на фаерволе и держать панель за VPN Jump-хостом. См. [SECURITY.md](SECURITY.md).

**Зачем сервис от root, это не опасно?**
`manage` сам требует root (wg/iptables/конфиги). Прослойка `awgpanel+sudo` не добавляла безопасности, но ломалась о systemd-песочницу. Компромисс зафиксирован: минимальный юнит (`PrivateTmp` only), вызовы без shell, allowlist helper, капы и таймауты. Разбор — [SECURITY.md](SECURITY.md#почему-сервис-работает-от-root).

**Будут ли 2FA / API / WireGuard-manager?**
Пока нет. Пользователи панели задаются в `[users]` (до 254, секция обязательна). Хотите 2FA/API — откройте Issue с use-case.

---

## Changelog и релизы

- Кратко: [CHANGELOG.md](CHANGELOG.md).
- Файлы: [GitHub Releases](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/releases) (`.deb` прикладывает CI по тегу `v*`).
- Старые неработоспособные релизы до `0.1.8` удалены; git-теги `v0.1.1–v0.1.17` оставлены (при нужде `.deb` пересоберёт CI).

---

## Участие в разработке

PR приветствуются. Прочитайте [CONTRIBUTING.md](CONTRIBUTING.md): CRLF запрещён (`.gitattributes` держит LF для `postinst/helper/*.py`), тесты обязательны (`61/61`), коммиты — короткие imperative на английском или русском.

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

---

## Благодарности

- [bivlked/amneziawg-installer](https://github.com/bivlked/amneziawg-installer) — underlay (`manage_amneziawg.sh`), без которого панели не было бы.
- `qrencode`, `systemd`, `openssl` — за то, что просто работают.
