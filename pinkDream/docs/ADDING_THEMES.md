# Техническое руководство: новые темы и профили клиентов

## 1. Архитектура

Тема задаёт оформление, профиль — клиентские пакеты и исходные ресурсы.
Рендерер не должен читать клиентские каталоги или знать название Scryde.
Связь: **профиль → исходная библиотека → рецепт темы → новая версия → проверка → установка**.

| Модуль | Ответственность |
|---|---|
| `inventory.py` | Read-only таблицы UTX, хеши, оболочки |
| `texture.py` | Tagged properties, material serialization, mip layout, декодирование |
| `create_library.py` | Новая библиотека непосредственно из стандартного клиента |
| `import_library.py` | Миграция старых trial-изображений в библиотеку v2 |
| `asset_store.py` | Immutable content-addressed store, SHA-256, атомарная публикация |
| `theme_render.py` | RGB-генерация по рецепту и роли ресурса |
| `build_theme.py` | Импорт изображений, mipmaps, UTX, manifests, snapshots, previews |
| `library.py` | Список релизов и экспорт PNG для ручных правок |
| `verify_theme.py` | Проверка loose/CAS-файлов, alpha, UTX и установки/отката |
| `install.py` | Хеш-проверки, backup, переключение тем, откат |
| `cleanup_legacy.py` | Однократная проверяемая очистка старых trial-дубликатов |

`generator/generate.py` — независимая библиотека концептов, не упаковщик UTX.
`build_trial.py`/`verify_bundle.py` — исторический конвейер, новые темы им не собирать.

## 2. Рецепт темы

Расположение: `themes/<id>/theme.json` (для существующей розовой темы — recipe.json).
Минимальный контракт:

```json
{
  "schema": 2,
  "id": "my-theme",
  "algorithm": "my-theme-v1",
  "palette": {"shadow": "#101020", "accent": "#f08030"},
  "decoration": {},
  "alpha_policy": "preserve-source-exactly"
}
```

ID профиля, темы и ревизии: `[A-Za-z0-9_-]+`. Изменение алгоритма обозначать новым
algorithm/version; существующие опубликованные рецепты сохраняются в снимках релизов.
Параметры валидировать при чтении рендерером. Избегать времени, внешнего состояния
и нефиксированной случайности. Если нужна случайность — seed рецепта + полный
путь ресурса, без глобального состояния RNG.

## 3. Контракт рендерера

```python
render(source: PIL.Image.Image, resource: str, recipe: dict,
       role_override: str | None = None) -> tuple[Image.Image, str]
```

Вход — **стандартный RGBA**, а не результат предыдущей темы. Возврат — изображение
того же размера с побайтово сохранённой alpha и роль для отчёта/предпросмотра.
В `render` добавить ветку `algorithm`; общие функции вынести отдельно при расширении.
Входное изображение не изменять in-place. Нельзя менять геометрию окна или UV.

| Роль | Допустимое оформление |
|---|---|
| `title` | Украшения верхней рамки: гирлянды, тыквы, небольшие подвесы |
| `trim` | Контурные полосы, орнамент; учитывать повторение узких тайлов |
| `stretch` | Только однотонная цветовая гамма исходного рельефа, без нового рисунка: тайлы, края перетягивания, дорожки/бегунки |
| `plain-control` | Стрелки прокрутки: исходный читаемый символ и рельеф, без декоративных полос/паутины |
| `control` | Акцентные края и состояния; центральный символ должен читаться |
| `radar` | Декоративная оболочка, без изменения картографических маркеров |
| `surface` | Спокойный фон, низкоконтрастная текстура |
| `atlas` | Консервативное изменение оттенка; никаких рисунков поперёк отдельных слотов |

По умолчанию роль определяется по имени. Для другого клиента задавайте `roles`
в selection — они попадут в библиотеку и перекроют эвристику. Нельзя считать,
что одинаковое имя ресурса во всех клиентах имеет одинаковое назначение.
Особенно проверять slice/tile рамки, состояния кнопок и встроенные надписи.
Имена scrollbar/windowscroll/slider/sizecontrol и узкие сегменты frame
распознаются **до** общего правила кнопок и заголовков. Иначе маленький тайл
получит рисунок, который превратится в повторяющиеся обрывки при растягивании.
Визуальную проверку выполнять не только на отдельном PNG, но и при повторении
вдоль рабочей оси и масштабировании бегунка. Пример: `tools/preview_scaling.py`.

## 4. Подключение другого клиента

1. Создать `profiles/<client>/profile.json`: id, корни клиента, `packages` с путями
   вида `SysTextures/Foo.utx`, статус и game_tested=false.
2. Инвентаризировать **оригинальный** клиент. В CLI inventory сейчас перечислены
   scryde/high-five/gracia; для нового id расширить choices или вызывать `inspect`.
3. Выбрать только интерфейсные ресурсы и состояния, зафиксировать selection:

```json
{
  "schema": 1,
  "rules": {"SysTextures/L2UI_CT1.utx": ["L2UI_CT1.Frames.*"]},
  "roles": {"L2UI_CT1.Frames.Frame_DF_Hor_Large_*": "title"}
}
```

4. Создать свою исходную библиотеку:

```sh
python tools/inventory.py --profile high-five --client "D:/path/to/HF" --output profiles/high-five/inventory-v001.json
python tools/create_library.py --profile high-five --client "D:/path/to/HF" --inventory profiles/high-five/inventory-v001.json --selection profiles/high-five/selection.json --revision standard-v001
```

Команды показывают контракт; selection HF ещё нужно подготовить по его ресурсам.
Импорт сверяет входные хеши, сохраняет полные исходные пакеты и все mip payloads.
Неподдерживаемая сериализация/формат останавливает импорт, а не угадывается.

