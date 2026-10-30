# DLL — ExtensionL2 и патч клиентской Core

**Публикационная копия:** внешние пути и команды —
[SCRIPT_TOOLS](../docs/SCRIPT_TOOLS.md), [BUILD](../docs/BUILD.md).
Клиентские DLL подключаются отдельно; готовые комплекты создаются локально.
Пути разработки ниже описывают исходное рабочее дерево.

Сборка в Windows и все реализованные native-функции в игре проверены на целевых
клиентах. Scryde исключён: рабочая интеграция не получена, исследования прекращены.

Рабочий каталог: `dll` относительно корня репозитория.
Пользовательские функции: **`src/extensionL2.cpp`**. Готовые комплекты: **`dist/profiles`**.
Сборка: **`build.ps1`**. Подготовка/проверка комплекта: **`prepare_extension.ps1`**.
Все команды ниже выполняются из этого каталога.

## Каталоги

| Каталог | Назначение |
|---|---|
| `src/`, `tools/`, `tests/`, `ExtensionL2/` | Исходники, инструменты и тесты |
| `dist/profiles/Clear_hf/` | Готовый Core-комплект High Five |
| `dist/profiles/Gracia_epilogue/` | Актуальный Core-комплект Gracia (бывший prepared-gracia-epilogue-v2/client) |
| `dist/profiles/client_b3fb9af3/` | Комплект другого поддерживаемого Core-профиля |
| `dist/client/`, `dist/win32/` | Общий клиентский модуль и готовые инструменты |
| `build/` | Нативная сборка CMake |
| `work/gracia/v2/` | Сохранённые workspace, bindings и тестовый bytecode актуальной подготовки Gracia |
| `work/prepared-<дата>/` | Новые подготовки через prepare_extension.ps1 по умолчанию; результат внутри client/ |
| `archive/gracia/v1/` | Предыдущая подготовка Gracia целиком, включая client и workspace |
| `reports/` | Журнал переноса и контрольные хеши |

При переносе 2026-10-30 проверено побайтовое сохранение всех 101 файлов.
Исторические абсолютные пути в bundle.json и логах отражают прежние запуски.
Журнал: `reports/layout-20261030.json`.

Для браузера используйте ExtensionL2.dll из браузерного комплекта:
Core-комплект содержит базовую версию расширения, а не браузерную.

[Справочник скриптов](SCRIPTS.md) · [Структура проекта](../README.md) ·
[Компилятор int64](../int64/README.md)

**[Файловые функции WriteTextFile/ReadTextFile](FILE_IO.md)** — UTF-8,
строковый ABI, путь относительно DLL. Готовый тест Credit находится в
**[../test_interfaces](../test_interfaces/README.md)**.

**[Профили Core и автоматическая проверка комплекта](CORE_PROFILES.md)**:
единый каталог ABI, анализ неизвестных Core, loader/VM-пробы и проверка установки.

**Текущий шаблон позволяет добавлять функции в одном файле `src/extensionL2.cpp`.**
Список L2_NATIVE используется и для регистрации, и для автоматической генерации
UC. Основная инструкция: **[ADDING_NATIVE_FUNCTIONS.md](ADDING_NATIVE_FUNCTIONS.md)**.
Сканирование native-индексов остальных модулей исключено из стандартного сценария подготовки.
Для клиента Clear HF подготовлен отдельный исправленный комплект:
**[CLEAR_HF_FIX.md](CLEAR_HF_FIX.md)**. Core.dll выбирается по версии клиента,
а не только по архитектуре x86.

Реализована **новая** функция `SaturatingAdd64(A, B)`:

```uc
native(4000) static final function int64 SaturatingAdd64(int64 A, int64 B);
```

Она складывает два signed INT64; при переполнении возвращает INT64_MAX либо
INT64_MIN. В клиенте такой функции не было. Её реализация находится в нашем
**ExtensionL2.dll**, загружаемом в процесс клиента.

## Что входит в пример

| Файл | Назначение |
|---|---|
| `src/extensionL2.cpp` | Ваши C++ функции/классы и список L2_NATIVE |
| `src/extension_api.h` | Типизированные адаптеры аргументов и результатов |
| `src/extension_runtime.cpp` | Общая инфраструктура регистрации и ABI |
| `src/client_abi.h` | Проверенный ABI x86, порядок high/low слов INT64 |
| `src/client_profile.h` | Native-индекс и профиль клиентской Core.dll |
| `src/ExtensionL2.def` | Экспорты Win32 для загрузчика |
| `ExtensionL2/Classes/ExtensionL2API.uc` | Автоматически сгенерированные native-объявления |
| `ExtensionL2/Classes/ExtensionL2Tests.uc` | Примеры вызовов и тесты |
| `tools/patch_core.py` | Создаёт модифицированную **копию** Core.dll для автозагрузки |
| `tools/audit_native_index.py` | Проверяет номер в предоставленных клиентских пакетах |
| `tools/prepare_uc.py`, `tools/check_uc.py` | Собирают/проверяют тестовый пакет через существующий ucc64 |
| `tests/extension_probe.cpp` | Выполнение вызовов через настоящую клиентскую VM |

