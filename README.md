# L2Instruments

Инструменты для исследования и модификации клиента Lineage II / Unreal Engine 2:
редактор интерфейса, просмотр и восстановление UnrealScript, расширение UCC,
native API, встроенный браузер и генератор тем.

## Быстрый старт: готовые приложения

**Interface Editor** и **uExplorer** поддерживают автономные Windows x64-пакеты:
Python и Qt уже включены. Скачайте ZIP нужного компонента из раздела **Releases**,
распакуйте его и запустите `Start.cmd`.

Для собственной сборки по необходимости откройте **Actions**, выберите
**Release Interface Editor** или **Release uExplorer**, нажмите **Run workflow**
и задайте версию и признак предварительного релиза. После успешных тестов
workflow публикует ZIP и `SHA256SUMS.txt`. Новые workflows становятся доступны
для ручного запуска после их включения в основную ветку.

## Компоненты

| Компонент | Назначение | Платформа |
|---|---|---|
| [int64](int64/) | UCC launcher/bridge: INT64, профильные расширения UnrealScript, SDK и portable-запуск компиляции | Windows x86 |
| [dll](dll/) | ExtensionL2, native API, профили Core и проверка комплектов | Windows x86 |
| [interface_editor](interface_editor/) | Редактор XDAT, раздельные схемы с ленивой загрузкой, preview, DAT/SysString и UTX | Windows x64; Linux |
| [uExplorer](uExplorer/) | GUI/CLI для `.u`, извлечение ScriptText, восстановление UnrealScript и проверка метаданных | Windows x64; ядро и тесты также Linux |
| [gameAddWebWithD3D9](gameAddWebWithD3D9/) | WebView2 в интерфейсе HF/Gracia, адаптеры и исследования | Windows x86 |
| [pinkDream](pinkDream/) | Генерация тем, импорт текстур, установка и откат | Python |
| [test_interfaces](test_interfaces/) | Профильная подготовка, компиляция и упаковка тестовых Interface, проверка клиентских отчётов | Windows x86 |
| [InfoOfDll](InfoOfDll/) | Справочник исследованных DLL и ABI | Документация |

`ucc64` означает поддержку 64-битных чисел: это **не x64-компилятор**.
Профили относятся к конкретным хешам и ABI клиента, а не ко всем сборкам хроник.

## Текущий статус

- **Interface Editor:** редактирование XDAT и JSON roundtrip, Undo/Redo,
  сравнение деревьев, preview, текстуры и таблицы строк; встроены legacy- и
  modern-профили схем. [Возможности и ограничения](interface_editor/README.md).
- **uExplorer и UCC:** восстановление исходников, INT64, client Sort,
  профильные enum и native PtrProperty сопровождаются положительными,
  отрицательными и roundtrip-проверками.
  [Покрытие и поставка](docs/ROUNDTRIP_RELEASE.md).
- **Полный Interface:** в отчётах подтверждены адаптированные SDK-сборки
  Gracia, High Five, Японии и Кореи. Для первых двух использован сохранённый
  ScriptText, для последних двух — восстановление байткода. Успешная компиляция
  отделена от проверки в игре; различия метаданных modern-профилей сохранены
  в результатах. [Статус и границы проверки](docs/FULL_PACKAGE_REPAIR.md).
- **WebView2:** рабочие профили основной ветки — High Five и Gracia.
  Native-сборка без клиента и полный устанавливаемый UI-комплект — разные этапы.
  [Подготовка и сборка](gameAddWebWithD3D9/docs/PUBLICATION_BUILD.md).
- **Scryde:** подтверждён pinkDream; другие интеграции не подтверждены.

CI собирает native-компоненты, запускает автономные тесты и проверяет portable
пакеты обоих настольных приложений. Проверки с игровыми клиентами и внешним SDK
выполняются отдельно. Исторические результаты привязаны к хешам проверенных
артефактов и не заменяют проверку новой сборки.

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

## Сборка приложений из исходников

Нужны Python 3.12, CMake 3.24+, для Windows — Visual Studio 2022 с C++ tools
и Windows SDK. Команды ниже выполняются из корня клонированного репозитория.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r interface_editor/requirements-release.txt -r pinkDream/requirements.txt
$Python = (Get-Command python).Source

# Редактор: Python x64 и C++ x64
cmake -S interface_editor -B interface_editor/build -G "Visual Studio 17 2022" -A x64 "-DPython_EXECUTABLE=$Python"
cmake --build interface_editor/build --config Release
python interface_editor/app/main.py

# uExplorer
cmake -S uExplorer -B uExplorer/build -G "Visual Studio 17 2022" -A x64 "-DPython_EXECUTABLE=$Python"
cmake --build uExplorer/build --config Release
cmake --install uExplorer/build --config Release --prefix uExplorer
python uExplorer/launch.py
```

Дальнейшие инструкции:

- [Сборка всех компонентов и внешние входные данные](docs/BUILD.md).
- [Итоговый аудит script tools, snapshot-регрессия и комплекты поставки](docs/ROUNDTRIP_RELEASE.md).
- [UCC и ExtensionL2: настройка путей](docs/SCRIPT_TOOLS.md).
- [Portable-компилятор и выбор клиентского профиля](int64/docs/COMPILER_BUNDLE.md).
- [Профильный конвейер тестовых Interface](test_interfaces/PROFILE_PIPELINE.md).
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

Публикуемые исходники и архивы проверяются на секреты и персональные метаданные.
Лицензии и обязательная атрибуция сторонних компонентов сохраняются.

## Лицензия

Собственный код — [MIT](LICENSE), `L2Instruments contributors`.
Сторонние компоненты и атрибуция — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
