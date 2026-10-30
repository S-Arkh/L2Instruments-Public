# Исторические комплекты ExtensionL2

Эта таблица описывает исходное рабочее дерево до публикации. Перечисленные
готовые файлы не входят в Git и не создаются одной командой CMake.
Текущая инструкция: [README](README.md), полный маршрут: [Clear HF](../docs/CLEAR_HF_WALKTHROUGH.md).

| Исторический каталог | Назначение |
|---|---|
| `dist/profiles/Clear_hf/` | Core-комплект High Five |
| `dist/profiles/Gracia_epilogue/` | Core-комплект Gracia, бывший prepared-gracia-epilogue-v2/client |
| `dist/profiles/client_b3fb9af3/` | Комплект другого поддерживаемого Core-профиля |
| `dist/client/`, `dist/win32/` | Общий клиентский модуль и готовые инструменты |
| `work/gracia/v2/` | Workspace, bindings и тестовый bytecode прежней подготовки Gracia |
| `archive/gracia/v1/` | Предыдущая подготовка Gracia: client и workspace |

При переносе 2026-10-30 проверялось побайтовое сохранение 101 файла.
Исторические абсолютные пути в bundle.json и логах отражают прежние запуски.
Журнал: `reports/layout-20261030.json`; результаты: [VALIDATION](VALIDATION.md).
