# pinkDream

**Публикационная копия:** поставляются инструменты, генератор и рецепты тем.
Библиотеки текстур, изображения и готовые UTX создаются локально.
[Установка зависимостей и автономные тесты](../docs/BUILD.md#pinkdream).
Прежние готовые комплекты описаны в [историческом перечне](docs/HISTORICAL_BUILDS.md).

Сборка в Windows и все реализованные функции в игре проверены. Для Scryde
pinkDream — единственный рабочий проект в этом наборе; в остальных проектах
интеграция не запустилась либо исследования прекращены.

[Карта проектов и правила хранения](../gameAddWebWithD3D9/docs/PROJECT_LAYOUT.md).

Темы стандартного интерфейса Lineage II с общей генерацией и профилями клиентов.
Сохраняются оригиналы, редактируемые изображения, PNG/TGA, mip-уровни и готовые UTX.

## Начало работы из чистого клона

Из каталога `pinkDream`:

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tools -p 'test_*.py' -v
python tools/create_library.py --help
python tools/build_theme.py --help
```

1. Подготовьте стандартный клиент и selection ресурсов своего профиля.
2. Создайте inventory и исходную библиотеку по
   [ADDING_THEMES, раздел 4](docs/ADDING_THEMES.md#4-подключение-другого-клиента).
3. Передайте полученный `manifest.json` и рецепт из `themes` в `build_theme.py`
   по [разделу 5](docs/ADDING_THEMES.md#5-сборка-и-импорт-ручных-изображений).
4. Проверьте созданные UTX и изображения, затем используйте
   [установку с backup/откатом](docs/THEMES.md), подставляя пути своей сборки.

Библиотеки, previews и устанавливаемые UTX появляются только после этих шагов.
Названия исторических ревизий не означают, что такие файлы уже есть в клоне.

## Разработка

Последнее исправление: [гладкие ползунки и края перетягивания](docs/SMOOTH_CONTROLS.md).

**[Техническое руководство по новым темам и клиентам](docs/ADDING_THEMES.md).**

```sh
python tools/library.py list
# После создания собственной библиотеки, подставьте её путь:
python tools/build_theme.py --library path/to/library/manifest.json --theme themes/halloween/theme.json --revision custom-v001
```

- `themes/` — общие рецепты Christmas, Halloween, Glamour Pink.
- `profiles/<client>/` — инвентаризация, выбор ресурсов, статус и отчёты.
- `assets/libraries/` — стандартные исходники и layout отдельно для каждого клиента.
- `assets/objects/sha256/` — общие неизменяемые объекты; не удалять вручную.
- `assets/generated/<client>/<theme>/<revision>/` — изображения, mip, snapshots и previews.
- `assets/archives/` — хеш-архив ранних изображений и метаданных.
- `builds/<client>/<theme>/<revision>/` — независимые устанавливаемые комплекты.
- `tools/` — импорт, сборка, проверка, экспорт, установка и очистка.
- `generator/` — отдельная библиотека ранних процедурных концептов.

HF и Gracia пока имеют заготовки профилей. Для них создаются свои библиотеки;
рецепты общие, UTX Scryde для них не используются.

## История

[Прежние сборки и previews](docs/HISTORICAL_BUILDS.md),
[результаты очистки исходного дерева](docs/CLEANUP.md), ранние эксперименты — `docs/history/`.