Модуль не зависит от `editor_bridge.cpp` или MinHook. `Ucc64Bridge.dll` нужен
только при компиляции UC с типом int64. Реализация новой функции исполняется
из **ExtensionL2.dll в клиенте**.

Готовые проверенные инструменты находятся в `dist/win32`, общая DLL/UC — в
`dist/client`, а Core.dll для конкретного клиента — в `dist/profiles/<профиль>`.
Хеши и границы выполненной проверки
описаны в VALIDATION.md и JSON-манифестах рядом с файлами.

## 1. Сборка DLL и тестового EXE

Из каталога `rebuild/dll`, в Developer PowerShell for VS 2022:

```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A Win32
cmake --build build --config Release
cmake --build build --config Release --target generate_native_uc
```

Результат:

```text
build/Release/ExtensionL2.dll
build/Release/extension_probe.exe
build/Release/extension_bindings.exe
```

Требуются MSVC v143, Windows SDK и CMake 3.24+. Платформа — **Win32**, не x64.
Готовый вариант первоначально собран MinGW-w64. Сборка проекта в Windows проверена.

Альтернатива с установленным MinGW-w64 i686:

```powershell
py -3 tools/build_mingw.py
```

Эта команда создаёт `build-mingw` и BUILDINFO.json.

После C++ сборки можно автоматически подготовить UC и патченную копию клиента:

```powershell
$ClientSystem = Read-Host 'Полный путь к system целевого клиента HF'
.\prepare_extension.ps1 -ClientCore ..\..\Clear_hf\Core.dll -ClientSystem $ClientSystem
```

Скрипт использует `build/Release/ExtensionL2.dll`, генерирует объявления, компилирует
ExtensionL2.u, проверяет сигнатуры и создаёт новый каталог `prepared-<дата-время>`.
`-ClientCore` обязателен; это оригинал из выбранного клиента. Можно указать
`-NativeDll`, `-Launcher`, `-ClientSystem` и `-Destination`.
Он не устанавливает файлы в каталог игры.

## 2. Компиляция объявления и вызовов UC

```powershell
& build/Release/extension_bindings.exe build/Release/ExtensionL2.dll ExtensionL2/Classes/ExtensionL2API.uc build/bindings.json
py -3 tools/prepare_uc.py extension-workspace
py -3 ../int64/tools/run_compile.py extension-workspace/System --launcher ../int64/dist/win32/ucc64.exe
py -3 tools/check_uc.py extension-workspace/System/ExtensionL2.u --bindings-json build/bindings.json --bytecode-output extension-workspace/compiled-call.bin
```

Получится `extension-workspace/System/ExtensionL2.u`. Каталог workspace должен
быть новым. `check_uc.py` проверяет декларацию и реальный opcode вызова **6F A0**
(extended native 4000), а также преобразования аргументов в INT64.

Классы `ExtensionL2API` и `ExtensionL2Tests` намеренно **не помечены `native`**: они остаются обычными
скриптовыми классами, а функции имеют native-индексы. Для этого примера отдельная
регистрация C++ класса `UExtensionL2API` не нужна. Этот вариант проверен UCC.

В другом скрипте вызов выглядит так:

```uc
local int64 Result;
Result = class'ExtensionL2API'.static.SaturatingAdd64(5000000000, 10);
Log(string(Result)); // 5000000010
```

При сборке вызывающего пакета `ExtensionL2.u` должен находиться в его System.
Если собираете пакеты из исходников одной командой, разместите
`EditPackages=ExtensionL2` перед вызывающим пакетом в UE2Runtime.ini.
В клиенте также должен присутствовать ExtensionL2.u.

## 3. Вариант подключения A: из существующего клиентского загрузчика

Когда клиентская Core.dll уже инициализирована, а скрипты с новой функцией ещё
не загружены, выполните в коде загрузчика:

```cpp
HMODULE core = GetModuleHandleW(L"Core.dll");
HMODULE extension = LoadLibraryW(L"D:\\YourClient\\System\\ExtensionL2.dll");
using Attach = BOOL (WINAPI*)(HMODULE);
auto attach = extension
    ? reinterpret_cast<Attach>(GetProcAddress(extension, "ExtensionL2Attach"))
    : nullptr;
if (!attach || !attach(core)) {
    // Отменить запуск использующих функцию скриптов и вывести ошибку.
}
// Сохранить extension загруженным на всё время работы клиентской VM.
```

Это код точки инициализации вашего загрузчика, **не DllMain**. Экспорт
`ExtensionL2Attach` — служебная Win32-функция для подключения модуля; из UC
вызывается `SaturatingAdd64` через GNatives[4000].

Регистрация выполняется один раз, на стартовом потоке. Повторный вызов Attach
допустим. Модуль проверяет профиль Core, инициализацию таблицы и свободный слот.
Уже занятый слот не перезаписывается. DLL должна оставаться загруженной:
адрес обработчика используется GNatives и может кэшироваться в UFunction.

