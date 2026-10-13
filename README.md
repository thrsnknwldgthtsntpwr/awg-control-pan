# awg-panel — веб-интерфейс поверх amneziawg-installer

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
  Regen («Пересоздать файлы») — только внутри карточки клиента.
  Имя — ссылка в карточку: конфиг, `vpn://`, QR, трафик, handshake, срок.
- Срок при добавлении — только днями (пусто = бессрочно), удаление истекших — крон инсталлера.
- Auth: один `admin`, хеш PBKDF2 в `/etc/awg-panel/password` (не системный юзер),
  сессии в памяти, журнал в `/var/log/awg-panel/auth.log`. TOTP/2FA/API — нет.
- Стек: Python3 stdlib (`http.server`, встроенный HTTPS), SSR + HTMX через CDN
  (формы работают и без JS). Стороннего веб-сервера нет.
- Привилегии: сервис — пользователь `awgpanel` + точечный sudoers
  (только нужные `manage` + `/usr/sbin/awg-panel-helper`). UFW/iptables не трогаем.
- Порт/хост — в `/etc/awg-panel/config.ini` (`host`/`port`, дефолт `0.0.0.0:8443`).

## Файлы проекта

- `src/awg_panel/` — `server.py` (роуты+HTML), `manage.py` (обёртка `--json`),
  `system_info.py` (`/proc`), `auth.py`, `config.py`, `validate.py`
- `bin/awg-panel-helper` — безопасные чтения live-файлов (валидация имён,
  серверный `PrivateKey` никогда не отдаётся)
- `bin/awg-panel-set-password[-internal]` — смена пароля
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

1. Пароль: `sudo cat /root/.awg-panel-initial-password` (только первая
   установка). Сменить: `sudo awg-panel-set-password`.
2. Настройки: `/etc/awg-panel/config.ini` (`host`/`port`, дефолт `0.0.0.0:8443`),
   после правок — `sudo systemctl restart awg-panel`.
3. Открыть: `https://<IP-сервера>:8443/` (self-signed — подтвердить исключение).
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
- Все POST — с CSRF, кука `Secure; HttpOnly; SameSite=Lax`, rate-limit логина 5/5мин.
- `manage` вызывается списком аргументов (без shell), имена — `^[A-Za-z0-9_-]{1,63}$`.

## Проверка на dev-машине

```
python -m unittest discover -s tests -v
```

Полный e2e — только на VPS с установленным инсталлером
(нужны `/root/awg/manage_amneziawg.sh`, `/etc/amnezia/.../awg0.conf`).
