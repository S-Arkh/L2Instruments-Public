# Скрипты int64, UCC и пакетов UnrealScript

Команды выполняются из **`rebuild/int64`**. В Windows используется `py -3`,
в Linux — `python3`. Пути с пробелами заключайте в кавычки.
Скрипты DLL вынесены в отдельный [справочник](../../dll/SCRIPTS.md).

## Сборка и компиляция

| Скрипт | Аргументы | Результат / изменения |
|---|---|---|
| `build.ps1` | `-Configuration` = Release (также Debug/RelWithDebInfo/MinSizeRel), `-BuildDirectory` = build | VS2022 Win32/CMake: launcher, Bridge, C++-тесты; выполняет CTest. Обновляет каталог сборки. |
| `build_interface.ps1` | `-Workspace` = workspace, `-Launcher` = dist/win32/ucc64.exe | При необходимости создаёт workspace; пересобирает Interface и обновляет `dist/client/Interface.u`, отчёт и `plain/Interface.u`. |
| `build_smoke.ps1` | `-Destination` = новое имя smoke-build с датой, `-Launcher` = build/Release/ucc64.exe | Новый workspace, компиляция и проверка Int64Smoke.u. Рядом с launcher нужен Bridge. |
| `tools/build_mingw.py` | `--cc`, `--cxx` = i686-w64-mingw32-gcc/g++; `--minhook-source` = third_party/minhook; `--out` = dist/win32 | Обновляет EXE/DLL, obj, лицензию MinHook, BUILDINFO.json. Проверяет цель x86 и локальный MinHook. |
| `tools/run_compile.py` | `system --launcher EXE`, `--wine EXE`, `--rebuild-interface` | Запускает make -NoBind -Silent, перезаписывает `compile.log` рядом с System. Пересборка Interface сохраняет старый пакет в Backups, затем удаляет рабочую копию; требует source-preparation.json. |
| `tools/package_client.py` | `source output --like reference`, `--replace` | Создаёт клиентскую оболочку Ver111 и `.package.json`. Существующий выход заменяется только с --replace и резервной копией в Backups. |

```powershell
.\build.ps1
.\build_interface.ps1
py -3 tools/run_compile.py workspace/System --launcher dist/win32/ucc64.exe --rebuild-interface
py -3 tools/package_client.py workspace/System/Interface.u dist/client/Interface.u --like ../../decompilled/client_dll/u_files/interface.u --replace
```

Сборка C++ требует VS2022/CMake Win32 либо MinGW-w64 i686. Для исполнения
Windows-бинарников в Linux нужен Wine x86. Компилятор находится в `compiler/System`.

## Чтение .u и извлечение Classes

| Скрипт | Аргументы | Результат / изменения |
|---|---|---|
| `tools/ue2package.py` | `package`, повторяемый `--function Class.Function`, `--export Object.Path` | Читает UE2-пакет, выводит JSON, инструкции функций или байты экспорта. Ничего не записывает. --export не является каталогом выгрузки. |
| `tools/extract_sources.py` | `package destination` | Новый каталог `destination/Classes/*.uc` и extraction.json. Извлекает сохранённый ScriptText/TextBuffer, а не декомпилирует отсутствующие исходники. |
| `tools/compare_interface.py` | `original rebuilt`, `--report JSON`, `--require-equivalent` | Сравнение декодированных инструкций по символическим ссылкам и переходам, с поддержанным folding byte-констант. Пакеты только читает, отчёт записывает/заменяет. |

```powershell
py -3 tools/ue2package.py ../../decompilled/client_dll/u_files/interface.u --function CalculatorWnd.Calc
py -3 tools/extract_sources.py ../../decompilled/client_dll/u_files/interface.u extracted-interface
py -3 tools/compare_interface.py ../../decompilled/client_dll/u_files/interface.u workspace/System/Interface.u --report workspace/interface-comparison.json --require-equivalent
```

`extract_sources.py` требует новый каталог. Изучайте `missing` и `rejected` в
отчёте: завершение команды не означает наличия исходников всех классов.
Библиотечная функция `extract(package_path, class_dir)` допускает существующий
каталог и заменяет соответствующие UC; это используется при подготовке workspace.
Парсер поддерживает реализованные версии 123/37, 126/0 и оболочки Ver111;
он не является универсальным декриптором пакетов любых клиентов.

