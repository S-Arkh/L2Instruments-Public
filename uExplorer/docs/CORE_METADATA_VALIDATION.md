# Core / NWindow: Within, native metadata и cast 57

## Within

Ссылка `Object` внутри Core и импорт `Core.Object` обозначают стандартного
владельца класса. Генератор разрешает символ и проверяет пакет Core, имя Object,
тип Class и отсутствие внешнего владельца. Совпадения одного короткого имени
недостаточно: одноимённый класс другого пакета не считается корневым.

Для другого подтверждённого класса выводится `within <Class>`. Неразрешённая,
не являющаяся классом или недопустимая ссылка на себя сохраняет `partial`.
Тесты включают локальную ссылку Core.Object, нестандартный Within и ошибочные ссылки.

## Native-объявления

Компиляторный пример подтвердил: native-класс определяется `RF_Native`
(`0x04000000`) в ObjectFlags экспорта, а не битом `0x1000` в ClassFlags.
Сохраняются `native`, `noexport` (`ClassFlags & 0x100`) и `native` у свойств
(`PropertyFlags & 0x1000`). Реализации native-функций не восстанавливаются;
их объявления и индексы сравниваются при повторной компиляции.

## Unknown cast 57

`EX_PrimitiveCast` имеет opcode `0x39`. Следующий байт — **отдельный индекс
преобразования**. Значение 57 (`0x39`) этого индекса означает rotator → vector.

Это сопоставлено с сохранённым ScriptText старых пакетов (например,
Actor.EffectIsRelevant и Pawn.CheckWaterJump) и подтверждено независимой
компиляцией `vector(Rotation)` и вложенного преобразования. Генератор выводит
`vector(...)`, сохраняя дерево выражения и порядок вычислений.

## PtrProperty: подтверждённое ограничение

У трёх современных наборов 133/40 совпадают метаданные:

| Свойство | Flags | ArrayDim | Дополнительный хвост |
|---|---:|---:|---:|
| GFxValue.pValue | 0x1000 (native) | 1 | 0 байт |
| Pawn.AnimData | 0x2000 (transient) | 1 | 0 байт |
| MeshComponent.MeshComponentData.LinkedAnimData | 0x2000 | 1 | 0 байт |

Чтение этих свойств проходит. Однако **подтверждённого объявления данного типа
в доступном SDK пока нет**. Пробный синтаксис `var native const transient pointer
Handle;` отвергнут текущим компилятором: `Unrecognized type 'pointer'`.
В исследованных DLL компилятора не найдены имена PtrProperty/PointerProperty;
современный клиент содержит PtrProperty. Это различие SDK, а не ошибка чтения
пакета. Проверка `pointer` не доказывает, что это исходный синтаксис данного клиента.

Тип не заменяется на int/Object и свойство не скрывается. GFxValue сохраняет
`partial`; отчёт дополнен `unrecovered_properties`: имя, исходный тип, flags,
размерность, непрочитанный хвост и полный `raw_hex` сериализованных метаданных.
При усечённых метаданных сохраняются доступные raw-байты без придуманных flags.
Пользовательские данные указателя из памяти клиента в пакете не восстанавливаются.

Следующий отдельный этап для PtrProperty — установить синтаксис клиентского
диалекта и совместимый SDK либо согласовать расширение компилятора. ucc64/SDK
в этой доработке не изменяются.

## Проверки

Из каталога uExplorer, с собранным Windows x64 ядром:

```powershell
ctest --test-dir build-generation -C Release --output-on-failure
python -B tests/compile_generation.py --compiler D:/compiler/System `
  --launcher D:/toolchain/ucc64.exe --sources tests/metadata `
  --library build-generation/Release/uexplorer_core.dll `
  --metadata-probe build-generation/Release/uexplorer_metadata_probe.exe `
  --out local/metadata/roundtrip
```

Каталог назначения должен быть новым. Компилятор и SDK копируются в него;
исходные каталоги используются только для чтения. Сравниваются Within,
ObjectFlags/ClassFlags, типы/флаги свойств, функции, native-индексы, PC и AST.

Отрицательный тест неподтверждённого синтаксиса указателя:

```powershell
python -B tests/compile_generation.py --compiler D:/compiler/System `
  --launcher D:/toolchain/ucc64.exe --sources tests/metadata_unsupported `
  --out local/metadata/pointer-negative --expect-error "Unrecognized type 'pointer'"
```

PASS здесь означает **ожидаемый отказ** компилятора и отсутствие Generation.u.
Этот пример не является поддерживаемой декларацией для генератора.

`tests/inspect_metadata.cpp` — read-only утилита исследования и сравнения тестовых
пакетов. Она не входит в пользовательский portable-дистрибутив.

Полная матрица описана в [GENERATION_VALIDATION.md](GENERATION_VALIDATION.md).
`audit_generation.py --jobs 5` запускает независимые процессы по профилям,
выводит прогресс каждые 50 классов и объединяет результаты перед сравнением.
Подробные отчёты, игровые пакеты и журналы остаются локальными; пути в примерах
условные. Успех генерации не заменяет проверку загрузки в клиенте.

## Результаты полного сравнения

Проверенное ядро Windows x64 Release:
`9e77aca2481a549761c7b1a0a2055505321abbcf8d8e87b7b90a3f6e1b994b7d` (SHA-256).
На 23 пакетах в двух режимах: 0 регрессий и 0 ошибок структурного разбора.
`Unknown cast 57` больше не встречается. Все ранее восстановленные интерфейсы
сохранили `recovered`; сохранённый ScriptText не изменился.

| Профиль | Пакет | partial до | partial после (bytecode) |
|---|---|---:|---:|
| A, B, C (133/40) | Core.u | 8 | 0 |
| D, E (123/37) | Core.u | 8 | 0 |
| A, B, C | Engine.u | 76 | 74 |
| D, E | Engine.u | 71 | 69 |
| A, B, C | NWindow.u | 1 | 1 |
| D, E | NWindow.u | 0 | 0 |

Наличие других замечаний в Engine означает, что устранение cast/Within не всегда
меняет итоговый статус класса. У NWindow остаётся только исследуемый PtrProperty.
Метки профилей обезличены; полный исходный набор и журналы остаются локальными.

Пройдены три CTest-теста, compiler roundtrip пяти новых функций с проверкой
метаданных (включая native-вызов), регрессия восьми функций делегатов/new и
отрицательный compiler-тест `pointer`. Подробные отчёты:
`local/metadata/after.json`, `roundtrip-final/roundtrip.json`,
`delegate-regression/roundtrip.json`, журнал `pointer-negative/compile.log`.
