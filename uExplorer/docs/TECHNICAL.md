# Техническое описание

## Архитектура и файлы

```text
run.cmd → run.ps1 → launch.py → python/app.py
                                  ↓ Worker/QThread
                             python/backend.py
                                  ↓ ctypes, UTF-8 JSON
                             core/api.cpp
                                  ↓ Context
                     package.cpp + decompiler.cpp
```

| Файл | Назначение |
|---|---|
| `core/package.h` | Reader, Package, Node, Function, StructInfo, Symbol, Context |
| `core/package.cpp` | Оболочки, таблицы пакета, метаданные, ScriptText, AST декодер |
| `core/decompiler.cpp` | Зависимости, native registry, типизация выражений, генерация UC |
| `core/api.h/.cpp` | C ABI, JSON-диспетчер, mutex и кэш Context |
| `core/cli.cpp` | Один JSON-запрос из stdin, ответ в stdout |
| `python/backend.py` | ctypes, пути экспорта, байты/кодировки, запись и отчёт |
| `python/app.py` | Виджеты, подсветка, фоновые операции и отмена |
| `launch.py` | Добавление Python-модулей и существующих embedded packages |

Разбор пакета и генерация кода находятся в C++; Python не интерпретирует UE2.
Основные внешние зависимости: header-only nlohmann/json из соседнего
`gameAddWebWithD3D9/browserTexture/vendor`, PySide6 для UI. Во время работы
ядро не загружает DLL клиента и не исполняет UnrealScript.

## C API, ABI 1

```cpp
int ue_abi_version() noexcept;
char* ue_request(const char* input) noexcept;
void ue_free(char* output) noexcept;
```

Вход — NUL-terminated UTF-8 JSON. Ответ — выделенная DLL UTF-8 строка;
вызывающая сторона обязана освободить её именно `ue_free`, включая ответы
с ошибкой. `nullptr` означает сбой выделения/формирования ответа.
Исключения не пересекают ABI. Python использует `ctypes.CDLL` и `c_void_p`
для результата, чтобы сохранить адрес до освобождения.

Операции:

```json
{"operation":"inspect","path":"D:/client/system/Interface.u","dependencies":["D:/sdk/System"],"reload":true}
{"operation":"decompile","path":"D:/client/system/Interface.u","class":"LoginMenuWnd","force_bytecode":false}
{"operation":"decompile","path":"D:/client/system/Interface.u","class_id":123}
{"operation":"function","path":"D:/client/system/Interface.u","function":"LoginMenuWnd.OnLoad"}
{"operation":"reset"}
```

`class_id` — положительный, 1-based индекс export; используйте идентификатор
из `inspect`, а не фиксированное значение примера. `class`/`function` — пути
объектов внутри пакета. `operation` по умолчанию — `inspect`.

Успешный ответ содержит `ok:true`, `package` (версия, оболочка, таблицы/классы),
`diagnostics`; у `decompile/function` также `result`. Ошибка:
`{"ok":false,"error":"..."}`. `reset` возвращает только `ok:true`.
В `decompile.result` есть `class`, `id`, `method`, `status`, `code`, `encoding`,
`issues`; для ScriptText — `raw_hex`, для генерации — `functions` и
`class_flags`, иногда `class_tail_hex`. Набор полей зависит от результата;
потребитель должен допускать дополнительные поля.

Кэш содержит **один Context**, ключ — строка пути и JSON списка dependencies.
Автоматического контроля mtime нет: перед изменёнными файлами задавайте
`reload:true` или вызывайте `reset`. Каждый запрос должен передавать нужные
dependencies заново. Все запросы DLL сериализованы одним mutex; это не
многопакетный сервер. `function` предназначен прежде всего для диагностики.

## Пакеты и метаданные

Reader проверяет границы чтения, compact indexes, строки и ссылки. Отдельно
учитываются imports (отрицательные ссылки), exports (положительные), `None=0`.
Обрабатываются Name/Import/Export tables и цепочки outer. Форматы допускаются
явно: `123/0`, `123/37`, `126/0`. Перед разбором распознаются UTF-16LE маркеры
Lineage2Ver111/GamekitData111 и снимается XOR `0xAC`.

Реализовано чтение Struct/State/Class, Function, Property, Enum, Const и TextBuffer.
ScriptText проверяется на наличие декларации нужного класса после удаления
комментариев; его исходные байты возвращаются отдельно от текста для просмотра.

Ограничители: файл до 512 MiB; таблица до 2 млн записей (с дополнительной
проверкой по длине файла); outer chain до 256; глубина AST до 128;
до 1 млн узлов на декодирование; до 64 загруженных пакетов.
Это проверки корректности, а не обещание ограниченного общего потребления RAM.

## Зависимости и native-функции

Context индексирует `.u` рядом с главным пакетом и в выбранных каталогах,
без учёта регистра имени; затем рекурсивно проходит Package imports.
Приоритет — каталог главного пакета, далее каталоги по порядку.
Ошибки загрузки зависимостей попадают в diagnostics.

