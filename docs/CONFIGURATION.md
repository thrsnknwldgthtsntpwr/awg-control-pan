# Конфигурация

Единственный конфиг панели: `/etc/awg-panel/config.ini`.

- Права: `600`, владелец `root:root` (там пароль в открытом виде).
- Секции: `[server]` + обязательная `[users]` + необязательная `[client_names]` (генератор имён).
- Нет файла, битый файл или нет `[users]` → отказ старта (fail-closed), смотрите `journalctl -u awg-panel`.
- Пример с комментариями: [packaging/config.ini.example](../packaging/config.ini.example).

После любых правок:

```bash
sudo systemctl restart awg-panel
```

## Таблица ключей

| Ключ | Дефолт | Допустимые значения | Комментарий |
|------|--------|---------------------|-------------|
| `host` | `0.0.0.0` | `^[A-Za-z0-9.\-:]{1,253}$`, иначе `0.0.0.0` | `0.0.0.0` — слушать везде; `127.0.0.1` — только локально (например за reverse-proxy). Тот же `host` используется и для HTTP-редиректора. |
| `port` | `8443` | `1..65535`, иначе `8443` | Порт HTTPS. |
| `http_redirect_port` | `80` | `0..65535` (`0` = выкл), иначе `80` | Plain-HTTP `:http_redirect_port -> https://<host>:port` (`301`). Стандарт — `80`. Совпадение с `port` или `0` — редиректор выключен, остаётся только HTTPS. |
| `cert` | `/etc/awg-panel/cert.pem` | путь | Создаёт `postinst` (self-signed, 825 дней). |
| `key` | `/etc/awg-panel/key.pem` | путь | Создаётся под `umask 077`, права `600`. |
| `auth_max_attempts` | `5` | `1..100` (clamp) | Неверных попыток с одного IP до блокировки. Блок — средствами сервиса (`429`), без `iptables/ufw`. |
| `auth_lock_minutes` | `5` | `1..1440` (clamp) | Время блокировки IP после исчерпания попыток. |
| `session_ttl_min` | `30` | `1..1440` (clamp) | Sliding TTL. Абсолютный лимит сессии — 12 ч, захардкожен в `auth.py`. |
| `manage_script` | `/root/awg/manage_amneziawg.sh` | путь | Underlay инсталлера. Менять только если инсталлер стоит нестандартно. |
| `awg_dir` | `/root/awg` | путь | Каталог live-файлов клиентов (`*.conf`, `*.vpnuri`, `*.png`). |
| `server_conf` | `/etc/amnezia/amneziawg/awg0.conf` | путь | Читается только через helper (`server-pubkeys`: имена + `PublicKey`). |
| `helper` | `/usr/sbin/awg-panel-helper` | путь | Исполняемый helper. Пути внутри helper захардкожены и игнорируют env. |
| `auth_log` | `/var/log/awg-panel/auth.log` | путь | Журнал входов (`0600`, поля без `\r\n`). |

## Генерация имён клиентов

```ini
[client_names]
prefix = user_
rand_bytes = 8
```

- Кнопка «Сгенерировать имя» на странице «Клиенты» подставляет в поле ввода `prefix` + случайный hex из `2*rand_bytes` символов — аналог `user_$(openssl rand -hex N)` (`rand_bytes=8` → `user_fb4c14c49c3e2483`, `rand_bytes=9` → 18 hex-символов).
- Секция необязательна, дефолты — `prefix = user_`, `rand_bytes = 8`. В отличие от `[users]`, ошибки здесь не роняют старт: мусор в `rand_bytes` → `8`, выход за `1..32` → clamp, плохой `prefix` → `user_`.
- Ограничение: итоговая длина `len(prefix) + 2*rand_bytes <= 63` (правило имён `validate.py`), иначе `rand_bytes` урезается под префикс.

## Смена пароля

Рекомендуемый способ — скрипт (атомарная запись через `mkstemp+replace`, сразу `0600`, `umask 077`):

```bash
sudo awg-panel-set-password
sudo systemctl restart awg-panel
```

Скрипт спросит `Логин панели [текущий]:`, затем дважды пароль. Пустой пароль запрещён, переводы строк запрещены, логин — `^[A-Za-z0-9_.\-]{1,64}$`. Скрипт правит `user.1/password.1` в `[users]`, остальных пользователей не трогает.

## Пользователи

```ini
[users]
user.1 = admin
password.1 = секрет1
user.2 = user2
password.2 = секрет2
```

- Секция `[users]` обязательна. Нет секции, пустая секция, `password.N` без `user.N` — **отказ старта**.
- Пары строго `user.N/password.N`, `N=1..254`, max 254 пользователя. Пробелы в индексах/именах ключей не допускаются (`user. 1` — ошибка).
- Логин: `^[A-Za-z0-9_.\-]{1,64}$`, уникален. Пароль: непустой, без `\r\n` (пробелы внутри значимы, `%` разрешён).
- Любая ошибка (дубль логина, пустой пароль, `>254`, неизвестный ключ, дубль опции) — **отказ старта**, смотрите `journalctl -u awg-panel`. Тихого fallback нет.
- Старые ключи `webusername`/`webpassword` (до 0.1.12) игнорируются (остатки можно удалить вручную).

```bash
sudo chmod 600 /etc/awg-panel/config.ini
sudo chown root:root /etc/awg-panel/config.ini
sudo systemctl restart awg-panel
```

## Минимальный пример

```ini
[server]
host = 0.0.0.0
port = 8443
session_ttl_min = 30

[users]
user.1 = admin
password.1 = поменяйте-меня
```

Остальное подхватится дефолтами.

## HTTP -> HTTPS редирект

`http://<IP>:http_redirect_port/*` отвечает только `301 Location: https://<тот-же-хост>:<port>/*`
(путь и query сохраняются, порт `443` в URL не пишется). Контент панели, куки,
авторизация и статика по HTTP **никогда** не отдаются — только редирект.

```ini
[server]
port = 8443
http_redirect_port = 80   # стандарт; 0 = выключить (только HTTPS)
```

- Нужен открытый `80/tcp` в фаерволе, иначе браузер до редиректора не дойдёт
  (панель фаервол не трогает). Проверка: `curl -v http://<IP>/` → `301` + `Location: https://<IP>:8443/`.
- Ошибка редиректора (порт занят `nginx/apache`, нет прав на `80`) не роняет
  основную HTTPS-панель — в `journalctl` будет `awg-panel-redirect: ... disabled`.
- Не работает `http://<IP>:8443/` (TLS-порт не умеет plain-HTTP) — это нормально,
  заходите либо `http://<IP>/` (редирект), либо сразу `https://<IP>:8443/`.
- Для закрытой установки поставьте `http_redirect_port = 0`, чтобы не светить `:80`.

## Закрытая установка (только через SSH-туннель)

```ini
[server]
host = 127.0.0.1
port = 8443
```

```bash
ssh -L 8443:127.0.0.1:8443 root@<сервер>
# открыть https://127.0.0.1:8443/
```
