# awg-panel — веб-интерфейс поверх amneziawg-installer

Версия: **0.1.9**.

Минималистичная вебка в стиле роутера. Underlay — только команды
`manage_amneziawg.sh` из https://github.com/bivlked/amneziawg-installer
плюс `/proc` для состояния сервера. Своей БД пользователей VPN нет.

## Что умеет (фаза 1, по вашим ответам)

- Слева: **Статус / Клиенты / Выход**. Справа — контент.
- Статус: вкладки **Сервер** (CPU/RAM/disk/uptime/load/интерфейсы из `/proc`)
  и **AWG** (`manage check --json` + маркеры `AWG_PROTOCOL`/`SCRIPT_VERSION`).
- Клиенты: таблица из `manage list --json` + `stats --json` + префиксы ключей
  из `awg0.conf` (колонки как `list --verbose`: имя/IP/ключ/статус/RX-TX/срок).
  Чекбоксы, массовое удаление, кнопки **Добавить / Удалить**.
  Regen («Пересоздать») — кнопка внутри карточки клиента
  (эндпоинт держит и множественный выбор, UI множественный regen не предлагает).
  Имя — ссылка в карточку: блоки Пир / Конфиг / `vpn://` / QR сверху вниз,
  кнопки «Скопировать» у Конфига и `vpn://`, QR открывается в новой вкладке.
- Срок при добавлении — только днями (пусто = бессрочно, max 3650), удаление истекших — крон инсталлера.
- Auth: логин/пароль из `/etc/awg-panel/config.ini`
  (`webusername`/`webpassword`, дефолт `admin`/`admin`),
  сессии в памяти (sliding TTL из `session_ttl_min`, абсолютный лимит 12 ч,
  max 1000 сессий), журнал в `/var/log/awg-panel/auth.log` (0600, без переводов строк).
  TOTP/2FA/API — нет.
- Стек: Python3 stdlib (`http.server`, встроенный HTTPS), чистый SSR
  (формы работают без JS; внешний HTMX/CDN удалён в 0.1.8). Кнопки
  «Скопировать» работают через крошечный same-origin `/static/copy.js`
  (инлайн-`<script>` запрещён CSP `script-src 'self'` с 0.1.8, в 0.1.9 скрипт
  вынесен из страницы в статику). Стороннего веб-сервера нет.
- Привилегии: сервис работает от `root` и вызывает `manage`/`helper` напрямую
  без sudo (manage сам требует root: wg/iptables/конфиги). UFW/iptables не трогаем.
  Файл `/etc/sudoers.d/awg-panel` остался только как legacy для старых установок.
- Порт/хост/логин/пароль — в `/etc/awg-panel/config.ini`
  (`host`/`port`/`webusername`/`webpassword`, дефолт `0.0.0.0:8443` + `admin`/`admin`).

## Файлы проекта

- `src/awg_panel/` — `server.py` (роуты+HTML+статика `/static/style.css`,
  `/static/copy.js`), `manage.py` (обёртка `--json`),
  `system_info.py` (`/proc`), `auth.py`, `config.py`, `validate.py`,
  `__main__.py` (точка входа), `__init__.py` (версия)
- `bin/awg-panel-helper` — безопасные чтения live-файлов (валидация имён,
  серверный `PrivateKey` никогда не отдаётся)
- `bin/awg-panel-set-password` — смена логина/пароля в config.ini
  (старый `awg-panel-set-password-internal` и `/etc/awg-panel/password` удалены в 0.1.4)
- `packaging/` — `DEBIAN/{control,conffiles,postinst,prerm,postrm}`,
  `awg-panel.service`, `sudoers`, `config.ini.example`
- `build_deb.sh`, `.github/workflows/build-deb.yml` (сборка + релиз .deb на GitHub)

## Установка поверх живого сервера

