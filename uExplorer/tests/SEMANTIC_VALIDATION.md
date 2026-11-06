# Семантика и Sort: воспроизводимые проверки

Запускать из корня репозитория в Windows Python с совместимым x86 SDK.
Все каталоги `--out` должны быть новыми и находиться в `uExplorer/local`.
Входной SDK используется только для копирования файлов в изолированную среду.

```powershell
python -B uExplorer/tests/compile_generation.py --compiler <SDK-System> --launcher <tools>/ucc64.exe --library <tools>/uexplorer_core.dll --sources uExplorer/tests/semantics --scoped-enum-casts --semantic-probe <tools>/ptr_lifecycle_probe.dll --out uExplorer/local/semantic-check
python -B uExplorer/tests/sort_negative.py --compiler <SDK-System> --launcher <tools>/ucc64.exe --out uExplorer/local/sort-negative-check
python -B uExplorer/tests/compile_generation.py --compiler <SDK-System> --launcher <tools>/ucc64.exe --library <tools>/uexplorer_core.dll --sources uExplorer/tests/array_sort --client-array-sort --metadata-probe <tools>/uexplorer_metadata_probe.exe --out uExplorer/local/sort-check
python -B uExplorer/tests/test_sort_profile.py --library <tools>/uexplorer_core.dll --package uExplorer/local/sort-check/System/Generation.u
```

Рядом с launcher необходим `Ucc64Bridge.dll`. `--semantic-probe` допускается
только для фиксированного набора `semantics`: разрешены изменения AST двух
функций и добавление трёх известных helpers. Флаги функций, native ID и
replication offset проверяются отдельно. Обязательный VM-прогон сравнивает
обе сборки с десятью заранее заданными результатами; отчёты находятся в
`runtime/result.json`, `runtime/original.log`, `runtime/recompiled.log`.
`roundtrip.json` сохраняет различия AST и итог выполнения.

Без `--semantic-probe` действует точное сравнение AST. Для этой фикстуры оно
закономерно завершается ошибкой: восстановленный поток управления и helpers
меняют байткод. Это не повод отключать проверку для остальных наборов.
Проверка метаданных остаётся отдельным этапом.

`sort_negative.py --cases missing out result` запускает выбранные отрицательные
случаи. Успех требует конкретной диагностики, ненулевого кода компилятора и
отсутствия выходного пакета. Отсутствующий исходник не считается отказом Sort.

Для экспорта SDK-пакета с Sort передавайте `bytecode_profile='sdk-client-sort'`
в `Core.request` или `export_classes`. Опция не меняет заголовок пакета и
не включает INT64 opcode. Для нового диалекта нужны отдельные проверки формата;
подмена версии пакета не является способом расширения профиля.