## Подготовка SDK и рабочих каталогов

| Скрипт | Аргументы | Результат / изменения |
|---|---|---|
| `tools/import_compiler.py` | `source`, `--destination` = compiler | Проверяет и копирует оригинальные System/Core в новый каталог; создаёт manifest.json. Источник не меняет. |
| `tools/import_runtime_sdk.py` | `installer destination` | Проверяет хеш UE2Runtime-22261903.exe, читает как архив без запуска; создаёт новый SDK с Core.u/Engine.u/Editor.u/License.int и manifest.json. |
| `tools/verify_profile.py` | Без аргументов | Проверяет локальные бинарники и ABI; JSON в консоли. Содержит PE-reader для других инструментов. |
| `tools/prepare_interface.py` | `destination`, `--runtime-sdk` = sdk/runtime2226 | Новый workspace: compiler SDK, Core/NWindow/Interface, ClientReference/Engine, ресурсы, INI, source-preparation.json. Нормализует рабочие копии исходников. |
| `tools/prepare_smoke.py` | `destination` | Новый изолированный compiler workspace с Int64Smoke и INI. |

```powershell
$CompilerSource = Read-Host 'Полный путь к исходному комплекту UCC'
$SdkInstaller = Read-Host 'Полный путь к скачанному UE2Runtime-22261903.exe'
py -3 tools/import_compiler.py $CompilerSource --destination compiler-new
py -3 tools/import_runtime_sdk.py $SdkInstaller sdk/runtime-new
py -3 tools/verify_profile.py
py -3 tools/prepare_interface.py workspace-new --runtime-sdk sdk/runtime2226
```

Подготовка Interface использует эталоны `../../decompilled/client_dll`, включая
`u_files/interface/Classes`. Это конкретный профиль, не универсальный импорт клиента.
Нестандартные compiler-new/runtime-new не становятся автоматически значениями
по умолчанию остальных инструментов. Для подготовки выбирайте новые каталоги.

## Проверки int64

| Скрипт | Аргументы | Результат |
|---|---|---|
| `tools/check_smoke.py` | `package` | Читает и проверяет байткод/defaultproperties Int64Smoke.u. |
| `tools/run_smoke.py` | `destination --launcher EXE`, `--wine EXE`, повторяемый `--case NAME` | Новый каталог с workspace и логом каждого положительного/отрицательного сценария. |

Сценарии `--case`: positive, overflow_positive, overflow_negative,
implicit_narrowing, out_widening, unrelated_struct, bad_default. Без параметра — все.
Ожидаемый отказ UCC считается успешным отрицательным тестом только при проверке диагностики.

```powershell
.\build_smoke.ps1 -Destination smoke-new -Launcher .\dist\win32\ucc64.exe
py -3 tools/check_smoke.py smoke-new/System/Int64Smoke.u
py -3 tools/run_smoke.py regression-new --launcher dist/win32/ucc64.exe
py -3 -m unittest discover -s tests -p "test_*.py"
```

Python-тесты: `tests/test_profile.py` (ABI/бинарники), `tests/test_packages.py`
(пакеты), `tests/test_sources_and_comparison.py` (ScriptText/сравнение),
`tests/test_uc_declarations.py` (нормализация), `tests/test_sdk_enums.py`
(enum), `tests/test_texture_assets.py` (ресурсы). Части тестов нужны локальные
эталоны; временные выходы создаются отдельно от установленной игры.

## Внутренние модули без CLI

| Модуль | Назначение и запись файлов |
|---|---|
| `tools/compilation_sdk.py` | native_storage/object_with_runtime_storage: согласует native-поля Object со старым runtime; преобразует текст в памяти. |
| `tools/sdk_enums.py` | enum_members/augment: перенос enum-метаданных; augment записывает выходной пакет. |
| `tools/texture_assets.py` | Чтение текстур, восстановление поддержанных PCX/TGA; recover_imports создаёт/записывает ресурсы в назначение. |
| `tools/uc_declarations.py` | tokens/normalize/strip_constructive — операции с текстом; normalize_file может перезаписать переданный UC. |

Большинство CLI имеют `--help`; verify_profile.py и внутренние модули — исключения.
Подробные сценарии: [сборка C++](../BUILD_FROM_SOURCE.md),
[Interface](../CLIENT_BUILD.md). [Общая структура](../../README.md).
