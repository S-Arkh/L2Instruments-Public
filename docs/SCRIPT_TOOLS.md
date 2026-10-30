# L2 Script Tools

Инструменты работы с UnrealScript и native-расширениями клиента Lineage II:

- `int64/`: launcher `ucc64.exe`, bridge `Ucc64Bridge.dll`, обработка `INT64`,
  чтение пакетов, извлечение сохранённого ScriptText и подготовка SDK.
- `dll/`: `ExtensionL2.dll`, генерация UC-объявлений, профили Core, патчер и
  проверка совместимости комплекта.

Оба компонента предназначены для **Windows x86**. Название `ucc64` относится
к поддержке 64-битных чисел; launcher запускает внешний оригинальный UCC.
Извлечение ScriptText работает только для пакетов, где исходники сохранены.

## Сборка

Нужны Python 3.12, CMake 3.24+ и Visual Studio 2022 с C++ tools.
Команды из корня репозитория:

```powershell
cmake -S int64 -B int64/build -G "Visual Studio 17 2022" -A Win32
cmake --build int64/build --config Release
ctest --test-dir int64/build -C Release --output-on-failure
cmake -S dll -B dll/build -G "Visual Studio 17 2022" -A Win32
cmake --build dll/build --config Release
cmake --build dll/build --config Release --target generate_native_uc
```

Результаты находятся в `int64/build/Release` и `dll/build/Release`.
При использовании этих сборок передавайте `-Launcher` явно в сценарии подготовки.
Сборка исходного C++ не требует клиентских библиотек. Для компиляции UC нужны
внешние UCC/SDK и подходящая клиентская Core.

## Внешние входные данные

Пути задаются переменными окружения до запуска Python/PowerShell:

| Переменная | Содержимое |
|---|---|
| `L2_COMPILER_SYSTEM` | System оригинального компилятора: UCC.exe, Editor.dll, Core.dll; рядом каталог Core |
| `L2_CLIENT_SYSTEM` | System целевого клиента |
| `L2_CLIENT_CORE` | Оригинальная Core.dll; по умолчанию из L2_CLIENT_SYSTEM |
| `L2_CLIENT_PACKAGES` | Каталог Core.u, Engine.u, NWindow.u, Interface.u |
| `L2_INTERFACE_CLASSES` | Внешний каталог исходников Interface/Classes |
| `L2_RUNTIME_SDK` | Импортированный SDK с manifest.json и System |
| `L2_CLEAR_HF_SYSTEM` | Отдельный эталон Clear HF для двухпрофильных интеграционных тестов |

Значения по умолчанию описаны в `int64/tools/local_paths.py`; относительные
пути разрешаются от текущего рабочего каталога. Для сценариев PowerShell
удобнее задавать абсолютные пути.

`int64/tools/import_compiler.py` и `import_runtime_sdk.py` импортируют локальные
входные данные; параметры доступны через `--help`. `verify_profile.py` проверяет
известный ABI и хеши. Неизвестная Core анализируется как кандидат, но не
добавляется в разрешённые профили автоматически.

### Импорт компилятора и runtime SDK

Из корня репозитория в активированной Python 3.12 `.venv`:

```powershell
$CompilerSource = Read-Host 'Абсолютный путь к оригинальному компилятору (с System и Core)'
$RuntimeInstaller = Read-Host 'Абсолютный путь к UE2Runtime-22261903.exe'
python int64/tools/import_compiler.py $CompilerSource --destination int64/compiler
if ($LASTEXITCODE) { throw 'Compiler import failed' }
python int64/tools/import_runtime_sdk.py $RuntimeInstaller int64/sdk/runtime2226
if ($LASTEXITCODE) { throw 'Runtime SDK import failed' }
$env:L2_COMPILER_SYSTEM = (Resolve-Path int64/compiler/System).Path
$env:L2_RUNTIME_SDK = (Resolve-Path int64/sdk/runtime2226).Path
```

