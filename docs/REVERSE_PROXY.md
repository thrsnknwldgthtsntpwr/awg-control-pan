# AWG Panel за nginx

`base_url` — префикс пути панели, например `/awg` или `/tools/awg`.
Для отдельного домена без подпути оставьте его пустым. Полный адрес с `https://`
в этот параметр не записывается.

Схема на одном сервере:

```text
Браузер → https://panel.example.com/awg/ → nginx :443
       → https://127.0.0.1:8443/awg/ → awg-panel
```

nginx принимает внешние соединения, выбирает сервис по домену (`server_name`)
и пути (`location`), затем передаёт запрос на его локальный порт (`proxy_pass`).
Каждый сервис запускается своим systemd-юнитом и слушает отдельный порт.
В этой схеме оба участка используют HTTPS; сертификат браузеру отдаёт nginx.

## 1. Настроить панель

Добавьте параметры в **существующую** секцию `[server]` файла
`/etc/awg-panel/config.ini`, сохранив остальные настройки и секцию `[users]`:

```ini
[server]
host = 127.0.0.1
port = 8443
base_url = /awg
http_redirect_port = 0
trusted_proxies = 127.0.0.1/32
```

Панель продолжает использовать свои `cert.pem` и `key.pem`. Порт 80 теперь
обслуживает nginx. Новые настройки применяются после перезапуска:

```bash
sudo systemctl restart awg-panel
sudo systemctl status awg-panel --no-pager
```

При обновлении `.deb` существующий `config.ini` сохраняется: новые параметры
добавляются вручную. Пустой `base_url` сохраняет прежние адреса `/login`, `/clients`.
`/awg/` в конфиге нормализуется до `/awg`; домены, `..`, query и кодированные
разделители отклоняются при запуске.

## 2. Настроить nginx

Пример для Debian/Ubuntu. Нужны установленный nginx, DNS-запись домена на сервер
и действующий сертификат этого домена. Замените `panel.example.com` и пути к
его сертификату своими значениями. Если HTTPS-vhost уже есть, добавьте `location`
в него, без второго блока с таким же `server_name`.

Файл `/etc/nginx/sites-available/awg-panel`:

```nginx
server {
    listen 80;
    server_name panel.example.com;
    return 301 https://panel.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name panel.example.com;

    ssl_certificate     /etc/letsencrypt/live/panel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.example.com/privkey.pem;

    location = /awg {
        return 301 /awg/$is_args$args;
    }

    location /awg/ {
        # Без завершающего /: путь /awg/... передаётся целиком.
        proxy_pass https://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        proxy_set_header X-Real-IP $remote_addr;

        # Проверка локального self-signed сертификата, созданного postinst.
        # Его CN = awg-panel. Для собственного сертификата укажите его имя/CA.
        proxy_ssl_trusted_certificate /etc/awg-panel/cert.pem;
        proxy_ssl_verify on;
        proxy_ssl_name awg-panel;

        proxy_redirect off;
        proxy_cache off;
        proxy_connect_timeout 10s;
        proxy_read_timeout 150s;
        client_max_body_size 1m;
    }
}
```

Активируйте новый конфиг и примените его после успешной проверки:

```bash
sudo ln -s /etc/nginx/sites-available/awg-panel /etc/nginx/sites-enabled/awg-panel
sudo nginx -t
sudo systemctl reload nginx
```

Откройте `https://panel.example.com/awg/`. Ссылки, формы, скачивания, QR,
статика и редиректы будут содержать `/awg`; cookie сессии получает `Path=/awg/`.
После смены префикса войдите заново.

Для панели в корне отдельного домена оставьте `base_url =`, удалите
`location = /awg` и замените `location /awg/` на `location /`.
Для других сервисов создавайте свои `location`/домены и локальные порты.
Если сервис находится в подпути, ему тоже нужна поддержка такого префикса.

## Реальный IP и диагностика

`trusted_proxies` — IP или CIDR **непосредственного** прокси через запятую.
Пусто означает «не доверять заголовкам». Панель читает `X-Real-IP` только от
этих адресов и использует его для журнала входов и блокировки неудачных попыток.
nginx должен перезаписывать заголовок через `$remote_addr`, как в примере.
`X-Forwarded-For` и `X-Forwarded-Prefix` панель не использует.
В цепочке из нескольких прокси сначала настройте определение клиентского IP
на nginx; пример выше рассчитан на прямое подключение браузера к nginx.

- **502:** проверьте `systemctl status awg-panel`, локальный порт и
  `/var/log/nginx/error.log`. Ошибка проверки upstream-сертификата означает
  несоответствие CA/имени или истёкший сертификат. При замене `cert.pem`
  перезагрузите конфигурацию nginx.
- **504:** смотрите `journalctl -u awg-panel`; операции установщика могут
  занимать до 120 секунд, поэтому `proxy_read_timeout` установлен в 150 секунд.
- **404 после проксирования:** сверяйте `base_url` и `location`. Не добавляйте
  `/` в конец `proxy_pass` из примера: он удалит `/awg/` из upstream-пути.
- **Все пользователи блокируются вместе:** проверьте `trusted_proxies` и
  `proxy_set_header X-Real-IP $remote_addr`.
- **Не сохраняется вход:** в браузере должен быть HTTPS; cookie имеет `Secure`.

Семантика передачи URI и HTTPS к upstream описана в
[официальной документации nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
