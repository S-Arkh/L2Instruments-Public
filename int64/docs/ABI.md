# Проверенный бинарный профиль и гипотезы перехватов

Editor preferred image base: `0x10200000`. Все адреса ниже — RVA.
Хеши — в README и verify_profile.py. Клиентская DLL имеет другой ABI.

| RVA | Назначение | Восстановленная сигнатура |
|---|---|---|
| `0x705a0` | выбор преобразования | `cdecl int(const Property* dest, const Property* source)` |
| `0x713c0` | ConversionCost | `thiscall int(Compiler*, const Property* dest, const Property* source)` |
| `0x74870` | FindField | `thiscall Field*(Compiler*, Struct*, const wchar_t*, Class*, const wchar_t*)` |
| `0x72760` | конструктор FToken из FPropertyBase | `thiscall Token*(Token*, const Property*)` |
| `0x72ac0` | EmitConstant | `thiscall void(Compiler*, Token*)` |
| `0x74260` | попытка преобразовать константу | `thiscall void(Token*, const Property*)` |
| `0x7b590` | GetToken | `thiscall int(Compiler*, Token*, const Property*, int noConsts)` |
| `0x78430` | CompileExpr | `thiscall int(Compiler*, Property byValue, const wchar_t*, Token*, int, Token*)` |
| `0x73320` | MatchSymbol | `thiscall int(Compiler*, const wchar_t*)` |
| `0x71290` | сохранение позиции | `thiscall void(Compiler*, Retry*)` |
| `0x736e0` | перенос сгенерированного кода | `thiscall void(Compiler*, const Retry*, const Retry*)` |

Ghidra потеряла второй аргумент функции `0x705a0`. Машинный код берёт его
из `[esp+0x14]` после сохранения EBX/ESI/EDI. ConversionCost передаёт оба
указателя и снимает со стека 8 байтов. Использовать экспортированную Ghidra
сигнатуру с одним аргументом нельзя.

ConversionCost, в отличие от GetConversion, завершает вызов через `ret 8`,
а FindField — через `ret 16`; вызывающие места передают Compiler в ECX.
Это проверяется verify_profile.py. Несоответствие cdecl/thiscall здесь повреждает
стек даже при вычислении обычного `ID.ClassID == 57`.

В class-header цикле GetToken возвращается на `0x80de0`. Только в этом месте
обрабатываются клиентские флаги: nonativereplication очищает 0x800,
localized устанавливает 0x20, dynamicrecompile устанавливает 0x400000.
Смещение UClass::ClassFlags в компиляторе — +0x498.

FindField при отсутствии трёх известных Vehicle-полей может вернуть метаданные
IntProperty (ArrayDim=1, ElementSize=4, Flags=0). Они создаются через Core API,
имеют Outer Engine.Vehicle, но не добавляются в Children и не меняют
PropertiesSize. Их Offset не используется компилятором: в Script записывается
символическая ссылка, которая разрешается в настоящее свойство клиента.
Эти инварианты проверяются в момент создания прокси.

`Property` занимает 20 байтов: type, array dimension, flags, struct/class/enum
pointer, metaclass pointer. `Token` занимает `0x8a4`: Property, четыре int,
64 UTF-16 символа Identifier, 2048 байтов объединения значений.

Компилятор содержит встроенный FArchive по `+0x1c`, его virtual Serialize —
слот 1. Retry содержит четыре int, последний — размер Script в памяти.

Вызов GetToken в начале CompileExpr возвращается на `0x784d3`.
Только этот вызов допускает разбор `int64(...)` в tokenHook с генерацией
байткода. При просмотре вперёд или объявлениях никаких выражений не генерируется.

После автоматического cast CompileExpr обнуляет указатель структуры в новом
Property. Конструктор токена вызывается с возвратом на `0x7a53e`.
ctorHook восстанавливает указатель только в этой точке и только если
непосредственно предшествующее выбранное преобразование принадлежало INT64.
Это требует runtime-проверки при вложенных выражениях.

Проверено в smoke: `int64(int64(Value + 1) + 5000000000)` компилируется;
в байткоде остаются только необходимые casts 0x5b и 0x5e.

Большие литералы хранятся во временном FToken с type Struct, kind Const,
точным int64 в начале объединения и служебной меткой по `data+8`.
EmitConstant распознаёт метку. Для явно приведённого выражения используется
другая метка: его код уже сформирован, повторная эмиссия не нужна.

Core UStructProperty::ImportText использует указатель Struct по `+0x6c`.
Числовой default записывается как пара `[high32, low32]`. В остальных
структурах и при исходном синтаксисе `(Left=...,Right=...)` вызывается оригинал.

В ImportText нельзя использовать appThrowf как в CompileExpr: при проверке
ошибочного default это приводило к generic protection fault. Теперь ошибка
выводится через GWarn::Serialize(NAME_Error), а ImportText возвращает nullptr.
GWarn::NumErrors по смещению +8 подтверждён итоговыми кодами возврата UCC.
Перехват ANSI Serialize восстанавливает учёт NAME_Error: оригинальная реализация
этого UCC увеличивала только NumWarnings. Шесть негативных тестов завершились
кодом 1 и не создали Int64Smoke.u.

## Подтверждённые клиентские индексы

GCast base VA: `0x150ec2d8`; GNatives: `0x150ec6d8`.

| Cast | Индекс |
|---|---|
| byte -> INT64 | 0x5a |
| int -> INT64 | 0x5b |
| bool -> INT64 | 0x5c |
| float -> INT64 | 0x5d |
| string -> INT64 | 0x5e |
| INT64 -> byte | 0x5f |
| INT64 -> int | 0x60 |
| INT64 -> bool | 0x61 |
| INT64 -> float | 0x62 |
| INT64 -> string | 0x63 |

Токен primitive cast — `0x39`, после него байт индекса и выражение.
Индексы native-операторов 400..413 подтверждены initializer-кодом клиентской DLL.
Прямой INT64 constant — `0x46`; модуль его не генерирует.

В оригинальном interface.u полностью декодированы:

| Функция | Размер скрипта в памяти | Особенности |
|---|---|---|
| CalculatorWnd.GetOperand | 42 | casts 0x5e и 0x5b; восстановлен пропущенный return |
| CalculatorWnd.SetNumeric | 122 | cast 0x63; сообщение 3093 при длине >17; затем CE |
| CalculatorWnd.Calc | 169 | natives 404,405,401,412,403; сравнение INT64 с int zero |

Декодер проверяет границу script по размеру В ПАМЯТИ, затем читает хвост
UFunction и требует полного потребления export. Смещения переходов проверяются
по границам инструкций, а не по смещениям компактных ссылок в файле.
