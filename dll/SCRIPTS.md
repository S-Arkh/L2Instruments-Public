# Скрипты DLL

Все команды выполняются из **`rebuild/dll`**. Python: `py -3` в Windows,
`python3` в Linux. `--help` показывает параметры CLI.
Компилятор и парсеры пакетов находятся в соседнем `../int64`;
Python-инструменты находят их относительно собственного файла.

## Сборка и подготовка

| Скрипт | Аргументы | Результат / изменения |
|---|---|---|
| `build.ps1` | `-Configuration` = Release, также Debug/RelWithDebInfo | CMake/VS2022 Win32: DLL и EXE в build; генерирует client_profile.h, ExtensionL2/Classes/ExtensionL2API.uc и build/bindings.json. |
| `prepare_extension.ps1` | Обязательный `-ClientCore`; `-ClientSystem` по умолчанию родитель Core; `-NativeDll` = build/Release/ExtensionL2.dll; `-Launcher` = ../int64/dist/win32/ucc64.exe; `-Destination` = новый prepared с датой | Проверка импортов, генерация UC (перезаписывает API проекта), новый workspace, компиляция/проверка UC, патч, упаковка, loader/VM-пробы. Результат в destination/client, manifest — только после успеха. |
| `tools/build_mingw.py` | `--cxx` = i686-w64-mingw32-g++; `--out` = build-mingw | Перегенерирует профиль C++, обновляет DLL, extension_probe.exe, extension_bindings.exe, client_link_probe.exe, BUILDINFO.json. Сам UC не генерирует. |
| `tools/prepare_uc.py` | `destination` | Новый изолированный workspace с текущими ExtensionL2/Classes, compiler и INI. |
| `tools/check_uc.py` | `package`, `--bindings-json JSON`, `--bytecode-output FILE` | Читает/проверяет API и тесты UC; опционально записывает байткод в новый файл для VM-probe. |

```powershell
.\build.ps1
$ClientSystem = Read-Host 'Полный путь к system целевого клиента HF (используется далее)'
.\prepare_extension.ps1 -Destination prepared-new -ClientCore ..\..\Clear_hf\Core.dll -ClientSystem $ClientSystem
```

Рядом с NativeDll нужны свежие extension_bindings.exe, extension_probe.exe,
client_link_probe.exe. Путь ClientCore — оригинальный, не уже патченный файл.
Подготовка не копирует результат в игру. Каталог назначения должен быть новым.

Ручная подготовка UC после генерации API:

```powershell
py -3 tools/prepare_uc.py uc-new
py -3 ../int64/tools/run_compile.py uc-new/System --launcher ../int64/dist/win32/ucc64.exe
py -3 tools/check_uc.py uc-new/System/ExtensionL2.u --bindings-json build/bindings.json --bytecode-output uc-new/compiled-call.bin
```

## Core, профили и проверка установки

| Скрипт | Аргументы | Результат / изменения |
|---|---|---|
| `tools/core_profiles.py` | `generate [--check]` либо `analyze core [--report JSON]` | Генерация src/client_profile.h из core_profiles.json; --check только сверяет. Анализ пишет отчёт-кандидат, но не одобряет профиль и не меняет Core. |
| `tools/patch_core.py` | `source output` | Проверяет известный оригинал и ABI, создаёт новую Core и .patch.json. Выход не должен существовать. Исходные секции и экспорты сохраняются. |
| `tools/check_core_dependencies.py` | `system --core DLL`, `--report JSON` | Проверяет обычные PE-импорты Core у EXE/DLL. Читает клиент, выводит JSON/перезаписывает указанный отчёт. Не проверяет native-индексы. |
| `tools/validate_bundle.py` | `original bundle --system DIR --tools DIR --bytecode FILE`, `--wine EXE` | Проверяет готовые файлы и запускает изолированные loader/VM-пробы на оригинале и патче. Пишет bundle/validation/*.log; при успехе — новый bundle/bundle.json. Существующий manifest не заменяет. |
| `tools/check_installation.py` | `system --manifest JSON`, `--report JSON` | Сверяет установленные файлы с manifest; отдельно проверяет стандартное расположение ресурсов. Ничего не устанавливает; пишет только заданный отчёт. |
| `tools/audit_native_index.py` | `--index` = 4000, диапазон 256..4095 | Необязательная проверка объявлений в фиксированных пакетах ../../decompilled/client_dll; только консоль. Не сканирует все модули и не входит в стандартную подготовку. |

```powershell
py -3 tools/core_profiles.py analyze "D:\OtherClient\system\Core.dll" --report candidate.json
py -3 tools/check_core_dependencies.py $ClientSystem --core ../../Clear_hf/Core.dll
py -3 tools/check_installation.py $ClientSystem --manifest prepared-new/client/bundle.json
```

check_installation возвращает код 1 при несовпадении/отсутствии перечисленных
файлов. Предупреждение о ресурсах отдельно: пользовательские Paths в INI не
декодируются. Manifest не является цифровой подписью или проверкой полной игры.

## Тесты

```powershell
py -3 tools/core_profiles.py generate --check
py -3 -m unittest discover -s tests -p "test_*.py"
```

- `tests/test_patch_core.py`: сохранность секций/экспортов, профили, несовместимые импорты.
- `tests/test_profile_workflow.py`: синхронизация каталога, неизвестная Core,
  неверные ABI-данные, хеши/ресурсы установки и опциональная реальная интеграция.

Для интеграционного теста задаются EXTENSION_TEST_TOOLS (свежие EXE/DLL),
EXTENSION_TEST_BYTECODE (compiled-call.bin), на Linux также EXTENSION_TEST_WINE.
Используется локальный эталон ../../Clear_hf. Зависимости копируются во временный
каталог; установленная игра не изменяется. Без переменных интеграция пропускается.

При изменении API `EXTENSION_TEST_PACKAGE` указывает на соответствующий ExtensionL2.u.
`validate_bundle.py --file-bytecode FILE` дополнительно выполняет извлечённый
из Credit вызов WriteTextFile с ожидаемым результатом test.txt.

Инструкции: [функции C++](ADDING_NATIVE_FUNCTIONS.md),
[файловый API](FILE_IO.md), [сборка тестового Interface](../test_interfaces/README.md),
[профили и полная цепочка](CORE_PROFILES.md), [Clear HF](CLEAR_HF_FIX.md).
Инструменты `.u`/UCC: [отдельный справочник](../int64/docs/SCRIPTS.md).
