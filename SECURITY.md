# Политика безопасности

## Поддерживаемые версии

| Версия | Поддержка |
|--------|-----------|
| 0.1.15 (latest) | ✅ |
| 0.1.8–0.1.14 | ✅ (только критические фиксы) |
| ≤ 0.1.7 | ❌ (обновитесь; релизы удалены, теги оставлены) |

Актуальный changelog — [CHANGELOG.md](CHANGELOG.md), файлы — [Releases](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/releases).

## Сообщить об уязвимости

**Не открывайте публичный Issue** для уязвимостей.

Напишите мейнтейнеру через [private vulnerability reporting](https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/security/advisories/new)
или в личные сообщения. Приложите:

- версию (`dpkg -l | grep awg-panel`, `__version__`);
- шаги воспроизведения;
- вывод `journalctl -u awg-panel` (секреты затрите).

Мы постараемся ответить в течение 72 часов и выпустить фикс + регресс-тест.

## Модель угроз (честно)

Панель — административный UI для личного сервера. Модель простая:

- **Доверенные:** root сервера, код инсталлера (`manage_amneziawg.sh`), kernel/`/proc`.
- **Недоверенные:** всё из браузера (формы, куки, имена клиентов, `Content-Length`).
- **Актив:** панель слушает HTTPS напрямую (self-signed), rate-limit — по socket-IP, `X-Forwarded-For` игнорируется.

Панель осознанно **не** защищает от:

- злоумышленника с root-доступом к серверу (он и так видит всё через `manage`);
- подбора пароля из примера (`admin/admin` в `config.ini.example`) в открытом интернете — смените пароль **до** открытия порта;
- атак на сам инсталлер/`manage`-скрипт — панель лишь вызывает его с валидированными аргументами.

## Что реализовано

### Аутентификация и сессии

- До 254 пользователей, credentials только из `/etc/awg-panel/config.ini` (`[users]` `user.N/password.N`, `600 root:root`). Нет секции или ошибка в `[users]` — отказ старта (fail-closed).
- Сравнение — constant-time по всем записям без раннего выхода, без падений на non-ASCII.
- Сессии в памяти: случайные `sid`/`csrf` (`secrets.token_urlsafe(32)`), sliding TTL (`session_ttl_min`, дефолт 30 мин) + абсолютный лимит 12 ч, cap 1000 сессий (evict oldest, не `clear()`). В сессии хранится имя пользователя.
- Кука: `Secure; HttpOnly; SameSite=Lax; Max-Age=TTL`, перевыпускается при каждом authed-запросе (sliding).
- Rate-limit логина средствами сервиса (без `iptables/ufw/nftables`): `auth_max_attempts` неверных → блок IP на `auth_lock_minutes` (`429`, дефолт `5/5мин`), GC с cap 10000 IP (evict oldest, чтобы флуд случайными IP не разблокировал атакующего).
- Журнал входов: `/var/log/awg-panel/auth.log` (`0600`, `O_APPEND`, поля без `\r\n`, обрезка длин).
- Logout — только `POST` с CSRF (`GET /logout` — лишь подтверждение, сессию не убивает).

### CSRF / заголовки / лимиты

- Все POST с CSRF-токеном из сессии; редиректы после POST — `303`.
- Заголовки на всех ответах: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `CSP: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'`, `HSTS max-age=31536000`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `Cache-Control: no-store` (кроме статики с `max-age=3600`).
- Лимиты: тело форм 1 МиБ (превышение → `413` + разрыв keep-alive против desync), max 2000 полей, max 100 имён в батче, stdout `manage` 1 МиБ, helper-ответы 2 МиБ, socket timeout 10 с, ожидание `manage`-фьючерсов `40 с`, `405` на `HEAD/PUT/DELETE/PATCH/OPTIONS`.
- Инлайн-`<script>` запрещён CSP — весь JS в same-origin `/static/copy.js` (без CDN/HTMX с 0.1.8).

### Вызовы manage / helper

- Только списком аргументов, без shell. Имена клиентов: `^[A-Za-z0-9_-]{1,63}$` (валидация и в Python, и в helper).
- `expires` собирается только внутри (`^--expires=\d+d$`, `1..3650`) — порядок `--yes --expires=Nd add` зафиксирован тестом под sudoers.
- Helper — allowlist из 5 команд (`client-conf | client-uri | client-qr <name> | server-pubkeys | init-info`), пути захардкожены (`/root/awg`, `awg0.conf`), env игнорируется, symlink отклоняются, `PATH` зажат.
- Серверный `PrivateKey` не отдаётся никогда (helper публикует только `#_Name` / `PublicKey`); `awg show dump` целиком не показываем (там PSK); приватные ключи клиентов видит админ — как root через `manage`.
- Ошибки `manage/helper` в UI обобщены (`rc=...`), детали — только в stderr сервиса (`journalctl`).

### Файлы и секреты

- Пароли в `config.ini` в открытом виде (`600 root:root`, атомарная запись `mkstemp+replace`, `umask 077`); `%` разрешён (`interpolation=None`); пробелы в пароле значимы; битый ini → дефолты, а не падение (кроме ошибок `[users]` и дублей опций — там отказ старта).
- `key.pem` создаётся под `umask 077` (без окна `644`), сразу `600 root:root`; `cert.pem` — `644`.
- `.deb` собирается `root-owned` (`chown -R 0:0` + `--root-owner-group`) — иначе повторение бага `0.1.1` (sudoers с `uid 1001` ломал весь sudo).

## Почему сервис работает от root

`manage` сам требует root (wg/iptables/конфиги). Попытка `User=awgpanel + sudo` давала:

- `sudo: unable to change to root gid: Operation not permitted`,
- `sudo: error initializing audit plugin sudoers_audit`,
- в UI: `manage check failed (rc=1)` / `list failed (rc=1)`.

Причина — песочница systemd (`CapabilityBoundingSet=` резал setuid, `ProtectSystem=strict + ReadOnlyPaths` делали `/root/awg` read-only). Прослойка не добавляла безопасности, но ломала всё. Поэтому юнит минимальный (`PrivateTmp` only, `User=root`), вызовы прямые, `sudoers` оставлен для чистых upgrade. Компромисс покрыт регресс-тестами (`TestPackaging`, `TestManage`).

## Рекомендации оператору

1. Смените пароль из примера **до** открытия порта: `sudo awg-panel-set-password && sudo systemctl restart awg-panel`.
2. Не открывайте панель в интернет без нужды; идеально — `host = 127.0.0.1` + SSH-туннель или ограничение по IP на фаерволе.
3. Держите сервер обновлённым (`apt update && apt upgrade`), бэкапьте `/etc/awg-panel/config.ini` (там пароль) и `/root/awg`.
4. Следите за `auth.log` (брутфорс виден как `FAIL`) и `journalctl -u awg-panel`.
