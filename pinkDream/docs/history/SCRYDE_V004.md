# Scryde: trial-v004 — World Trade и мини-радар

> Исторический отчёт; прежние пути удалены после архивации изображений.
> Актуальные комплекты: [темы](../THEMES.md).

**446 текстур, 199 новых** относительно v003, в пяти UTX.

World Trade: собственные рамки и фоны, вкладки, поля ввода, списки, чекбоксы,
кнопки покупки, обновления и возврата, состояния и кадры анимации подсветки кнопок.
Мини-радар: рамка Scryde из patch, кольцо/фон, кнопки масштаба и настроек,
дополнительные кнопки возле радара и варианты старого оформления L2UI/CH3.
Маркеры целей/партии/квестов, карта местности и значки валют/категорий товара
сохраняют исходные цвета. Их различимость не зависит от розовой темы.

Предпросмотр: `assets/previews/scryde-trial-v004-trade-radar.png`.
Полный лист: `assets/previews/scryde-trial-v004.png`.

## Установка поверх v003

Закройте игру и лаунчер. PowerShell из каталога pinkDream:

```powershell
$py = '..\interface_editor\dist\windows\runtime\python.exe'
$ClientRoot = Read-Host 'Полный путь к корню Scryde, содержащему SysTextures'
& $py tools\install.py install --client $ClientRoot --bundle builds\scryde\trial-v004 --check
& $py tools\install.py install --client $ClientRoot --bundle builds\scryde\trial-v004 --backup backups\scryde-trial-v004
```

Откат возвращает v003:

```powershell
& $py tools\install.py rollback --backup backups\scryde-trial-v004
```

## Проверки

446 текстур / 492 mip-уровня. Все 247 предыдущих ресурсов сохранены без
повторного окрашивания. Проверены хеши PNG/TGA, совпадение с декодированными
UTX и alpha каждого mip. Вне новых pixel payloads пакеты неизменны.
Настоящий комплект установлен и откачен на изолированной копии.
Read-only --check установленного клиента прошёл через Windows Python.
На момент подготовки v004 игровой тест ещё не был выполнен; основной клиент
при подготовке не изменялся. Актуальные темы проверены в Scryde;
текущий статус — в [VALIDATION.md](../VALIDATION.md).
Отчёт: `profiles/scryde/validation-v004.json`.

## Воспроизведение

Вход можно брать из сохранённой сборки, без зависимости от установленного клиента:

```sh
python tools/build_trial.py --profile scryde --revision trial-v005 --base-bundle builds/scryde/trial-v003 --client builds/scryde/trial-v003
python tools/verify_bundle.py --bundle builds/scryde/trial-v004 --base-bundle builds/scryde/trial-v003 --temp-root "${TMPDIR:-/tmp}" --report profiles/scryde/validation-v004-new.json
```

Последняя команда для Linux: используется `$TMPDIR` или `/tmp`, если переменная
не задана. В PowerShell замените `"${TMPDIR:-/tmp}"` на `([System.IO.Path]::GetTempPath())`.
Храните предыдущие версии: manifests переиспользуют ранее сохранённые изображения.
