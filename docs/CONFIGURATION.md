# Конфигурация

Единственный конфиг панели: `/etc/awg-panel/config.ini`.

- Права: `600`, владелец `root:root` (там пароль в открытом виде).
- Секция: `[server]`.
- Битый/отсутствующий файл → сервис стартует на дефолтах, а не падает.
- Пример с комментариями: [packaging/config.ini.example](../packaging/config.ini.example).

После любых правок:

```bash
sudo systemctl restart awg-panel
```

## Таблица ключей

| Ключ | Дефолт | Допустимые значения | Комментарий |
|------|--------|---------------------|-------------|
| `host` | `0.0.0.0` | `^[A-Za-z0-9.\-:]{1,253}$`, иначе `0.0.0.0` | `0.0.0.0` — слушать везде; `127.0.0.1` — только локально (например за reverse-proxy). |
| `port` | `8443` | `1..65535`, иначе `8443` | Порт HTTPS. |
| `cert` | `/etc/awg-panel/cert.pem` | путь | Создаёт `postinst` (self-signed, 825 дней). |
| `key` | `/etc/awg-panel/key.pem` | путь | Создаётся под `umask 077`, права `600`. |
| `webusername` | `admin` | trimmed, пусто → `admin` | Логин панели. |
| `webpassword` | `admin` | **не** trim'ится (пробелы значимы), только `\r\n` срезаются; пусто/whitespace-only → `admin` | `%` разрешён (`interpolation=None`). |
| `session_ttl_min` | `30` | `1..1440` (clamp) | Sliding TTL. Абсолютный лимит сессии — 12 ч, захардкожен в `auth.py`. |
| `manage_script` | `/root/awg/manage_amneziawg.sh` | путь | Underlay инсталлера. Менять только если инсталлер стоит нестандартно. |
| `awg_dir` | `/root/awg` | путь | Каталог live-файлов клиентов (`*.conf`, `*.vpnuri`, `*.png`). |
| `server_conf` | `/etc/amnezia/amneziawg/awg0.conf` | путь | Читается только через helper (`server-pubkeys`: имена + `PublicKey`). |
| `helper` | `/usr/sbin/awg-panel-helper` | путь | Исполняемый helper. Пути внутри helper захардкожены и игнорируют env. |
| `auth_log` | `/var/log/awg-panel/auth.log` | путь | Журнал входов (`0600`, поля без `\r\n`). |

## Смена пароля

Рекомендуемый способ — скрипт (атомарная запись через `mkstemp+replace`, сразу `0600`, `umask 077`):

```bash
sudo awg-panel-set-password
sudo systemctl restart awg-panel
```

Скрипт спросит `Логин панели [текущий]:`, затем дважды пароль. Пустой пароль запрещён, переводы строк запрещены, логин — `^[A-Za-z0-9_.\-]{1,64}$`.

Вручную (эквивалент):

```ini
[server]
webusername = boss
webpassword = s3cret-пароль-с-%-и-пробелами
```

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
webusername = admin
webpassword = поменяйте-меня
session_ttl_min = 30
```

Остальное подхватится дефолтами.

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
