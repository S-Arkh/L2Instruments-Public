# Браузер WebView2 в игровом интерфейсе

**Публикационная копия:** начните со [сборки из чистого клона](docs/PUBLICATION_BUILD.md).
В Git находятся исходники; комплекты и workspace создаются локально.
Статусы игровых проверок относятся к историческим хешам из отчётов.

Сборка в Windows и все реализованные игровые функции проверены на High Five
и Gracia. Для Scryde рабочая интеграция не получена, исследование прекращено.

[Карта трёх проектов, временные пути и результаты очистки](docs/PROJECT_LAYOUT.md).

[GPU/CPU: фактическая поддержка по профилям и проверка устройства игры](docs/GPU_CPU_BACKENDS.md).

## Клиентские профили

| Клиент | Каталог | Выход после полной подготовки | Исторический игровой статус |
|---|---|---|---|
| High Five REVISION 268 EN | [profiles/high-five](profiles/high-five/README.md) | `out/high-five/system` | Проверен в игре |
| Gracia Epilogue | [profiles/gracia](profiles/gracia/README.md) | `out/gracia/system` | Проверен в игре, без helper EXE |
| Scryde | [profiles/scryde](profiles/scryde/README.md) | Нет | Исследование закрыто; тестовые клиенты удалены |

Реализованный API браузера:

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
не взаимозаменяемы. Компилятор импортируется в `toolchain/`, SDK/editor — в `sdk/`,
общие UE2-инструменты — в `tools/ue2/`. Соседние addWeb и gameAddWeb больше не нужны.
Ранние реализации и исследования сохранены в `archive/addWeb/` и
`archive/gameAddWeb/`. [Перенос и проверки](docs/MIGRATION.md).

## Сборка

Для чистого клона выполните [PUBLICATION_BUILD](docs/PUBLICATION_BUILD.md):
установите SDK, подготовьте native-stage, соберите DLL/EXE. Эти шаги не требуют
игровых файлов и создают результаты в `profiles/high-five/build/Release` и
`profiles/gracia/build-inprocess/Release`.

Для полного UI-комплекта дополнительно нужны импортированные клиентские входы,
UCC/SDK и Classes. После их подготовки из каталога `gameAddWebWithD3D9`:
HF — `./profiles/high-five/build.ps1`, Gracia — `./profiles/gracia/build_inprocess.ps1`.
Пересборка Interface с аргументами открытия из уже подготовленных workspace:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_browser_options.ps1
```

`out/<клиент>/` создаётся этим последним сценарием, а не native-сборкой.
Готовые `out`, `result` и workspace в Git не входят. Прежние комплекты и правила
их обновления описаны отдельно в [HISTORICAL_LAYOUT](docs/HISTORICAL_LAYOUT.md).

## После переноса каталогов

| Старый путь | Новый путь |
|---|---|
| `browserTexture/` | `profiles/high-five/` |
| `gracia/` | `profiles/gracia/` |
| `scryde/` | `profiles/scryde/` |
| `profiles/<клиент>/result-browser-options/` (ранее `result-open-api/`) | `out/<клиент>/` |
| `build_browser_open_api.ps1` | `build_browser_options.ps1` |

Исторические логи/JSON могут содержать старые абсолютные пути: это запись условий
тех запусков, а не актуальные команды. Подтверждение работы относится к конкретным
хешам, не автоматически к любой последующей пересборке.

Проверка переноса: [reports/profile-layout-validation.json](reports/profile-layout-validation.json).
Старый пустой каталог `gracia/` удалён; отсутствие проверено.
Рабочий профиль — profiles/gracia. Перенос каталогов завершён.

## Документация

- [Руководство](docs/GUIDE.md)
- [Перенос на другие клиенты](docs/PORTING.md)
- [Gracia: причина прежнего сбоя и in-process решение](docs/GRACIA_INPROCESS_BROWSER.md)
- [История HF и GPU-эксперимента](docs/HF_IMPLEMENTATION_HISTORY.md)
