# Объединение addWeb и gameAddWeb — 2026-10-30

После переноса подтверждена работа HF/Gracia. Выполнена
[очистка кешей и промежуточных объектов](CLEANUP_POST_VALIDATION.md);
исторические контрольные списки содержат также явно удалённые временные файлы.

Основной проект больше не использует соседние каталоги `../addWeb` и
`../gameAddWeb`. Они переименованы в `addWeb.retired` и `gameAddWeb.retired`;
это резервные копии для последующего отдельного удаления. Junction/symlink нет.

## Новые пути

| Материалы | Путь от корня gameAddWebWithD3D9 |
|---|---|
| UCC launcher и bridge | `toolchain/` |
| WebView2 SDK | `sdk/webview2/` |
| XDAT editor и схемы | `sdk/editor/` |
| Общие JSON-заголовки | `sdk/json/` |
| Парсер UE2, извлечение, компиляция, упаковка | `tools/ue2/` |
| Полная историческая реализация overlay | `archive/addWeb/` |
| Ранние текстурные прототипы | `archive/gameAddWeb/prototype/`, `archive/gameAddWeb/browserTexture/` |
| Ghidra-базы, скрипты и captures | `archive/gameAddWeb/projects/`, `ghidra/`, `captures/` |
| Исторические отчёты | `archive/addWeb/*.json`, `archive/gameAddWeb/reports/` |
| Актуальные проверенные комплекты | `out/high-five/`, `out/gracia/` |

Архив addWeb сохранён полным снимком, включая его старые копии tools/compiler/SDK:
они фиксируют окружение ранней реализации. Активные браузерные сборки используют
общие tools/ue2, toolchain и sdk. Исходные inputs, native и workspace раннего
overlay используются подготовкой профилей из `archive/addWeb`; этот внутренний
архив удалять нельзя. Старые инструменты разработки самого UCC сохранены в
архиве; в tools/ue2 вынесены только переиспользуемые модули браузерной цепочки.

## Зависимости

- HF/Gracia → локальные SDK, toolchain, tools/ue2 и archive/addWeb.
- Исторический gameAddWeb → локальные SDK/toolchain и соседний архив addWeb.
- Эксперимент GPU → sdk/json (ранее брал заголовки из соседнего gameAddWeb).
- uExplorer → tools/ue2, sdk/json, архивные fixtures addWeb и profiles/gracia.

Это отказ от двух старых каталогов, а не от всех соседних инструментов workspace:
Python runtime по-прежнему берётся из interface_editor, часть подготовки — из
int64 и dll. Исследовательские внешние Ghidra/JDK остаются внешними зависимостями.

## Проверки

При недоступном исходном addWeb выполнены:

- свежие нативные сборки HF, Gracia helper, Gracia in-process, GPU и overlay;
- компиляция UC и упаковка HF/Gracia в `work/migration/out/`;
- проверка manifests и установка/откат новых пакетов через API существующих
  установщиков на временных каталогах; пользовательский options.config сохранён;
- регрессии uExplorer: validate.py и validate_formats.py.

После переноса gameAddWeb собраны его prototype и browserTexture из новых путей.
Оба исходных каталога отсутствовали под прежними именами.
Файлы готовых комплектов `out/` совпали с исходными SHA-256.
Тестовые пересборки имеют другие хеши и не объявляются подтверждёнными в игре.
В рамках автоматической проверки переноса игровой запуск и открытие Ghidra-баз
не выполнялись. Работа HF/Gracia в игре подтверждена отдельно.

`tests/build_migration.ps1` собирает нативные проекты в свежих каталогах
`work/migration`, `-Only <имя>` выбирает одну сборку.
`build_browser_options.ps1 -OutputRoot <путь>` позволяет проверить упаковку,
сохранив подтверждённые файлы в out. Без параметра выход по-прежнему out.
`tests/verify_migration.py` проверяет сохранённые данные и install/restore.

Старые CMake build-каталоги архивных проектов переименованы в `build-before-move`:
сохранены, но не используются для новых сборок. Перед запуском архивного test.ps1
сначала выполните build.ps1. Исторические JSON и логи могут содержать старые
абсолютные пути; это записи прошлых запусков.

Контрольные хеши и результаты: `reports/addweb-migration.json` и
`reports/gameaddweb-migration.json`.