## 4. Вариант подключения B: модифицированная копия клиентской Core.dll

Это конкретный пример изменения клиентской DLL. Патчер поддерживает два
оригинала **клиентской** Core.dll, каждый со своим ABI-профилем:

```text
SHA256 b3fb9af30a4fc9429b6765e9d897acb00478e7ba0a1e6c48266d475bfadf0f3c
SHA256 0677e909b10ec398543dbd04cf4d8714ed97befd23d5f928aef17b1a5d844471 (Clear HF)
```

Из каталога `rebuild/dll`:

```powershell
py -3 tools/check_core_dependencies.py ../../Clear_hf --core ../../Clear_hf/Core.dll
py -3 tools/patch_core.py ../../Clear_hf/Core.dll client/Core.dll
Copy-Item build/Release/ExtensionL2.dll client/ExtensionL2.dll
py -3 ../int64/tools/package_client.py extension-workspace/System/ExtensionL2.u client/ExtensionL2.u --like ../../decompilled/client_dll/u_files/interface.u
```

Выходной Core.dll должен быть новым файлом. Оригинал не перезаписывается.
До установки результата в клиент сохраните его исходный Core.dll; восстановление
состоит в возвращении этой исходной DLL.

Для подключения в клиентский System используются три файла:

```text
Core.dll         — патченная копия именно клиентской DLL
ExtensionL2.dll  — новая реализация
ExtensionL2.u    — скриптовый класс с объявлением и примерами
```

Патчер:

1. Добавляет импорт `ExtensionL2.dll!ExtensionL2Attach`.
2. Добавляет секции `.ndcode` (RX) и `.nddata` (RW).
3. Перенаправляет PE entry point на короткую обёртку.
4. Обёртка сначала вызывает **оригинальный** entry point Core с исходными
   аргументами. После успешного DLL_PROCESS_ATTACH вызывает ExtensionL2Attach.
5. Все остальные уведомления передаются оригинальному entry point.

Исходные секции, тела функций, экспорты и адреса старых IAT остаются прежними.
Новые вызовы адресуются относительно базы модуля. Пересчитывается PE checksum.
Рядом записывается `Core.patch.json` с адресами и хешами.

В этом способе ExtensionL2.dll загружается как зависимость Core. Её DllMain
ничего не регистрирует; регистрация идёт из обёртки **после** инициализации Core.
Этот установщик не загружает другие DLL и не запускает потоки.
Если регистрация не удалась, attach Core завершается ошибкой, вместо запуска
скриптов с отсутствующим/чужим обработчиком.

## 5. Проверка на клиентской VM

`extension_probe.exe` загружает реальную Core.dll и исполняет bytecode через
`FFrame::Step`, включая extended-native диспетчер. Для автономного теста строк
он предоставляет Core небольшой тестовый allocator; клиентский ExtensionL2.dll
не меняет allocator игры.

Пример ручного подключения (все DLL-пути лучше задать абсолютными):

```powershell
$Core = (Resolve-Path ../../decompilled/client_dll/Core.dll).Path
$Extension = (Resolve-Path build/Release/ExtensionL2.dll).Path
$Deps = 'D:\YourClient\System'
$Call = (Resolve-Path extension-workspace/compiled-call.bin).Path
& build/Release/extension_probe.exe $Core $Deps $Extension manual $Call
```

Для проверки автоматического подключения укажите созданную патченную Core.dll
и режим `patched` вместо `manual`. ExtensionL2.dll должна быть доступна загрузчику;
в реальном клиенте она лежит рядом с Core.dll и EXE клиента.

Проверены в Wine x86:

- отказ от перезаписи занятого индекса;
- повторная установка без дублирования;
- автоматическая установка при загрузке патченной Core;
- вычисления с положительными/отрицательными 64-битными величинами;
- насыщение на INT64_MIN / INT64_MAX;
- вложенные вызовы новой функции;
- выполнение **фактических байтов вызова, сгенерированных UCC**, с результатом
  2147483648.

Полный игровой клиент, загрузка ExtensionL2.u и все реализованные функции
в игре проверены отдельно (кроме Scryde). Проверка хоста подтверждает
ABI/регистрацию/диспетчеризацию.

## 6. Как написать свою функцию на основе примера

1. Добавьте функцию или статический метод в `src/extensionL2.cpp`.
2. Добавьте строку `L2_NATIVE(номер, ИмяДляUC, &Функция)` в список того же файла.
3. Выполните build.ps1 — адаптеры и UC-декларации формируются автоматически.
4. Соберите ExtensionL2.u и вызывающие пакеты; обновите тестовые вызовы при
   изменении сигнатур. Полный порядок — в ADDING_NATIVE_FUNCTIONS.md.

Индекс 4000 свободен в предоставленных Core/Engine/NWindow/UWindow/Interface.u.
Это не глобально зарезервированный номер: другие расширения клиента должны
использовать другие индексы. Более поздняя регистрация другой DLL с тем же
номером может заменить обработчик; распределение индексов нужно согласовывать
для всего набора модулей.
