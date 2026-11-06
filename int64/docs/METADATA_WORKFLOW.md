# Проверка метаданных и времени жизни

Исследование этапа 5 завершено с установленной несовместимостью контрактов SDK
и клиентов. Это **не** подтверждение полного совпадения метаданных Interface.
Подробные результаты: [METADATA_LIFECYCLE_RESEARCH.md](METADATA_LIFECYCLE_RESEARCH.md).

## Запуск

Нужны Windows x86 SDK, собранные `ucc64.exe`, `Ucc64Bridge.dll`,
`ptr_lifecycle_probe.dll`, `uexplorer_core.dll` и `uexplorer_metadata_probe.exe`.
SDK — вход только для чтения. Каталоги результатов должны быть новыми и находиться
под `uExplorer/local`. Команды выполняются из корня репозитория через Windows Python.
Замените `<sdk>`, `<tools>` и `<explorer>` своими каталогами.

```text
python -B uExplorer/tests/compile_generation.py --compiler <sdk> --launcher <tools>/ucc64.exe --sources uExplorer/tests/metadata_lifecycle --library <explorer>/uexplorer_core.dll --metadata-probe <explorer>/uexplorer_metadata_probe.exe --out uExplorer/local/metadata-fixture

python -B int64/tests/metadata_contract.py --compiler <sdk> --tools <tools> --metadata-probe <explorer>/uexplorer_metadata_probe.exe --package uExplorer/local/metadata-fixture/System/Generation.u --out uExplorer/local/metadata-contract
```

Первая команда проверяет экспорт, повторную компиляцию и метаданные синтетики.
Вторая выполняет две серии по три отдельных процесса, native-копирование,
создание из шаблона, GC и шесть загрузок в editor/client/server-контекстах.
Один отрицательный client-контроль ожидаем: у копии классов снят только
`RF_LoadForClient`. Общий PASS требует именно установленной ошибки этого контроля.

## Устройство инструментов

- `metadata_variant.py` принимает только синтетический набор из трёх известных
  классов. Параметры `--original-property-mask` и `--clear-client-class-bit`
  создают проверяемые копии; `changes.json` содержит смещения, маски и хеши.
- `metadata_lifecycle.py` проверяет три точных хеша SDK, копирует окружение,
  подставляет исследовательскую DLL и собирает три снимка save/reload.
  Известные Ver111-оболочки декодируются без подмены версии пакета.
- `ptr_lifecycle_probe.dll` перехватывает завершение appInit. Только режим
  `metadata` включает наблюдение Serialize/Link; существующие pointer-режимы
  сохраняют прежнее назначение. Это тестовая DLL, а не DLL поставки.
- `metadata_contract.py` проверяет ожидаемые маски, результаты native-операций,
  стабильность двух последующих инвентарей и разницу загрузочных контекстов.

Для отдельного внешнего пакета:

```text
python -B int64/tests/metadata_lifecycle.py --compiler <sdk> --tools <tools> --metadata-probe <explorer>/uexplorer_metadata_probe.exe --package <package> --objects "NWindow.GFxValue;NWindow.GFxValue.SetElement.Value;NWindow.GFxValue.pValue" --out uExplorer/local/metadata-external
```

`--objects` — полные имена классов/свойств через `;`, включая точные пути внутренних
элементов массивов. `--context` выбирает editor (по умолчанию), client или server.
`--lifecycle` разрешён по смыслу только для фиксированной синтетики Generation:
это не универсальный тест native-классов внешнего пакета.

## Отчёты и диагностика

`inputs.json` связывает вход, декодированную копию, SDK и инструменты по хешам.
`serialized-N.json` — данные с диска; `pass-N.log` — native-переходы и проверки;
`result.json` — сводка успешной серии. Ошибка процесса остаётся ошибкой, даже
если перед ней успели появиться отдельные успешные строки. Отсутствие итогового
`result.json` не означает отсутствие локальных диагностических материалов.

`0x4000008` в файле и `0x4400008` после Link — разные стадии. Сравнивайте их
раздельно. Повторное сохранение оригинального GFxValue в SDK действительно
меняет маски; инструмент не скрывает это нормализацией.

`Bad expr token 46/47` при загрузке полного Interface означает несовместимость
bytecode с этим SDK-пробником. Не заменяйте заголовок и не объявляйте такой прогон
успешным. Исследование оригинального NWindow проходит после декодирования оболочки.

## Новый профиль

Общий capture-инструмент принимает другие пакеты с классами и свойствами, но SDK
ABI остаётся фиксированным. Для другого SDK нужны отдельные проверенные хеши,
смещения, сигнатуры и контрольные результаты; простого отключения проверки хеша
недостаточно. Для нового клиента отдельно снимайте initialized native-экспорты
Serialize/Link/CopySingleValue в изолированной копии, затем проверяйте его runtime.
Не переносите результат SDK GC на клиент автоматически.

Текущие изменения — исследовательские тесты. Production-компилятор и экспортёр
не переписывают флаги; полная точность исходных метаданных остаётся неподтверждённой.
