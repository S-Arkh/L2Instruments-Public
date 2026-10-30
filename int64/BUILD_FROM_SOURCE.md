# Исходники и самостоятельная сборка EXE, DLL и Int64Smoke.u

Каталог проекта относительно корня репозитория:

```text
int64
```

Все перечисленные ниже исходники находятся в этом каталоге. MinHook v1.3.4
также включён исходниками в `third_party/minhook`, вместе с лицензией и
`UPSTREAM.json` (версия, commit и контрольные суммы файлов). CMake использует
эту локальную копию; скачивание MinHook и Git для обычной сборки не нужны.

## 1. Какой файл из каких исходников собирается

| Результат | Основные исходники | Назначение |
|---|---|---|
| `ucc64.exe` | `src/launcher.cpp` | Проверяет комплект UCC, запускает оригинальный UCC и подключает расширение |
| `Ucc64Bridge.dll` | `src/editor_bridge.cpp`, `src/int64_semantics.h`, `src/ucc64.def`, `third_party/minhook/` | Реализует поддержку INT64 и совместимость с клиентскими объявлениями |
| `int64_semantics_test.exe` | `tests/int64_semantics_test.cpp`, `src/int64_semantics.h` | Проверяет разбор чисел, диапазон, порядок 32-битных частей и правила преобразований |
| `client_native_probe.exe` | `tests/client_native_probe.cpp`, `src/int64_semantics.h` | Проверяет настоящие native-обработчики предоставленной клиентской Core.dll |
| `Int64Smoke.u` | `smoke/Int64Smoke/Classes/*.uc` | Проверочный UnrealScript-пакет, собираемый оригинальным UCC с расширением |

Состав исходников `Int64Smoke.u`:

```text
smoke/Int64Smoke/Classes/
    Int64Probe.uc       — INT64, литералы, casts, арифметика, массивы, defaults
    FlagBase.uc         — базовый класс с NativeReplication
    FlagChild.uc        — проверка NoNativeReplication
    LocalizedProbe.uc   — проверка localized
    DynamicProbe.uc     — проверка dynamicrecompile
```

Общая конфигурация C/C++ сборки — `CMakeLists.txt`.
Исходный `UCC.exe` остаётся бинарной зависимостью: `ucc64.exe` — наш запускатель,
а расширение компилятора находится в `Ucc64Bridge.dll`.

Отдельный пример расширения **клиентского runtime** (ExtensionL2.dll,
SaturatingAdd64 и создание патченной копии Core.dll) находится в
[../dll](../dll/README.md). У него свой
CMake-проект, поскольку это модуль игры, а не компилятора.

## 2. Что установить для Visual Studio 2022

В Visual Studio Installer выберите:

- **Разработка классических приложений на C++**;
- MSVC v143, инструменты x86/x64;
- Windows 10 или Windows 11 SDK;
- средства CMake для Windows, либо отдельный CMake **3.24+**.

Для Python-инструментов и сборки `.u` нужен **Python 3.10+**, доступный через
`py -3`. Для сборки самих EXE/DLL Python не требуется.

Откройте **Developer PowerShell for VS 2022** и перейдите в корень проекта:

```powershell
# Выполняется из корня репозитория.
cd .\int64
```

Целевая платформа всех Windows EXE/DLL — **Win32/x86**, включая запускатель.
Это соответствует 32-битному UCC и клиентским DLL.

## 3. Собрать все EXE и DLL

Самый короткий вариант:

```powershell
.\build.ps1
```

Скрипт создаёт проект VS 2022 / Win32, собирает Release и запускает C++ тест.
Результаты:

```text
build/Release/ucc64.exe
build/Release/Ucc64Bridge.dll
build/Release/int64_semantics_test.exe
build/Release/client_native_probe.exe
```

Эквивалентные команды вручную:

