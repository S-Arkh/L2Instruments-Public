# Сборка клиентского Interface с INT64

## Результат

Полный Interface собран из **исходного ScriptText**, сохранённого в клиентском
пакете: 253 класса, 3792 функции, 0 ошибок, 35 предупреждений.
Предупреждения — устаревшие размеры строк, имена классов с цифрой на конце
и неиспользуемые локальные переменные исходного кода.

В исходных пакетах найдены и извлечены 309 классов Engine, 113 NWindow и
253 Interface. Это исходники с комментариями и корректными операторами,
а не текст с UnknownFunctionNNN. Исходная ANSI/UTF-16 кодировка сохраняется.

## Где работать

```text
workspace/Interface/Classes/     — редактируемые исходники интерфейса
workspace/nwindow/Classes/      — объявления и скрипты API клиента
workspace/Core/Classes/         — Core для компилятора
workspace/ClientReference/      — исходники/текстуры Engine для исследования
workspace/System/              — изолированный комплект UCC и SDK-пакеты
workspace/source-preparation.json — происхождение и преобразования файлов
compiler/System/               — локальная исходная копия UCC.exe и его DLL
compiler/Core/Classes/         — исходники Core для подготовки сборок

dist/win32/ucc64.exe + Ucc64Bridge.dll — проверенная x86 сборка расширения
dist/client/Interface.u         — результат в оболочке Lineage2Ver111
dist/client/plain/Interface.u   — тот же пакет без оболочки
```

**Для клиента предназначен итоговый Interface.u.** Core/Engine/Editor/NWindow
в workspace/System — зависимости компилятора, а клиент использует свои исходные
базовые пакеты и DLL. Нативная память старого компилятора и клиента отличается.

Исходные пользовательские файлы в compiller и client_dll не перезаписываются.
Правки для последующих сборок делайте в workspace/Interface/Classes.
Подготовка новых workspace использует локальный `rebuild/int64/compiler`; контрольные
суммы скопированного оригинального комплекта — в `compiler/manifest.json`.

## Повторная сборка в Windows

В PowerShell из каталога rebuild/int64:

```powershell
./build_interface.ps1
```

Нужен Python 3.10+. Готовые exe/dll уже находятся в dist/win32; Visual Studio
нужна только для пересборки самого расширения (`./build.ps1`). Готовые PE32
собраны MinGW-w64 и проверены в Wine x86. Сборка проекта в Windows также проверена.
Подробная инструкция и расположение исходников всех EXE/DLL и Int64Smoke.u —
[BUILD_FROM_SOURCE.md](BUILD_FROM_SOURCE.md).

Использовать заново собранное расширение можно явно:

```powershell
./build_interface.ps1 -Launcher ./build/Release/ucc64.exe
```

Скрипт сохраняет предыдущий Interface.u в workspace/Backups, принудительно
пересобирает интерфейс и формирует dist/client/Interface.u. Уже существующие
исходники workspace повторно не извлекаются. Лог — workspace/compile.log.
`-Silent` автоматически отвечает на вопрос UCC об обновлении вспомогательных
C++ заголовков в сборочном каталоге.

Вручную:

```powershell
py -3 tools/run_compile.py workspace/System --launcher dist/win32/ucc64.exe --rebuild-interface
py -3 tools/package_client.py workspace/System/Interface.u dist/client/Interface.u --like ../../decompilled/client_dll/u_files/interface.u --replace
```

Обёртка повторяет формат исходного interface.u. Версия данных остаётся
**126/0**, которую записывает UCC; исходный клиентский пакет имеет 123/37.
Инструмент упаковки меняет только внешнюю оболочку/XOR, сохраняя payload.
Загрузка нового пакета целиком и работа реализованных функций в целевом игровом
клиенте проверены; Scryde в подтверждённые интеграции не входит.

## Проверка результата

```powershell
py -3 tools/compare_interface.py ../../decompilled/client_dll/u_files/interface.u workspace/System/Interface.u --report workspace/interface-comparison.json
```

Для неизменённых восстановленных исходников получено:

- совпадают множества импортов и экспортов, суперклассы и class flags;
- совпадают метаданные функций и все 10 состояний;
- отсутствующих/лишних функций нет;
- все 3792 функции декодируются до точного конца сериализованного тела;
- у 3716 совпадают нормализованные инструкции;
- у 76 отличие сводится к безопасному сворачиванию преобразований byte-констант
  (`byte(255)`, `byte(255.0)`, `int(byte(255))`) и соответствующим адресам переходов;
- после этих явно заданных правил сравнения различий не осталось.

Это проверка инструкций и основных метаданных, не доказательство эквивалентности
всех сериализованных defaults и не замена теста в игре. После ваших правок
различия с оригиналом в соответствующих функциях будут ожидаемыми.

## Почему нужен отдельный SDK

Клиентский Material содержит поля, отсутствующие в старой Engine.dll UCC.
Пересборка клиентского Engine на ней приводила к GPF при уничтожении Texture.

Найден публичный UE2 Runtime 2226.19.03, чьи UCC.exe/Core.dll/Engine.dll/Editor.dll
побайтово совпадают с предоставленными бинарниками компилятора. Его Core.u,
Engine.u и Editor.u импортированы в `sdk/runtime2226` вместе с License.int.
URL, хеш установщика и хеши файлов записаны в sdk/runtime2226/manifest.json.
Установщик использован только как ZIP-архив и не запускался.

Компиляционный SDK сохраняет родной layout UObject, но включает клиентские
типы и функции Object, в том числе INT64. В Engine.u дополнены только enum
метаданные Actor.EL2ObjectType и Interactions.EInputKey; нативные поля и данные
текстур остаются на исходных смещениях.

Три отсутствующих поля Engine.Vehicle (MaxFuel, CurFuel, DriverID) представлены
в компиляторе символическими IntProperty. Они не добавляются в storage/Children
нативного Vehicle. Результат содержит обычные импорты к реальным полям клиента;
эти импорты совпадают с оригинальным Interface.u.

Модификатор `constructive` убирается из native struct только в компиляционной
копии: C++ конструкторы клиентских DLL здесь не генерируются. Runtime DLL и
описания структур клиента остаются исходными. Class flags localized,
dynamicrecompile и nonativereplication поддерживаются расширением.

## Создание нового workspace

```powershell
py -3 tools/prepare_interface.py workspace2
./build_interface.ps1 -Workspace ./workspace2
```

SDK уже подготовлен. Если требуется восстановить его отдельно, используйте
проверенный установщик из URL в manifest.json:

```powershell
py -3 tools/import_runtime_sdk.py UE2Runtime-22261903.exe sdk/runtime2226
```

Импорт требует нового каталога и сверяет SHA1 установщика и SHA256 всех четырёх
бинарников с профилем компилятора. Новые каталоги не перезаписывают существующую
работу.
