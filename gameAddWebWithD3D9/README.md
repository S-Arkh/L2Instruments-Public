# Браузер WebView2 в игровом интерфейсе

**Публикационная копия:** начните со [сборки из чистого клона](docs/PUBLICATION_BUILD.md).
В Git находятся исходники; комплекты и workspace создаются локально.
Статусы игровых проверок относятся к историческим хешам из отчётов.

Сборка в Windows и все реализованные игровые функции проверены на High Five
и Gracia. Для Scryde рабочая интеграция не получена, исследование прекращено.

[Карта трёх проектов, временные пути и результаты очистки](docs/PROJECT_LAYOUT.md).

[GPU/CPU: фактическая поддержка по профилям и проверка устройства игры](docs/GPU_CPU_BACKENDS.md).

## Клиентские профили

| Клиент | Каталог | Актуальный комплект | Статус |
|---|---|---|---|
| High Five REVISION 268 EN | [profiles/high-five](profiles/high-five/README.md) | `out/high-five/system` | Проверен в игре |
| Gracia Epilogue | [profiles/gracia](profiles/gracia/README.md) | `out/gracia/system` | Проверен в игре, без helper EXE |
| Scryde | [profiles/scryde](profiles/scryde/README.md) | Нет | Исследование закрыто; тестовые клиенты удалены |

Актуальные комплекты поддерживают:

```uc
BrowserWnd(GetScript("BrowserWnd")).OpenBrowser("https://example.com", true);
```

Второй аргумент скрывает Home, Reload, адресную строку и Go. Размер страницы
не меняется; сворачивание и закрытие сохраняются. [Подробности API](docs/BROWSER_OPEN_API.md).
Подтверждение работы обоих клиентов: [отчёт](reports/browser-options-validation.json).

## Структура

- `profiles/<клиент>/` — исходники/адаптеры, подготовка, workspace, сборки и тесты клиента.
- `docs/` — общие руководства, архитектура и история исследований.
- `reports/` — межпрофильные результаты и подтверждения.
- `tools/`, `client_profiles.json` — общая проверка ABI и каталог профилей.
- `prototype/` — ранний HF-адаптер текстуры; используется подготовкой HF.
- `native/`, `CMakeLists.txt`, `build.ps1`, `tests/`, `build/` — отдельный эксперимент
  D3D11 → D3D9Ex, а не комплект для установки в клиент.

Общий BrowserWnd и WebView/WGC-исходники пока находятся в high-five;
подготовка Gracia явно использует их. Скомпилированные файлы разных клиентов
не взаимозаменяемы. Компилятор находится в `toolchain/`, SDK/editor — в `sdk/`,
общие UE2-инструменты — в `tools/ue2/`. Соседние addWeb и gameAddWeb больше не нужны.
Ранние реализации и исследования сохранены в `archive/addWeb/` и
`archive/gameAddWeb/`. [Перенос и проверки](docs/MIGRATION.md).

## Сборка

Базовая HF-сборка: `profiles/high-five/build.ps1`.
Gracia без helper: `profiles/gracia/build_inprocess.ps1`.
Пересборка Interface с аргументами открытия из подготовленных workspace:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_browser_options.ps1
```

В `out/<клиент>/` находится текущая пользовательская сборка.
В каждом профиле `result` — предыдущий базовый комплект; у Gracia `result` содержит старый helper,
а `result-inprocess` — предыдущий вариант без helper. Прежние install.py обслуживают
именно `result`, поэтому для обновления установленного соответствующего комплекта
на Browser Options заменяется Interface.u из `out/<клиент>/system`
при закрытом клиенте с сохранением предыдущего файла.

## После переноса каталогов

| Старый путь | Новый путь |
|---|---|
| `browserTexture/` | `profiles/high-five/` |
| `gracia/` | `profiles/gracia/` |
| `scryde/` | `profiles/scryde/` |
| `profiles/<клиент>/result-browser-options/` (ранее `result-open-api/`) | `out/<клиент>/` |
| `build_browser_open_api.ps1` | `build_browser_options.ps1` |

Исторические логи/JSON могут содержать старые абсолютные пути: это запись условий
тех запусков, а не актуальные команды. Старые CMake-каталоги с абсолютным cache
сохранены в `profiles/<клиент>/archive/pre-layout-build*`; новые сборки используют
новые build-каталоги. Подтверждение работы относится к конкретным хешам,
не автоматически к любой последующей пересборке.

Проверка переноса: [reports/profile-layout-validation.json](reports/profile-layout-validation.json).
Старый пустой каталог `gracia/` удалён; отсутствие проверено.
Рабочий профиль — profiles/gracia. Перенос каталогов завершён.

## Документация

- [Руководство](docs/GUIDE.md)
- [Перенос на другие клиенты](docs/PORTING.md)
- [Gracia: причина прежнего сбоя и in-process решение](docs/GRACIA_INPROCESS_BROWSER.md)
- [История HF и GPU-эксперимента](docs/HF_IMPLEMENTATION_HISTORY.md)