Каталоги назначения должны быть новыми. Импорт не скачивает входы и не запускает
установщик. `import_compiler.py` ожидает `System/{UCC.exe,Core.dll,Editor.dll,Engine.dll}`
и `Core/Classes/Object.uc`; также копирует остальные имеющиеся `.exe/.dll/.u/.int/.ini`
из System. Предоставьте полный рабочий System с зависимостями UCC.
`import_runtime_sdk.py` создаёт отдельные `manifest.json` и `System` с пакетами
`Core.u`, `Engine.u`, `Editor.u`, `License.int`; он не заменяет импорт компилятора.

Поддерживаемый runtime installer — **UE2 Runtime 2226.19.03**.
Ожидаемые контрольные суммы (другие версии нельзя подставлять по одному имени):

| Вход | Алгоритм | Ожидаемый хеш |
|---|---|---|
| `UE2Runtime-22261903.exe` | SHA-1 | `2356fafdf7dd77b3f74f766f28dcd451849dfb9b` |
| Компилятор `UCC.exe` | SHA-256 | `c68ba1ce0eab03af23b04dc1c991c3f1cc047a8a2076c6850e3071892806fb65` |
| Компилятор `Core.dll` | SHA-256 | `5bff274734cae994353a8c60f4bfe1087dbdd9aa3883c7b2a7eff6ea2f51dc7e` |
| Компилятор `Editor.dll` | SHA-256 | `d64995c1282956c6e9d67dd70715a69b5101331aa727a2d44b03e25fd7f2cd2e` |
| Компилятор `Engine.dll` | SHA-256 | `a89b7c00697808861c9c86b003014d4c7f4a732ecf476440b4c187c880a710b6` |

Источник истины: `int64/tools/verify_profile.py` (`HASHES`) и
`int64/tools/import_runtime_sdk.py` (`ARCHIVE_SHA1`, `ENGINE_HASH`, URL источника).
Клиентская Core — другой файл; её утверждённые профили находятся в
`dll/core_profiles.json`. Полный пример настройки и установки:
[Clear HF walkthrough](CLEAR_HF_WALKTHROUGH.md).

```powershell
$env:L2_COMPILER_SYSTEM = 'C:\LocalInputs\compiler\System'
$env:L2_CLIENT_CORE = 'C:\LocalInputs\client\System\Core.dll'
python int64/tools/verify_profile.py
# После настройки SDK, пакетов и Classes:
./int64/build_interface.ps1 -Workspace C:\Build\Interface `
  -Launcher ./int64/build/Release/ucc64.exe `
  -ReferencePackage C:\LocalInputs\client\System\Interface.u
```

Для подготовки DLL-комплекта используйте `dll/prepare_extension.ps1` с
`-ClientCore`, `-ClientSystem`, `-Launcher` и при необходимости `-ReferencePackage`.
Функции и native-индексы объявляются в `dll/src/extensionL2.cpp` через `L2_NATIVE`.
Проверки комплекта находятся в `dll/tools/validate_bundle.py` и
`dll/tools/check_installation.py`; параметры — через `--help`.

## Тесты

Без игровых данных:

```sh
python -B -m unittest discover -s int64/tests -v
python -B -m unittest discover -s dll/tests -v
```

Для интеграционных проверок задайте `L2_INTEGRATION=1` и пути из таблицы.
Эти тесты проверяют конкретные эталоны (хеши и ABI), а не произвольный клиент.
Loader/VM-проверка отдельно включается через `EXTENSION_TEST_TOOLS`,
`EXTENSION_TEST_PACKAGE`, `EXTENSION_TEST_BYTECODE`; под Wine также
`EXTENSION_TEST_WINE`.

Результаты текущей проверки: [VALIDATION.md](VALIDATION.md).

## Лицензия и публикация

Собственный код — MIT, `L2Instruments contributors`. Сторонние уведомления:
корневой `THIRD_PARTY_NOTICES.md`. UCC, SDK, клиентские DLL и извлечённые игровые исходники
предоставляются отдельно. Бинарные комплекты предназначены для GitHub Releases.
