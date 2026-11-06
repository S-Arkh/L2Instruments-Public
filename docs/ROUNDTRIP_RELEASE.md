# Итоговый аудит, регрессия и поставка script tools

Область этого этапа: ucc64, uExplorer и связанные проверки script tools.
Успех экспорта, компиляции, метаданных, SDK VM и игрового клиента учитывается
раздельно. Данные игрового клиента в архивы инструментов не входят.
Результаты конкретного снимка и хеши архивов:
[ROUNDTRIP_VALIDATION.md](ROUNDTRIP_VALIDATION.md).

## Аудит покрытия

| Изменение | Положительный/roundtrip-контроль | Отрицательный или дополнительный контроль |
|---|---|---|
| INT64, преобразования enum/byte | `int64_enums`, CTest `int64_semantics`, прежние клиентские отчёты | `int64_enums_unsupported`: запрет неявного enum → INT64 |
| Optional dynamic array | `optional_arrays`, сохранность descriptor flags, клиентские вызовы с пропуском/передачей | `optional_arrays_unsupported`: обязательный аргумент нельзя пропустить |
| Квалифицированные и зависимые структуры | `generation`, `expressions`, `metadata`, VM `semantics` | Строгие metadata/AST-сравнения |
| Лексические enum и область аргументов | `enum_collisions`, `expressions`, `semantics` | Конфликт имён текущего класса и получателя |
| Профиль client enum | `client_enums` с `--client-enum-profile korea290`, `client_enums_legacy` без него | Профиль является явной настройкой, не универсальным исправлением SDK |
| Typed context helpers, ветвления, PC-dispatch | `expressions`, десять заданных VM-результатов `semantics` на обеих сборках | Изменения AST/helper допускаются только фиксированным semantic-режимом |
| EV-имена | `expressions`, `compile_event_switch.py` | Alias, shadowing, вычисляемый selector сохраняют числовые значения; named/numeric AST равны |
| Defaults, replication, iterators, states | Одноимённые компиляторные наборы и CTests | Неподдерживаемые конструкции не становятся автоматически поддержанными |
| Native PtrProperty | `pointers`, fresh-process lifecycle, ProcessEvent, подтверждённые modern-отчёты | 45 отказов, включая nested/inherited struct и RPC; положительные replication controls |
| Client Sort | `array_sort`, производственный decoder profile, клиентские граничные случаи | 12 отказов; строгий default, изоляция кэша, неизвестный профиль и opcode `0x46` |
| `instanced`, editable/category, class flags | `metadata`, `metadata_lifecycle`, настоящий NWindow | Установленная несовместимость saver/linker; флаги не нормализуются |
| UTF-16 staging | `compile_external.py` сохраняет кодовые точки экспортированных классов | Хеш исходного пакета; экспорт/компиляция не заменяют runtime-проверку строк |
| Native файл отчёта | Самостоятельный `extension_probe`, Python-проверки отчёта/Build | Ошибки отсутствующего пути/файла и неверного UTF-8; полный клиентский отказ записи исключён |

Это связь конкретных контрактов с тестами, а не процент branch coverage или
обещание исчерпывающего покрытия всех программ UnrealScript.

## Проверки инструментов

- Свежие MSVC-сборки: INT64 CTest 1/1, uExplorer CTest 7/7.
- Snapshot-регрессия: MSVC 20/20, MinGW launcher/bridge 20/20; входы неизменны.
- Дополнительные EV/enum/negative-контроли: 6/6 для каждого компилятора.
- Python: int64 15 PASS / 21 SKIP; DLL 2 PASS / 8 SKIP; client tools 8 PASS;
  launcher 5 PASS. Пропуски требуют отдельных исторических внешних эталонов и
  не засчитаны как проверки текущих пакетов.
- Самостоятельный native file-I/O probe: PASS на изолированной копии проверенного
  patched Core и прежней ExtensionL2; это не новая сборка DLL и не игровой запуск.

Обнаружены и исправлены две ошибки MinGW: пропущенный `ptr_property.cpp` в
скрипте сборки и экранирование регистров GNU extended asm в Sort-hook.
Последующее сравнение полного Interface обнаружило отдельную ошибку: устаревшая
метка в переиспользуемом токене могла подавлять bool-константу. Исправление
очищает метку при чтении нового bool-токена; подробности и границы доказательства
приведены в [исследовании](../int64/docs/BOOL_TOKEN_REUSE_RESEARCH.md).
Первые отрицательные прогоны также обнаружили ограничение длины пути SDK;
повторный запуск столкнулся с заполнением диска. Эти неуспешные попытки сохранены
отдельно; итоговые PASS получены новым запуском, а не переклассификацией логов.

Повторная MinGW-сборка не дала побайтово одинаковые PE. EXE различались временем
линковки и checksum; DLL также получила другую preferred image base. После
диагностического учёта HIGHLOW-релокаций runtime-секции совпали; оставшиеся
различия относятся к debug-секциям и двум COFF-символам image base. Дистрибутивные
бинарники не изменялись этой диагностикой. Общая byte-for-byte воспроизводимость
native-бинарников не заявляется.

