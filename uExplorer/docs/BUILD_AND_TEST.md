# Сборка и проверка

## Windows / Visual Studio 2022

Сборка и запуск в Windows, все реализованные функции и использование результатов
в целевом игровом клиенте проверены. Scryde в подтверждённые интеграции не входит.

Требования: CMake 3.24+, VS2022 Desktop development with C++, Windows SDK.
Для UI — Python 3.10+ и `PySide6>=6.6,<7`. Текущая проверенная сборка — x64 Release.

Из каталога `uExplorer`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Эквивалентные команды:

```powershell
cmake -S . -B build-x64 -G "Visual Studio 17 2022" -A x64
cmake --build build-x64 --config Release
cmake --install build-x64 --config Release --prefix .
```

Открыть `build-x64\uExplorer.sln` в VS2022; выбрать Release/x64, собрать solution.
CMake создаёт цели `uexplorer_core` (DLL) и `uexplorer_cli` (EXE).
После сборки из IDE выполнить install-команду выше для обновления `bin`.
MSVC runtime статический (`/MT`, Debug `/MTd`).

`build.ps1 -Architecture Win32` создаёт отдельный solution, но устанавливает
результат в тот же `bin`. Win32 не проверялся; для UI потребуется подходящий
32-bit Python/Qt runtime. Рекомендуется проверенная x64-конфигурация.

Заголовок JSON берётся из
`../gameAddWebWithD3D9/browserTexture/vendor/nlohmann/json.hpp`.
При переносе исходников сохраните этот путь или измените CMake include path.
Самой готовой DLL этот каталог не нужен.

## Выбор ядра и Python

backend ищет ядро: `UEXPLORER_CORE`, затем `bin`, `build/Release`, `build`.
Если путь из переменной не существует, поиск продолжается. DLL должна
соответствовать разрядности процесса Python. `run.ps1 -Python <путь>` позволяет
выбрать интерпретатор; без аргумента приоритет у соседнего embedded runtime.

```powershell
python -m pip install -r requirements.txt
.\run.ps1 -Python 'C:\Python312\python.exe'
```

## CLI

Один запрос за запуск, JSON в stdin, UTF-8 ответ в stdout. Код завершения:
0 — успех, 1 — ошибка API, 2 — отсутствие выделенного ответа.

```powershell
'{"operation":"inspect","path":"D:/client/system/Interface.u"}' | .\bin\uexplorer_cli.exe
```

CLI возвращает код/метаданные в JSON. Запись `.uc` с отчётом реализована в
`backend.export_classes` и UI.

## Тесты

Тесты используют реальные fixtures соседних проектов, поэтому для их запуска
нужно полное дерево `rebuild`. Команды из `uExplorer`:

```powershell
$python = '..\interface_editor\dist\windows\runtime\python.exe'
& $python -B tests\validate.py
& $python -B tests\validate_formats.py
& $python -B tests\test_gui.py
& $python -B tests\compile_recovered.py
& $python -B tests\verify_roundtrip.py
```

Проверяйте `$LASTEXITCODE` после каждой команды.

- `validate.py`: независимый Python parser `gameAddWebWithD3D9/tools/ue2/ue2package.py`,
  opcode/PC/size/flags/native всех функций Gracia; побайтовый ScriptText;
  выборочный экспорт, запрет перезаписи, отмена, недопустимый путь, truncation.
- `validate_formats.py`: дополнительные пакеты, оба режима восстановления,
  missing dependencies, plain/Gamekit оболочки и неподдержанная версия.
  Статусы записываются в отчёт, наличие partial не означает падение теста.
- `test_gui.py`: реальный PySide6 offscreen, загрузка в Worker, 239 классов,
  read-only preview, фильтр, доступность кнопок, повторное переключение пакетов
  с выбранным классом и очистка при смене каталога. Это автоматический smoke test,
  а не ручная оценка внешнего вида.
- `compile_recovered.py`: создаёт новый `tests/compile-<timestamp>`, экспортирует
  Gracia, копирует compiler fixture и запускает UCC. Нужны соседние
  `gameAddWebWithD3D9/profiles/gracia/workspace` и `gameAddWebWithD3D9/toolchain`. Для этого fixture UC преобразуется
  в ANSI через Latin-1. Рабочие каталоги занимают место и сохраняются для анализа.
- `verify_roundtrip.py`: выбирает последний `compile-*/System/Interface.u`,
  сравнивает function flags/native, CFG expressions/routes, инициализацию/выход
  dispatcher, helper, исходные свойства, enum и наследование. Оригинальные
  комментарии/форматирование, defaults и все class flags этим тестом не проверяются.

## Результаты текущей проверки

| Проверка | Результат |
|---|---|
| VS2022 x64 Release через build.ps1 | Успешно; DLL/CLI установлены в bin |
| Gracia 123/0 | 239 recovered, 0 issues; все экспортированные классы компилируются |
| Сравнение декодера | 3259 функций совпали по opcode/PC/size/flags/native |
| Round-trip Gracia | 3259 функций, 20009 CFG-блоков, 0 ошибок; метаданные совпали |
| Gracia NWindow ScriptText | 108 исходников совпали побайтово |
| HF NWindow 123/37 | 113 source; force: 113 recovered |
| addWeb Interface 126/0 | 253 source; force: 252 recovered, 1 partial (L2Util/DelegateProperty) |
| int64 compiler Interface 126/0 | 216 source; force: 216 recovered |
| UI offscreen | Пройден |
| Ошибки/экспорт/оболочки | Пройдены описанные выше проверки |

Для addWeb fixtures зависимости дополнены из `gameAddWebWithD3D9/archive/addWeb/workspace/System`.
Семантический round-trip выполнялся для Gracia; другие строки таблицы отражают
извлечение/генерацию, не доказанную эквивалентность после компиляции.

Машиночитаемые отчёты: `tests/validation.json`, `tests/formats-validation.json`,
`tests/roundtrip-validation.json`. Они содержат хеши проверенных входов/ядра
или повторно скомпилированного пакета. Новая сборка/fixtures требуют повторных
проверок; старые отчёты не распространяются автоматически на изменения.
