# Участие в разработке (Contributing)

Спасибо, что хотите помочь. Проект маленький — правила тоже короткие.

## Как предложить изменение

1. Откройте Issue (баг → вывод `journalctl` + версия; фича → use-case, а не «добавьте всё»).
2. Форкните, сделайте ветку `fix/...` или `feat/...`.
3. Добавьте/обновите тесты (`python3 -m unittest discover -s tests -v` → должно быть зелёным).
4. Откройте PR на `master` с описанием: что, зачем, как проверено.

## Что обязательно

- **Тесты:** новый фикс = новый регресс-тест в `tests/test_panel.py`. Без тестов PR не мержится (кроме доки).
- **Проверки:**

  ```bash
  python3 -m py_compile src/awg_panel/*.py bin/awg-panel-set-password
  python3 -m unittest discover -s tests -v
  bash -n bin/awg-panel-helper packaging/DEBIAN/postinst build_deb.sh
  ```

- **LF, не CRLF:** `.gitattributes` держит LF для скриптов/`*.py`/`*.md`/`*.yml`. CRLF ломает `#!/bin/bash` на сервере.
- **Без секретов:** пароли, ключи, `*.pem`, IP серверов — никогда в коммит. `dist/*.deb` и `__pycache__` — в `.gitignore`.
- **Безопасность:** не теките `stderr`/`PSK`/`PrivateKey` в браузер; вызовы — argv без shell; валидация имён — через `validate.py`.

## Стиль коммитов

Короткий imperative, как уже в истории:

```text
release 0.1.X: кратко что
fix: key.pem 640 root:awgpanel with self-heal
docs: README in sync with 0.1.9
```

## Релизы (для мейнтейнера)

```bash
# версия в src/awg_panel/__init__.py + README-бейдж + CHANGELOG.md
git commit -am "release 0.1.X: ..."
git tag v0.1.X
git push origin master --tags
# → CI build-deb.yml соберёт .deb и приложит к Release
```

Вопросы — в Issues. Документация по коду — в [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
