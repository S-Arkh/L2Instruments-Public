# Каталоги и очистка — 2026-10-30

**Обновление:** addWeb и gameAddWeb объединены с этим проектом. Пути gameAddWeb
в таблицах ниже теперь относительны `archive/gameAddWeb/`; старый корневой
каталог — резервный `gameAddWeb.retired`. Актуальная карта общих инструментов
и архивов: [MIGRATION.md](MIGRATION.md).

## Где находятся рабочие материалы

| Проект | Назначение | Каталог |
|---|---|---|
| pinkDream | Готовые темы с версиями | `builds/<profile>/<theme>/<revision>` |
| pinkDream | Оригиналы, изображения, ручные правки и CAS | `assets/` |
| pinkDream | Профили клиентов и инструменты | `profiles/`, `tools/` |
| gameAddWebWithD3D9 | Рабочие HF/Gracia-комплекты | `out/<client>/` |
| gameAddWebWithD3D9 | Рабочие копии компиляции Browser Options | `work/<client>/<timestamp>/` |
| gameAddWebWithD3D9 | Другие собранные варианты | `profiles/<client>/result*/` |
| gameAddWebWithD3D9 | Исходники и восстановленные классы | `profiles/<client>/`, включая `recovered/` |
| gameAddWebWithD3D9 | Подтверждения и отчёты | `reports/`, `profiles/<client>/tests/` |
| gameAddWeb | Рабочие прототипы и браузерная текстура | `prototype/`, `browserTexture/` |
| gameAddWeb | Временный home и tmp для Ghidra | `work/home/`, `work/tmp/` |
| gameAddWeb | Исследования и исходные данные | `projects/`, `ghidra/`, `captures/`, `inputs/`, `reports/` |

Старые версии тем, backups, архивы исходников и Ghidra databases — сохраняемые
наработки. `build`, `stage` и `workspace` могут содержать результаты компиляции
и участвовать в текущих скриптах; их очистка требует отдельной проверки.
Существующие каталоги связаны относительными импортами, скриптами и CMake cache.
При дальнейшем переносе нужно одновременно обновлять эти зависимости.

## Перенос 2026-10-30

| Старый путь | Новый путь |
|---|---|
| `gameAddWebWithD3D9/profiles/<client>/result-browser-options/` | `gameAddWebWithD3D9/out/<client>/` |
| `gameAddWebWithD3D9/profiles/<client>/tests/open-api-<timestamp>/` | `gameAddWebWithD3D9/work/<client>/<timestamp>/` |
| `gameAddWeb/runtime-home/` | `gameAddWeb/work/home/` |
| `gameAddWeb/temp/` | `gameAddWeb/work/tmp/` |

Обновлены build_browser_options.ps1, client_profiles.json, analyze.ps1 и инструкции.
В manifest готовых комплектов исправлена относительная ссылка confirmation_report.
Исторические compile_log и пути в прежних отчётах относятся к моменту запуска;
таблица выше позволяет найти перенесённые рабочие копии. В ещё более старых
логах `browserTexture` соответствует нынешнему `profiles/high-five`, а `gracia`
соответствует `profiles/gracia`.

Файлы при переносе проверены SHA-256. Повторная компиляция HF и Gracia через
`build_browser_options.ps1 -CompileOnly` завершилась без ошибок (35 и 3 предупреждения).
Готовые игровые файлы в out сохранены побайтово. Журнал переноса и контрольные
хеши: `../reports/layout-20261030.json`.

Базовые result/result-inprocess остаются в профилях: это входы сборки Browser
Options и цели прежних установщиков. Нативные CMake build-каталоги также
остаются рядом со своими проектами. pinkDream сохраняет свою структуру assets/builds.

## Временные данные

`profiles/gracia/diagnose_browser.ps1` создаёт WebView2-профили в
`<CACHE_ROOT>\<12-символьный-id>`. `<CACHE_ROOT>` — короткий локальный каталог
кеша; укажите подходящий для своей системы путь параметром `-CacheRoot`,
чтобы не зависеть от значения по умолчанию в скрипте.
Отчёт `launch.json` содержит фактический путь профиля; отчёты
остаются в `profiles/gracia/tests/`. Кеш можно удалить после завершения клиента
и его браузерных процессов. Скрипт не удаляет его автоматически, поскольку
дочерний браузер может пережить процесс запуска игры.

## Выполненная очистка

- Удалены четыре старых диагностических WebView2-профиля Gracia.
- Удалены шесть сырых PML и два полных CSV Scryde.
- Удалён Python `__pycache__` Gracia.
- Сохранены отфильтрованные CSV, итоговые JSON, конфиги и инструкции исследования.
- Освобождено 3 949 556 302 байта (около 3,68 GiB).
- SHA-256 24 807 файлов ассетов, комплектов, восстановленных исходников,
  отчётов и README совпали до и после удаления.

Максимальная длина полного Windows-пути: pinkDream — 174,
gameAddWebWithD3D9 — 211, gameAddWeb — 162. Путей длиной ≥260 больше нет.
Журнал удаления и контрольные хеши: `../reports/cleanup-20261030.json`.
Хеши отражают момент очистки, до последующего обновления документации.
