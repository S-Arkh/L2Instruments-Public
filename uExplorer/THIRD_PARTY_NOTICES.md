# Сторонние компоненты portable-сборки

Собственный код uExplorer распространяется по MIT, см. `LICENSE`.

- CPython 3.12.10: PSF и уведомления включённых компонентов — `runtime/LICENSE.txt`.
- PySide6-Essentials / Qt 6.12.0 и Shiboken6 6.12.0: LGPL/GPL либо коммерческая
  лицензия. Тексты LGPL-3.0, GPL-2.0 и GPL-3.0 включены в `licenses/` из
  SPDX license-list-data v3.27.0 с проверкой SHA-256. Оригинальные уведомления
  и metadata wheels сохраняются в `packages`, включая `*.dist-info/licenses`.
  Исходные дистрибутивы соответствующих версий доступны
  на https://download.qt.io/official_releases/qt/6.12/ и
  https://download.qt.io/official_releases/QtForPython/ .
  Qt/PySide поставляются как отдельные динамические библиотеки и Python-пакеты.
- Microsoft Visual C++ runtime: оригинальные файлы и уведомления из официальных
  CPython/Qt-дистрибутивов; часть DLL копируется в `runtime` для загрузки Qt.
- nlohmann/json 3.12.0: MIT, `licenses/nlohmann_json.txt`; включён в C++-ядро.

Точные входные архивы и их SHA-256 записаны в `BUILDINFO.json`. Упаковщик сохраняет
полное содержимое официальных wheels, в том числе их уведомления и лицензии.
Игровые пакеты для работы пользователь выбирает отдельно.
