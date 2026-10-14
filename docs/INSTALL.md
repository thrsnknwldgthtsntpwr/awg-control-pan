# Установка

Эта инструкция — для живого сервера, где уже стоит
[bivlked/amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

## 1. Требования

- Debian 11+ / Ubuntu 22.04+, systemd.
- `/root/awg/manage_amneziawg.sh` — исполняемый.
- `/etc/amnezia/amneziawg/awg0.conf` — существует.
- Открытый порт панели (дефолт `8443/tcp`) — проверьте фаервол.
- Для авто-редиректа `http://<IP>/ → https://<IP>:8443/` — открытый `80/tcp`
  (`http_redirect_port = 80` по умолчанию; `0` — выключить редирект).

Зависимости `.deb`: `python3`, `openssl`, `systemd`. Рекомендуется `qrencode`.

## 2. Установка .deb

```bash
# Скачать нужный релиз со страницы Releases
wget https://github.com/thrsnknwldgthtsntpwr/awg-control-pan/releases/download/v0.1.14/awg-panel_0.1.14_all.deb

# Рекомендуется именно dpkg:
sudo dpkg -i awg-panel_0.1.14_all.deb
```

`postinst` делает только своё:

- `/etc/awg-panel/config.ini` (создаёт `600 root:root`, существующий не перезаписывает);
- self-signed `cert.pem`/`key.pem` (`key.pem` — `600 root:root`, `umask 077` без окна `644`);
- `/var/lib/awg-panel`, `/var/log/awg-panel`;
- `systemctl enable + restart awg-panel`.

`/root/awg` и `/etc/amnezia` **не трогаются**.

В конце установки `postinst` печатает памятку «что дальше» — те же 3 шага, что ниже.

## 3. Что дальше

```bash
# 1. Сменить пароль из примера (user.1/admin в config.ini.example)
sudo awg-panel-set-password
# или вручную: правка /etc/awg-panel/config.ini → [users] user.1/password.1

# 2. Применить и проверить
sudo systemctl restart awg-panel
sudo systemctl status awg-panel --no-pager
sudo journalctl -u awg-panel -n 30 --no-pager

# 3. Открыть
# https://<IP-сервера>:8443/  (self-signed — подтвердить исключение в браузере)
```

Порт берётся из `config.ini` (`port`). Если меняли порт вручную — откройте свой.

## 4. Обновление

```bash
sudo dpkg -i awg-panel_<новая-версия>_all.deb
```

- Конфиг сохраняется (conffile): ваши `host/port`, пользователи и лимиты не затрутся.
- Права лечатся при каждом upgrade (`key.pem 600`, `config.ini 600`, `sudoers 440 root:root`).

Откат: `sudo dpkg -i awg-panel_<старая>_all.deb` (конфиг сохранится).

## 5. Удаление

```bash
sudo apt remove awg-panel   # бинарники и юнит удалены, конфиг, ключи и логи остаются
sudo apt purge awg-panel    # + удаляет /etc/awg-panel (конфиг, ключи) и /var/log/awg-panel
```

Клиенты VPN при этом **не удаляются** — они живут в инсталлере.

## 6. Про предупреждение _apt

При установке через `apt install ./awg-panel_*.deb` вы увидите:

```text
N: Загрузка выполняется от лица суперпользователя без ограничений песочницы,
так как файл «.../awg-panel_*_all.deb» недоступен для пользователя «_apt».
```

Это безвредно: файл лежит в `$HOME`, куда у системного пользователя `_apt` нет доступа, и `apt` дочитывает его как root.

Чтобы не видеть предупреждение, ставьте одним из способов:

```bash
sudo dpkg -i awg-panel_*_all.deb
# или
cp awg-panel_*_all.deb /tmp/ && sudo apt install /tmp/awg-panel_*_all.deb
```

## 7. Сборка .deb из исходников

```bash
git clone https://github.com/thrsnknwldgthtsntpwr/awg-control-pan.git
cd awg-control-pan
./build_deb.sh 0.1.14
# → dist/awg-panel_0.1.14_all.deb
```

Требуется `dpkg-deb`. На Windows — собирать в WSL (на `/mnt/d` с правами `777` собирайте через `/tmp`, см. DEVELOPMENT).