```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A Win32
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

После первого конфигурирования можно открыть `build/UccInt64.sln` в Visual
Studio и собирать нужные проекты из IDE. Для повторной сборки после изменения
`.cpp`/`.h` достаточно `cmake --build build --config Release`.

`build/Release` — ваши новые сборки. Готовые файлы в `dist/win32` автоматически
ими не заменяются. Для запуска новой версии передавайте её путь через
`-Launcher`, как показано ниже. DLL должна находиться рядом с выбранным EXE.

### Сборка отдельной цели

```powershell
cmake --build build --config Release --target ucc64
cmake --build build --config Release --target Ucc64Bridge
cmake --build build --config Release --target int64_semantics_test
cmake --build build --config Release --target client_native_probe
```

Цель `ucc64` зависит от `Ucc64Bridge`, поэтому нужная DLL также будет собрана.

### Сборка для отладки

```powershell
.\build.ps1 -Configuration Debug
```

Файлы появятся в `build/Debug`. Можно использовать отдельный каталог генерации:

```powershell
.\build.ps1 -Configuration RelWithDebInfo -BuildDirectory build-symbols
```

Если каталог CMake раньше создавался для другой платформы/компилятора,
укажите новый `-BuildDirectory`.

## 4. Запустить EXE-проверки

Числовой тест самодостаточен:

```powershell
.\build\Release\int64_semantics_test.exe
```

Ожидается `INT64 semantics tests passed` и код 0.

`client_native_probe.exe` требует именно **клиентскую** `Core.dll` и каталог
её DLL-зависимостей. В примере замените `D:\YourClient\System` на каталог
вашего установленного клиента:

```powershell
$ClientCore = (Resolve-Path ..\decompilled\client_dll\Core.dll).Path
$ClientSystem = 'D:\YourClient\System'
& .\build\Release\client_native_probe.exe $ClientCore $ClientSystem
```

Probe печатает `PASS` для выполненных проверок. Он проверяет отдельные
обработчики DLL; весь игровой клиент и Interface.u этим EXE не запускаются.
`ctest` автоматически запускает только самодостаточный `int64_semantics_test`.

## 5. Собрать Int64Smoke.u из его исходников

Редактируйте файлы в **`smoke/Int64Smoke/Classes`**. Оригинальные бинарники и
базовые Core-исходники уже скопированы в **`rebuild/int64/compiler`**. Для проверки профиля нужна
предоставленная клиентская `Core.dll` в `int64_UCC/decompilled/client_dll`.

После C++ сборки выполните:

```powershell
.\build_smoke.ps1 -Destination smoke-from-source
```

По умолчанию скрипт использует **`build/Release/ucc64.exe`** и соседнюю новую DLL.
Он копирует текущие UC в новый изолированный каталог, запускает UCC и проверяет
байткод и defaults. Результат:

```text
smoke-from-source/System/Int64Smoke.u
smoke-from-source/compile.log
```

Повторный запуск требует нового каталога, например `smoke-from-source-2`.
Без `-Destination` скрипт создаёт уникальный каталог `smoke-build-<дата-время>`.
Это гарантирует пересборку текущих UC, а не использование старого пакета UCC.

Для Debug или готового дистрибутива путь задаётся явно:

```powershell
.\build_smoke.ps1 -Launcher .\build\Debug\ucc64.exe
.\build_smoke.ps1 -Launcher .\dist\win32\ucc64.exe
```

Команды вручную, с теми же действиями:

```powershell
py -3 tools/prepare_smoke.py smoke-manual
py -3 tools/run_compile.py smoke-manual/System --launcher build/Release/ucc64.exe
py -3 tools/check_smoke.py smoke-manual/System/Int64Smoke.u
```

`Int64Smoke.u` — результат компиляции UnrealScript, поэтому он не создаётся
одной C++ целью CMake. Правки тестов могут потребовать соответствующих правок
ожидаемых результатов в `tools/check_smoke.py`.

## 6. Проверить изменения расширения на интерфейсе

Чтобы сборка интерфейса использовала именно ваши новые EXE/DLL:

```powershell
.\build_interface.ps1 -Launcher .\build\Release\ucc64.exe
```

Полный набор положительных и отрицательных тестов компилятора:

```powershell
py -3 tools/run_smoke.py regression-from-source --launcher build/Release/ucc64.exe
```

Для `regression-from-source` тоже нужен новый каталог. Существующие исходники
интерфейса в workspace не перезаписываются. Основная инструкция по ним —
[CLIENT_BUILD.md](CLIENT_BUILD.md).

## 7. Альтернативная сборка MinGW-w64

Готовые файлы `dist/win32` первоначально собирались MinGW-w64 и проверялись
в Wine x86. Сборка проекта в Windows также проверена; загрузка пакетов и все
реализованные функции проверены в целевом игровом клиенте, кроме Scryde.

При наличии MinGW-w64 **i686** в PATH:

```powershell
py -3 tools/build_mingw.py --out build-mingw
```

Если имена компиляторов отличаются:

```powershell
py -3 tools/build_mingw.py --cc i686-w64-mingw32-gcc --cxx i686-w64-mingw32-g++ --out build-mingw
```

Скрипт использует локальный `third_party/minhook`, проверяет его upstream-хеши
и создаёт те же четыре файла плюс `BUILDINFO.json` и копию лицензии MinHook.
Для пробной сборки удобно указывать отдельный `--out`, чтобы сохранить
текущие готовые файлы `dist/win32`.

## 8. Что сохранить на будущее

Для EXE/DLL компилятора сохраните весь `rebuild/int64`, особенно `src`, C++ файлы из `tests`,
`third_party/minhook`, `CMakeLists.txt`, `build.ps1` и эту инструкцию.

Для повторной сборки `.u` дополнительно сохраните:

- `smoke`, `tools` и скрипты `build_smoke.ps1` / `build_interface.ps1`;
- `workspace` с вашими изменёнными UC и `sdk/runtime2226`;
- локальный комплект `rebuild/int64/compiler` с оригинальными UCC.exe и DLL;
- предоставленные клиентские DLL и пакеты в `int64_UCC/decompilled/client_dll`.

Смещения ABI в `src/editor_bridge.cpp` и проверки в `tools/verify_profile.py`
относятся к конкретным исходным бинарникам UCC/Core/Editor. При изменении
самого расширения EXE/DLL пересобираются из перечисленных исходников; при
замене версии оригинального компилятора потребуется также пересмотр ABI-профиля.
