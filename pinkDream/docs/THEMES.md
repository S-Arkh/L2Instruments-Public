# Готовые темы Scryde и установка

## Актуальные версии

| Тема | Комплект | Оформление |
|---|---|---|
| Christmas | `builds/scryde/christmas/v003` | Леденцовые заголовки и гирлянды; гладкие зелёные ползунки/края |
| Halloween | `builds/scryde/halloween/v002` | Тыквы, паутина, кости; гладкие сливовые ползунки/края |
| Glamour Pink | `builds/scryde/glamour-pink/v001` | Розовые панели и акценты |

Файлы для ручной замены находятся в подпапке `SysTextures`. Копировать в
`<SCRYDE_CLIENT>\SysTextures` при закрытой игре, предварительно сохранив
заменяемые пять UTX. Текстурные комплекты не содержат Interface.u/Interface.xdat.

`<SCRYDE_CLIENT>` — корень установки Scryde с папками `SysTextures` и `Scryde`.
В примерах PowerShell он задаётся переменной `$ClientRoot`.

По 446 текстур / 492 mip-уровня в каждой теме. Все строятся независимо из
стандартных изображений. Сохраняются размеры, alpha, UV/layout и другие ресурсы.
Готовые PNG/TGA и страницы сравнения:
`assets/generated/scryde/<theme>/<revision>/previews/highlights.png` и `page-*.png`.

## Обновление установленной темы

Проверено по хешам при подготовке исправления: в клиенте находится Halloween v001.
Инструкции для обеих тем: [SMOOTH_CONTROLS.md](SMOOTH_CONTROLS.md).
Для установки новой версии закройте игру и лаунчер. PowerShell из pinkDream:

```powershell
$py = '..\interface_editor\dist\windows\runtime\python.exe'
$ClientRoot = Read-Host 'Полный путь к корню Scryde, содержащему SysTextures'
& $py tools\install.py install --client $ClientRoot --bundle builds\scryde\halloween\v002 --from-bundle builds\scryde\halloween\v001 --check
& $py tools\install.py install --client $ClientRoot --bundle builds\scryde\halloween\v002 --from-bundle builds\scryde\halloween\v001 --backup backups\scryde-halloween-v002
```

Переход с установленной Halloween v001 на исправленную Christmas:

```powershell
& $py tools\install.py install --client $ClientRoot --bundle builds\scryde\christmas\v003 --from-bundle builds\scryde\halloween\v001 --backup backups\scryde-christmas-v003
```

Если установлена другая версия — в `--from-bundle` укажите её.
То же правило для перехода между любыми темами одной исходной библиотеки.
Для полностью исходного клиента или старой trial-v004 `--from-bundle` не нужен:
их хеши уже включены в manifests. Другие версии клиента требуют новой библиотеки.

## Откат

```powershell
& $py tools\install.py rollback --backup backups\scryde-halloween-v002
```

Укажите backup именно нужной установки. Откат возвращает фактическое прежнее
состояние (например, Christmas v001), а не обязательно исходный UI.
Установщик проверяет хеши, делает все backup до замены и ведёт журнал. Если
лаунчер обновил пакеты или есть поздние ручные изменения, откат останавливается.

## Статус проверок

Обе новые сборки прошли повторное чтение UTX, сравнение PNG/TGA и alpha всех mips,
проверку байтов вне payloads, реальную установку/откат на изолированной копии.
Отчёты для исправленных версий: `profiles/scryde/christmas-v003-validation.json`,
`profiles/scryde/halloween-v002-validation.json`.
Установка из полностью исходного клиента предусмотрена по хешам, но полной
оригинальной копии для этого игрового/установочного теста сейчас нет.
Сборка в Windows и игровая проверка актуальных тем выполнены, включая
растягивание и повторение рамок. Работа на Scryde подтверждена.

## Разработка и переиспользование

[ADDING_THEMES.md](ADDING_THEMES.md) описывает рецепты, роли, другие клиенты,
импорт изображений, версии, mipmaps, ручные правки и контроль качества.

```sh
python tools/library.py export --manifest assets/generated/scryde/halloween/v001/manifest.json --kind editable --out work/halloween-edit
python tools/build_theme.py --library assets/libraries/scryde/standard-ui-v001/manifest.json --theme themes/halloween/theme.json --revision custom-v001 --overrides work/halloween-edit
```

Редактируемые PNG сохраняются под полными именами ресурсов, размеры и alpha
не меняются. Новый релиз не перезаписывает старые изображения или ручные правки.