```
# Рекомендуется dpkg (без _apt-предупреждения, см. ниже):
sudo dpkg -i awg-panel_*_all.deb
# postinst НЕ трогает /root/awg и /etc/amnezia — только свои файлы.
```

Что дальше (то же самое печатает postinst в конце установки):

1. Логин/пароль: `/etc/awg-panel/config.ini` (`webusername`/`webpassword`,
   дефолт `admin`/`admin`). Сменить: `sudo awg-panel-set-password`
   (или правка config.ini вручную), после правок —
   `sudo systemctl restart awg-panel`.
2. Открыть: `https://<IP-сервера>:8443/` (self-signed — подтвердить исключение).
   Проверка: `sudo systemctl status awg-panel --no-pager`,
   `sudo journalctl -u awg-panel -n 30 --no-pager`.

Про предупреждение apt при установке локального .deb:

```
N: Загрузка выполняется от лица суперпользователя без ограничений песочницы,
так как файл «.../awg-panel_*_all.deb» недоступен для пользователя «_apt».
```

Это безвредно: файл лежит в `$HOME`, куда у `_apt` нет доступа, и apt
дочитывает его как root. Чтобы не видеть его — ставить через
`sudo dpkg -i` (выше) либо скопировать .deb в доступное место:
`cp awg-panel_*_all.deb /tmp/ && sudo apt install /tmp/awg-panel_*_all.deb`.

Восстановление sudo после 0.1.1: выпуск 0.1.1 привёз
`/etc/sudoers.d/awg-panel` с владельцем uid 1001, такой файл ломает ВЕСЬ
sudo (`... is owned by uid 1001, should be 0`). Починить как root
(через консоль/`su -`/`pkexec`, т.к. сам sudo не работает):

```
su -
chown root:root /etc/sudoers.d/awg-panel
chmod 440 /etc/sudoers.d/awg-panel
visudo -c
```

После этого поставить 0.1.2+: там сборка идёт с `--root-owner-group`,
а postinst при каждом upgrade/reinstall сам чинит владельца/права.

## Безопасность (честно)

- Приватный ключ сервера из `awg0.conf` в браузер не отдаётся никогда
  (helper публикует только `#_Name`/`PublicKey`).
- Приватные ключи клиентов видит админ панели — так же, как root через manage.
- `awg show dump` целиком не показываем (там PSK).
- Все POST — с CSRF (constant-time, без падений на non-ASCII), редиректы после
  POST — `303`, кука `Secure; HttpOnly; SameSite=Lax`, rate-limit логина 5/5мин
  по socket-IP (`X-Forwarded-For` игнорируется).
- Заголовки: `nosniff/DENY/no-referrer` + `CSP default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'`, `HSTS`, `Permissions-Policy`.
- Лимиты: тело форм 1 МиБ (с закрытием соединения на `413`), max 2000 полей,
  max 100 имён в батче (`add/remove/regen`), stdout manage до 1 МиБ, ответы
  helper до 2 МиБ, таймаут соединения 10 с, лимит ожидания manage-фьючерсов.
- `manage`/`helper` вызываются списком аргументов (без shell), имена —
  `^[A-Za-z0-9_-]{1,63}$`, `expires` проверяется внутри (`^--expires=\d+d$`,
  1..3650), helper держит allowlist команд и режет symlink/`PATH` зажат.
- Пароль в `config.ini` в clear (600, root-only, атомарная запись через
  `mkstemp+replace`); `%` в пароле разрешён (`interpolation=None`), пробелы
  по краям не режутся; битый ini даёт дефолты, а не падение сервиса.
- `key.pem` создаётся под `umask 077` (без окна 644), `config.ini` ставится
  сразу `600`. Ошибки manage/helper в UI обобщены, детали — только в stderr сервиса.

## Проверка на dev-машине

```
python -m unittest discover -s tests -v
```

Полный e2e — только на VPS с установленным инсталлером
(нужны `/root/awg/manage_amneziawg.sh`, `/etc/amnezia/.../awg0.conf`).
