# Сторонние компоненты

Корневая MIT-лицензия относится к собственному коду проекта.

- MinHook: BSD-2-Clause, [лицензия](int64/third_party/minhook/LICENSE.txt),
  [происхождение](int64/third_party/minhook/UPSTREAM.json).
- XDAT-схемы: acmi, [LICENSE.acmi](interface_editor/LICENSE.acmi).
- DAT-форматы/константы: acmi, [LICENSE.dat-format](interface_editor/LICENSE.dat-format).
- Единственный включённый runtime DLL — zlib для редактора:
  [ZLIB-LICENSE.txt](interface_editor/third_party/windows/ZLIB-LICENSE.txt).
- nlohmann/json: MIT; устанавливается через Python-пакет `nlohmann_json`.
  Используется редактором, uExplorer и браузером. Заголовки браузера генерируются
  `tools/fetch_dependencies.py` из установленного пакета с исходными уведомлениями.
- Microsoft WebView2 SDK/Runtime, Windows SDK: устанавливаются отдельно,
  действуют условия Microsoft. SDK скачивается с NuGet, версия и SHA-256
  записываются в локальный `sdk/webview2/download.json`.
- Python — PSF; PySide6/Shiboken6/Qt — LGPL/GPL либо коммерческая лицензия;
  pybind11 — BSD; Pillow — HPND; OpenSSL 3 — Apache-2.0; zlib — zlib.

[Подробности зависимостей редактора](interface_editor/THIRD_PARTY_NOTICES.md).
При создании бинарных Releases вместе с runtime включаются соответствующие
лицензии и уведомления. Игровые библиотеки и данные в Git не включены.
