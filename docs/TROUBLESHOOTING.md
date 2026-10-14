# Диагностика (Troubleshooting)

## Быстрые команды

```bash
sudo systemctl status awg-panel --no-pager
sudo journalctl -u awg-panel -n 50 --no-pager
sudo cat /var/log/awg-panel/auth.log
sudo cat /etc/awg-panel/config.ini
```

> Панель осознанно показывает в браузере обобщённые ошибки (`rc=...`),
> а детали пишет в stderr сервиса. Смотрите `journalctl` по SSH.

---

## manage check failed (rc=1) / list failed (rc=1)

Самый частый класс проблем — панели нечего показать, потому что упал underlay.

Проверьте по порядку:

```bash
# 1. Жив ли manage и что он сам говорит
sudo /bin/bash /root/awg/manage_amneziawg.sh check --json --no-color | head -c 2000
sudo /bin/bash /root/awg/manage_amneziawg.sh list --json --no-color | head -c 2000

# 2. Жив ли интерфейс
ip addr show awg0
systemctl status awg-quick@awg0 --no-pager

# 3. Что видит панель
sudo journalctl -u awg-panel -n 50 --no-pager | tail -30
```

Если `manage` по SSH тоже падает — это проблема инсталлера/системы, не панели.

## В UI «v? / поколение ?»

Значит упал `helper init-info` (маркеры `AWG_PROTOCOL`/`SCRIPT_VERSION`):

```bash
sudo /usr/sbin/awg-panel-helper init-info
cat /root/awg/awgsetup_cfg.init
```

## TLS load failed / сервис в restart-loop

Актуально для версий `≤0.1.3`. Починено в `0.1.4`:

- сервис работает от `root`, `key.pem` — `600 root:root`, `postinst` лечит права при каждом upgrade.

Лечение: обновитесь до актуальной версии тем же `dpkg -i`.

```bash
sudo journalctl -u awg-panel -n 20 --no-pager
# было: TLS load failed (...key.pem): Permission denied
```

## sudo сломан после 0.1.1 (is owned by uid 1001)

Выпуск `0.1.1` привёз `/etc/sudoers.d/awg-panel` с владельцем не-root — такой файл ломает **весь** `sudo`:

```text
sudo: /etc/sudoers.d/awg-panel is owned by uid 1001, should be 0
```

Чинить как root (через консоль хостера / `su -` / `pkexec`, сам `sudo` не работает):

```bash
su -
chown root:root /etc/sudoers.d/awg-panel
chmod 440 /etc/sudoers.d/awg-panel
visudo -c
```

После этого ставьте `≥0.1.2`: сборка идёт с `--root-owner-group`, а `postinst` сам чинит владельца/права при каждом upgrade.

## Не пускает в панель / 429

- Rate-limit средствами сервиса (без `iptables`): `auth_max_attempts` неверных попыток → блок IP на `auth_lock_minutes` (дефолт `5/5мин`, `429 Too Many Attempts`). Подождите или зайдите с другого IP.
- Проверьте пользователей (`[users]` `user.N/password.N`, fallback `webusername/webpassword`) в `/etc/awg-panel/config.ini` и рестарт сервиса после правок. Ошибка в `[users]` — отказ старта, смотрите `journalctl -u awg-panel`.
- `X-Forwarded-For` игнорируется осознанно — лимит считается по socket-IP.

## Порт занят / не открывается

```bash
sudo ss -tlnp | grep -E ':(80|8443)'
# поменяйте port / http_redirect_port в /etc/awg-panel/config.ini + restart
```

Self-signed сертификат — это нормально: браузер покажет предупреждение, нужно подтвердить исключение один раз.

## http://<IP>:8443 не отвечает, а https://<IP>:8443 работает

Так и должно быть: TLS-порт не понимает plain-HTTP (handshake рвётся до HTTP).
Заходите `http://<IP>/` (редирект `301 → https://<IP>:8443/`, нужен открытый
`80/tcp` и `http_redirect_port = 80`) либо сразу `https://<IP>:8443/`.
Проверка редиректа: `curl -v http://<IP>/` → `301` + `Location: https://<IP>:8443/`.

## Предупреждение _apt при установке

Безвредно, см. [INSTALL.md](INSTALL.md#6-про-предупреждение-_apt). Ставьте через `sudo dpkg -i`.

## Куда писать, если не помогло

Откройте Issue с выводом (секреты затрите):

```bash
sudo systemctl status awg-panel --no-pager
sudo journalctl -u awg-panel -n 50 --no-pager
dpkg -l | grep awg-panel
cat /etc/awg-panel/config.ini | sed 's/webpassword.*/webpassword = ***/'
```
