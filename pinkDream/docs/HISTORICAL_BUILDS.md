# Исторические сборки Scryde

Это результаты исходного рабочего дерева, не готовые файлы публичного клона.
Как создать свою библиотеку и сборку: [README](../README.md#начало-работы-из-чистого-клона).

| Тема | Исторический каталог |
|---|---|
| Christmas v003 — леденцы и гирлянды; гладкие ползунки и края | `builds/scryde/christmas/v003/SysTextures` |
| Halloween v002 — тыквы, паутина, кости; гладкие ползунки и края | `builds/scryde/halloween/v002/SysTextures` |
| Glamour Pink v001 — розовая тема | `builds/scryde/glamour-pink/v001/SysTextures` |

Каждая из этих сборок: 446 текстур / 492 mip-уровня в пяти UTX. Эти конкретные
версии проверялись офлайн и в игре на Scryde. Проверка не распространяется
автоматически на вновь сгенерированные UTX.

Прежние previews:

- `assets/generated/scryde/christmas/v003/previews/highlights.png`;
- `assets/generated/scryde/halloween/v002/previews/highlights.png`;
- `assets/previews/seasonal-scaling-fix.png`;
- соседние `page-*.png` — полное сравнение тем.

В исходном дереве ранние trial-v001…v004 UTX-дубликаты были удалены после
проверки. Их изображения, оригиналы и метаданные были сохранены по хешам
в `assets/archives/legacy-trials-v1.json`. Christmas v001 и найденный в ней
пользовательский `SysTextures.zip` были сохранены. Эти архивы не входят в Git.
Современные темы от прежних trial-каталогов не зависят.

Подробности: [CLEANUP](CLEANUP.md), [VALIDATION](VALIDATION.md),
[установка и откат](THEMES.md).
