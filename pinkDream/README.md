# pinkDream

**Публикационная копия:** поставляются инструменты, генератор и рецепты тем.
Библиотеки текстур, изображения и готовые UTX создаются локально.
[Установка зависимостей и автономные тесты](../docs/BUILD.md#pinkdream).
Готовые комплекты ниже описывают результаты исходного рабочего дерева.

Сборка в Windows и все реализованные функции в игре проверены. Для Scryde
pinkDream — единственный рабочий проект в этом наборе; в остальных проектах
интеграция не запустилась либо исследования прекращены.

[Карта проектов и правила хранения](../gameAddWebWithD3D9/docs/PROJECT_LAYOUT.md).

Темы стандартного интерфейса Lineage II с общей генерацией и профилями клиентов.
Сохраняются оригиналы, редактируемые изображения, PNG/TGA, mip-уровни и готовые UTX.

## Готовые комплекты Scryde

| Тема | Папка с файлами для замены |
|---|---|
| Christmas v003 — леденцы и гирлянды; гладкие ползунки и края | `builds/scryde/christmas/v003/SysTextures` |
| Halloween v002 — тыквы, паутина, кости; гладкие ползунки и края | `builds/scryde/halloween/v002/SysTextures` |
| Glamour Pink v001 — розовая тема | `builds/scryde/glamour-pink/v001/SysTextures` |

Каждая тема: 446 текстур / 492 mip-уровня в пяти UTX. При закрытой игре файлы
копируются в `<SCRYDE_CLIENT>\SysTextures` с резервным копированием предыдущих.
`<SCRYDE_CLIENT>` — корень клиента Scryde, содержащий `SysTextures` и `Scryde`;
подставьте путь к своей установке.
**[Установка с автоматическим backup/откатом и переключение тем](docs/THEMES.md).**
Актуальные версии проверены офлайн и в игре на Scryde.

Предпросмотры:

- `assets/generated/scryde/christmas/v003/previews/highlights.png`
- `assets/generated/scryde/halloween/v002/previews/highlights.png`
- Исправление повторяющихся узоров: `assets/previews/seasonal-scaling-fix.png`.
- Полное сравнение каждой темы — соседние `page-*.png`.

## Разработка

Последнее исправление: [гладкие ползунки и края перетягивания](docs/SMOOTH_CONTROLS.md).

**[Техническое руководство по новым темам и клиентам](docs/ADDING_THEMES.md).**

```sh
python -m pip install -r requirements.txt
python tools/library.py list
python tools/build_theme.py --library assets/libraries/scryde/standard-ui-v001/manifest.json --theme themes/halloween/theme.json --revision v002
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

## Очистка старых версий

Ранние trial-v001…v004 UTX-дубликаты удалены после проверки. Их готовые изображения,
оригиналы и метаданные сохранены по хешам: `assets/archives/legacy-trials-v1.json`.
Современная библиотека и темы от прежних trial-каталогов не зависят.
Christmas v001 сохранена как предыдущая установленная тема для переключения/отката;
найденный в ней пользовательский `SysTextures.zip` сохранён.

Итоги: [docs/CLEANUP.md](docs/CLEANUP.md). История первых экспериментов: `docs/history/`.