Registry `native index → (Symbol, Function)` строится по UFunction метаданным
всех загруженных пакетов. Используются friendly name, operator flags и типы
параметров. Конфликтующие индексы исключаются из registry; генератор выдаёт
явную ошибку, вместо угадывания `UnknownFunctionNNN`.
Это восстановление деклараций/вызовов native, не их C++-реализаций.

## Декодер и генератор

`Decoder::expression` строит дерево Node: opcode/kind, PC, операнды, target,
ссылки и children. **PC байткода отличается от serial offset**: compact object
references в памяти занимают 4 байта. Смешивание этих координат ломает переходы.

Writer разрешает типы параметров/возвратов, enum, поля и receiver вызовов;
выводит наследование, enum/struct/const, свойства, функции и состояния.
Декларации native и функции без FUNC_Defined заканчиваются `;`.
Trailing implicit Return Nothing не печатается в линейном теле.

Линейные функции генерируются непосредственно. При jump/jump_if_not/switch:

1. Индексируются корневые инструкции по PC и проверяются цели переходов.
2. Выделяются границы блоков.
3. Создаётся local `__RecoveredPC` (с разрешением конфликта имени).
4. Блоки выводятся как cases внешнего switch внутри while.
5. Ветви назначают следующий PC, выход маршрутизируется через `-1`.

Для null-context с integer constant создаётся `__UXContextInt`: при `Owner=None`
возвращает 0, иначе константу. Он сохраняет эффект исходного Context, который
нельзя выразить просто заменой на целое число.

Class tail разбирается через GUID, зависимости, package names, Within,
ConfigName, hide categories и tagged defaults. Поддержаны простые scalar,
name/string/object и vector/rotator defaults. Неподдержанный default получает
диагностику/raw; ошибка хвоста сохраняет `class_tail_hex`.

ConfigName восстанавливается как `config(Name)` (либо `config` для None).
Не все флаги/редакторские метаданные восстанавливаются. Within,
replication, state masks и class/state scripts частично диагностируются;
полного восстановления state/latent, delegate и всех defaults нет.
Список `issues` не следует считать исчерпывающим доказательством отсутствия
потерь на непроверенном профиле.

## Ошибки и сохранность диагностических данных

Неподдержанное выражение делает функцию неполной: в `.uc` помещается
`INCOMPLETE`, в отчёт — декодированный AST. При ошибке декодирования функции
сохраняется raw serial payload. Неполные члены/состояния и defaults сообщаются
отдельно. Не каждый вид пропущенных метаданных имеет полный raw dump;
оригинальный пакет остаётся необходимым источником для дальнейшего анализа.

backend отделяет транспорт от файлового экспорта. Пути строятся из допустимых
идентификаторов, проверяются Windows reserved names, выход за назначение и
case-insensitive collisions. Запись файла — временный файл рядом с назначением
и `os.replace`. Весь экспорт не является одной транзакцией. Проверка запрета
перезаписи не обеспечивает межпроцессную блокировку при одновременной записи
другой программой. Отчёт создаётся отдельно на каждую операцию.

UI использует один Worker/QThread; сигналы возвращают результат в GUI-поток.
Отмена — threading.Event, проверяемый backend между классами. Внутреннее
прерывание C++-запроса пока не реализовано.

## Как дорабатывать

### Новый профиль пакета/оболочка

Сохранить fixture с хешем; исследовать header и layout метаданных; добавить
отдельную проверяемую ветвь reader. Недостаточно расширить whitelist версий:
сначала подтвердить поля, размеры и окончания сериализованных объектов.
Сравнить таблицы, функции и ScriptText с независимым парсером.

### Новый opcode

Добавить декодирование в `Decoder::expression`, правильно увеличить memory PC,
сохранить operands/children. Затем добавить expression/body lowering в Writer
и при необходимости nodeType/receiver. Если вывод ещё не реализован, сохранять
явный partial. Проверять не только текст UC, но и повторную компиляцию/CFG.

### Новый тип свойства/default

Расширить Package::property, Writer::type/declaration, типизацию вызовов и
tagged-default reader согласованно. Проверять array dimensions, flags,
enum qualification и импортированные ссылки. DelegateProperty — известная
точка следующего расширения (fixture `gameAddWebWithD3D9/archive/addWeb/inputs/interface.u`, класс L2Util).

### Улучшение читаемости

Структурирование if/while можно добавить поверх существующего CFG. Сохранить
dispatcher как fallback и использовать семантический verifier для проверки
переходов/порядка выражений. Проверяющий скрипт должен нормализовать только
обоснованные преобразования, а не скрывать любые расхождения.

### API/UI

При изменении несовместимого C ABI повысить ue_abi_version и обновить backend.
Для нового JSON-поля достаточно совместимого расширения; документировать
обязательность/отсутствие полей. Длительные действия оставлять в Worker.
Для переносимой поставки вынести JSON header и Python runtime зависимости
из соседних проектов в контролируемые зависимости сборки/дистрибутива.