5. Собрать любую общую тему с этой библиотекой, затем выполнить проверки и игру.
Нельзя устанавливать UTX Scryde в HF/Gracia: переиспользуется рецепт, не пакет.

### Формат библиотеки schema=2

- `profile`, `revision`, `source_kind` — происхождение.
- `packages[]`: `path`, `standard_sha256`, `container` (CAS reference).
- `textures[]`: `resource`, `package`, `format` (число UE2), `size`, `standard_png`,
  необязательный `role`, `mips[]` с `size`, `offset`, `reference_payload`.
- CAS reference: `path`, `sha256`, `bytes`. Объекты размещаются только внутри
  `assets/objects/sha256/<prefix>/<hash>.<ext>`; чтение проверяет хеш.

Существующая Scryde-библиотека мигрирована из стандартных PNG и layout trial-v004:
в ней сохранена оригинальная alpha, но RGB нижних исходных mips ранее не архивировался.
Новый `create_library.py` при прямом импорте сохраняет исходные данные всех уровней.

## 5. Сборка и импорт ручных изображений

```sh
python tools/build_theme.py --library assets/libraries/scryde/standard-ui-v001/manifest.json --theme themes/halloween/theme.json --revision v002
python tools/library.py export --manifest assets/generated/scryde/halloween/v001/manifest.json --kind editable --out work/halloween-edit
python tools/build_theme.py --library assets/libraries/scryde/standard-ui-v001/manifest.json --theme themes/halloween/theme.json --revision custom-v001 --overrides work/halloween-edit
```

Имена PNG в overrides — полные пути ресурсов. Можно оставить только изменённые
файлы. Размеры/alpha обязаны совпасть с стандартом; неизвестные имена запрещены.
Ручные правки сохраняются как объекты с provenance, не заменяют прежние релизы.

Обработка mip: декорировать верхний уровень → LANCZOS resize RGB → вернуть
оригинальную alpha соответствующего mip → encode → decode и проверить alpha.
BGRA8 сохраняется напрямую. DXT3/DXT5: компрессия Pillow, исходные 8-байтовые
alpha-блоки каждого 16-байтового блока копируются обратно. Малые mip дополняются
до 4×4 на кодировании. Произвольный импорт DXT1/P8 пока не поддержан.

UTX-патчер меняет только существующие pixel payloads, без изменения их длины,
формата, числа mip, таблиц, смещений и материалов. Оболочка пакета сохраняется.

## 6. Версии и воспроизводимость

- Уникальный путь: `builds/<profile>/<theme>/<revision>` и аналогичный generated.
- Публикация через `.partial`; существующие каталоги запрещено перезаписывать.
- В generated сохраняются standard/editable/packed PNG, TGA, все mip PNG,
  recipe/library, manifests, снимки Python и постраничные previews.
- Начиная с новых сборок Christmas v002/Halloween v001 входные JSON сохраняются
  побайтово, их хеши совпадают с snapshot. В ранних v001 JSON нормализовался.
- Копии скриптов — source snapshot; ROOT в них относителен к tools. Для повторения
  восстановить snapshot в `tools/` отдельной копии проекта, а не запускать его
  непосредственно из глубоко вложенного каталога generated.
- Хранить Pillow из requirements и исходную библиотеку. Релиз не зависит от
  наличия прошлых trial-UTX после миграции, но зависит от своих CAS-объектов.
- Не удалять CAS по времени/имени: сначала построить граф ссылок из всех
  library/generated/archive manifests. Текущая очистка store не удаляет объекты.

## 7. Обязательные проверки

```sh
python -m unittest discover -s tools -p "test_*.py" -v
python tools/verify_theme.py --bundle builds/scryde/halloween/v001 --assets assets/generated/scryde/halloween/v001 --temp-root "<TEMP>" --report profiles/scryde/halloween-check.json
```

`<TEMP>` замените существующим временным каталогом. В PowerShell вместо
`"<TEMP>"` можно передать `([System.IO.Path]::GetTempPath())`, в Linux — `"${TMPDIR:-/tmp}"`.
Проверить: все loose/CAS хеши, decoded PNG/TGA, alpha каждого mip, неизменность
экспортов и байтов вне payloads, установку/откат на копии. Добавлять тесты для
новой рискованной логики: правила alpha, границы атласов, форматы, состояние отката.

Визуально посмотреть highlights и страницы: отсутствие вылезания декора,
читаемость кнопок, согласованные состояния, швы тайлов. Затем игровой тест:
допуск UTX, масштаб UI, рамки/resize, инвентарь/слоты, чат, World Trade, радар.
`game_tested=true` только после подтверждения именно этой версии и её хешей.

## 8. Установка и переключение

`accepted_input_sha256` включает исходные пакеты и layout-референс библиотеки.
Для перехода с другой темы использовать `--from-bundle`: installer сверяет
одинаковую библиотеку, профиль, набор пакетов и hashes предыдущей темы.
Backup делается до первой замены; журнал фиксирует реальные прежние hashes.
Откат возвращает именно предыдущее состояние, включая другую установленную тему.
Чужие изменения клиента/backup отклоняются до восстановления.

## 9. Очистка и история

`assets/archives/legacy-trials-v1.json` сохраняет список прежних файлов и ссылки на
их содержимое в CAS. Старые UTX-дубликаты удаляются только при совпадении с
их manifests; архив старых изображений остаётся доступен. Неизвестные/изменённые
UTX и посторонние файлы не удаляются. Backups, рабочие правки, независимые библиотеки
и пригодные концепты не относятся к мусору.