## Воспроизводимый snapshot

Соберите Win32 ucc64 и x64 uExplorer. При конфигурации uExplorer явно передайте
`-DPython_EXECUTABLE=<python-из-venv>`: запуск `python -m cmake` сам по себе не
гарантирует, что FindPython выберет это окружение.

```text
python -B uExplorer/tests/regression_snapshot.py --compiler <SDK-System> --tools <ucc64-bin> --explorer <uExplorer-bin> --out uExplorer/local/regression-msvc
```

Runner копирует бинарники, записывает SHA-256 исходников/SDK/инструментов,
запускает 14 строгих roundtrip-наборов и шесть дополнительных проверок:
semantic VM, Sort profile, Sort negative, pointer negative, pointer lifecycle и
metadata lifecycle. Итоговый PASS требует неизменности входов и всех результатов.
Подробности каждого отказа сохраняются в отдельных логах; SKIP не считается PASS.

Для MinGW повторите команду с другим `--tools`. Если исследовательская DLL
собрана MSVC, передайте `--runtime-probe <MSVC>/ptr_lifecycle_probe.dll`.
Тогда проверены MinGW launcher/bridge и созданные ими пакеты, но native-пробник
и x64-экспортёр остаются MSVC — это явно отражено хешами, а не названо полной
MinGW-сборкой всех компонентов.

Дополнительно запустите `compile_event_switch.py` с теми же compiler/launcher/library;
для `client_enums` используйте `compile_generation.py --client-enum-profile korea290`,
для `client_enums_legacy` — обычный режим. Для трёх отрицательных каталогов из
таблицы используйте `--expect-error` с точной диагностикой SDK.

Для синтетических наборов достаточно SDK без неиспользуемых `Interface.u` и
`InterfaceClassic.u`: Core/Engine и DLL остаются точными копиями входа. Каждый
тест создаёт отдельную копию SDK, поэтому объём рабочей области нужно учитывать.
После завершения можно удалить только свои рабочие копии, сохранив логи,
манифесты и результирующие пакеты. Не используйте hard links для изменяемых DLL.

Старый SDK имеет ограничения длины путей, включая driver discovery. Используйте
короткий корень workspace. Pointer negative-suite сохраняет семантические имена
в `result.json`, а физические каталоги называет `case-N`.

## Реальные пакеты и границы сравнения

`audit_generation.py` проверяет все классы в auto/bytecode-режимах и сравнивает
результаты с baseline только при совпадении входных хешей. Изменившийся пакет
нельзя объявить регрессией или успехом на старом входе: нужен отдельный снимок
и сравнение старого/нового инструмента на этом же снимке.

`compile_external.py` выполняет свежий экспорт и компиляцию в отдельной копии.
Полный Interface требует трёх явных настроек: client Sort, профиль enum и scoped
enum casts. Сравнение с предыдущей собранной версией не подменяет сравнение с
оригинальными клиентскими метаданными. Последнее по-прежнему показывает
установленные отличия, описанные в [исследовании](../int64/docs/METADATA_LIFECYCLE_RESEARCH.md).

Сравнение MSVC/MinGW выполняется на одном исходном пакете и SDK. Отдельно
фиксируются бинарные хеши, metadata и различия GUID. Равенство символических
метаданных не является общим доказательством побайтовой воспроизводимости.

## Поставка

Компилятор:

```text
python -B int64/tools/package_tools.py --tools <ucc64-bin> --variant msvc --revision <full-source-SHA> --out <new-output>
```

Для второго варианта укажите MinGW bin и `--variant mingw`. В ZIP входят только
согласованная пара launcher/bridge, инструкция, лицензии и BUILDINFO. Проверка
извлекает архив в путь с кириллицей/пробелами и запускает launcher с ограниченным
PATH. Полная компиляция извлечённым комплектом проверяется отдельно через
`compile_generation.py --launcher <extracted>/bin/ucc64.exe`.

uExplorer:

```text
python -B uExplorer/tools/package_windows.py --version 0.1.0-dev.4 --bin <uExplorer-bin> --cache <cache> --out <new-output> --revision <full-source-SHA> --download
```

Упаковщик проверяет закреплённые SHA-256 зависимостей и запускает извлечённый
`Start.cmd`: native DLL, CLI, GUI, экспорт и локальные настройки. При переданном
`--revision` dirty-состояние неизвестно (`null`); полную связь состава обеспечивает
manifest файлов. Указывайте ревизию, содержащую именно упакованные исходники.

Новый SDK требует отдельного ABI-профиля и тестов. Новый клиент — совпадающего
предсобранного SDK, описания в `test_interfaces/profiles.py`, подготовки layout
и отдельного клиентского отчёта. Автоматический синтез произвольного SDK не заявлен.

Legacy-указатели не требуются; репликация указателей отложена с сохранением
запрета. Без сервера нет проверки авторизации, мира и сетевого поведения.
Новые архивы инструментов не означают новый клиентский прогон: прежние отчёты
связаны только с теми артефактами, хеши которых были в них проверены.
