# L2Instruments

Инструменты для исследования и модификации клиента Lineage II / Unreal Engine 2.
Один репозиторий с самостоятельными компонентами и общими сценариями работы.

В исходном проекте подтверждены сборки в Windows и реализованные игровые
функции на целевых профилях, включая браузер HF/Gracia. Для Scryde подтверждён
только pinkDream; остальные интеграции не получены или исследования прекращены.
Проверки публикационной копии: [docs/VALIDATION.md](docs/VALIDATION.md).

| Компонент | Назначение | Платформа |
|---|---|---|
| [int64](int64/) | UCC launcher/bridge, INT64, пакеты и подготовка SDK | Windows x86 |
| [dll](dll/) | ExtensionL2, native API, профили Core и проверка комплектов | Windows x86 |
| [interface_editor](interface_editor/) | Редактор XDAT, анализ схем, DAT/SysString и текстуры | Windows x64; Linux |
| [uExplorer](uExplorer/) | Просмотр `.u`, ScriptText и восстановление UnrealScript | Windows x64; ядро также Linux |
| [gameAddWebWithD3D9](gameAddWebWithD3D9/) | WebView2 в интерфейсе HF/Gracia, адаптеры и исследования | Windows x86 |
| [pinkDream](pinkDream/) | Генерация тем, импорт текстур, установка и откат | Python |
| [test_interfaces](test_interfaces/) | Пример native INT64/file-I/O через кнопку Credit | Windows x86 |
| [InfoOfDll](InfoOfDll/) | Справочник исследованных DLL и ABI | Документация |

`ucc64` означает поддержку 64-битных чисел: это **не x64-компилятор**.
Профили относятся к конкретным хешам и ABI клиента, а не ко всем сборкам хроник.

## Пути в документации

Корень репозитория — каталог с этим README и папками `dll`, `int64`,
`interface_editor` и другими проектами. Он может находиться в любом месте.
Пути внутри репозитория указаны относительно этого корня либо рабочего каталога,
явно названного в инструкции.

`<HF_CLIENT>`, `<GRACIA_CLIENT>` и `<SCRYDE_CLIENT>` обозначают корни установленных
клиентов соответствующих профилей; `system` и `SysTextures` — их подкаталоги.
Заменяйте обозначения своими путями, не вводите угловые скобки буквально.
В командах PowerShell пути задаются переменными, например:

```powershell
$ClientRoot = Read-Host 'Полный путь к корню нужного клиента'
$ClientSystem = Join-Path $ClientRoot 'system'
```

Для Scryde корень — каталог, содержащий `SysTextures` и `Scryde`, а не сама
подпапка `Scryde`. `<TEMP>` обозначает существующий временный каталог;
в PowerShell его можно получить через `[System.IO.Path]::GetTempPath()`.
Абсолютные пути вида `D:\YourClient` или `C:\Python312` — условные примеры:
подставьте расположение своей установки.

## Начало работы

Нужны Python 3.12, CMake 3.24+, для Windows — Visual Studio 2022 с C++ tools
и Windows SDK. Команды ниже выполняются из корня клонированного репозитория.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r interface_editor/requirements-release.txt -r pinkDream/requirements.txt

# Редактор: Python x64 и C++ x64
cmake -S interface_editor -B interface_editor/build -G "Visual Studio 17 2022" -A x64
cmake --build interface_editor/build --config Release
python interface_editor/app/main.py

# uExplorer
cmake -S uExplorer -B uExplorer/build -G "Visual Studio 17 2022" -A x64
cmake --build uExplorer/build --config Release
cmake --install uExplorer/build --config Release --prefix uExplorer
python uExplorer/launch.py
```

Дальнейшие инструкции:

- [Сборка всех компонентов и внешние входные данные](docs/BUILD.md).
- [UCC и ExtensionL2: настройка путей](docs/SCRIPT_TOOLS.md).
- [Clear HF: полный пример от чистого клона до установки ExtensionL2](docs/CLEAR_HF_WALKTHROUGH.md).
- [Браузер: подготовка чистой копии](gameAddWebWithD3D9/docs/PUBLICATION_BUILD.md).
- [Состав публикации и обновление](docs/PUBLICATION.md).
- [Результаты проверки этой копии](docs/VALIDATION.md).

## Что находится в репозитории

Исходники, схемы, рецепты тем, тесты, собственные примеры и документация.
UCC, игровые DLL/пакеты, извлечённые Classes, XDAT/UTX и клиентские библиотеки
изображений пользователь предоставляет локально. Генерируемые файлы исключены
через `.gitignore`. Наличие готовых архивов проверяйте в GitHub Releases;
команды выше собирают инструменты из исходников без готового релиза.

Сведения о предыдущих игровых проверках относятся к указанным в отчётах хешам.
Инструкции `docs/PUBLICATION_BUILD.md` и общая `docs/BUILD.md` описывают эту
публикационную структуру; исторические отчёты сохраняют контекст исходной разработки.

## Лицензия

Собственный код — [MIT](LICENSE), `L2Instruments contributors`.
Сторонние компоненты и атрибуция — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
