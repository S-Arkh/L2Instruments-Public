# Gracia Epilogue: восстановленный Interface и браузер

## Актуальный комплект

`../../out/gracia/system` — версия без helper с аргументами OpenBrowser,
проверенная в игре на Gracia и HF. Сборка в Windows и все реализованные функции проверены.
[UC API](../../docs/BROWSER_OPEN_API.md) ·
[Отчёт и хеши](../../reports/browser-options-validation.json).
`result-inprocess` и `result` ниже — предыдущие сохранённые комплекты.

## Новый вариант без helper EXE

`result-inprocess/system` — отдельная сборка браузера внутри `ExtensionL2.dll`,
без `GraciaBrowserHost.exe`. Причина прежнего `0x80010108` установлена:
`integrity.dll` блокировал чтение/запись pipe-дескрипторов, используемых WebView2.
Добавлен ограниченный слой совместимости для Mojo-каналов WebView2.

Проверены автоматические тесты кадров/ввода/завершения и запуск в отдельной копии
Gracia: страница отображается поверх логина, браузер закрывается, клиент выходит.
Работа подтверждена. Хеш установленной ExtensionL2.dll совпадает с этой сборкой.
Все реализованные функции проверены в игре.

- [Анализ причины, решение, сборка и установка](../../docs/GRACIA_INPROCESS_BROWSER.md).
- Сборка: `build_inprocess.ps1`.
- Хеши: `result-inprocess/manifest.json`; игровой smoke-test: `inprocess-validation.json`.

Ниже описан прежний, полностью проверенный комплект с helper;
он сохранён в `result/system` для отката.

## История: комплект с helper

`result/system` — комплект, проверенный в игре 29.10.2026. Interface восстановлен на существующем
парсере: 3259 исходных функций, 21326 basic blocks проверены после компиляции;
0 ошибок компиляции, 3 предупреждения о старых именах классов.

Подтверждены загрузка UI и положение Browser поверх окна логина.
Внутрипроцессный WebView2 возвращал `0x80010108` при создании контроллера, включая
чистый профиль. Удержание Environment не устранило сбой. Точная причина разрыва
COM-соединения внутри игры не установлена.

Прежний вариант запускает WebView2/WGC в `GraciaBrowserHost.exe`. Через shared memory
он передаёт BGRA-кадры и принимает команды ввода; ExtensionL2 обновляет игровую
UTexture в UI-потоке, штатный Canvas/D3D9 рисует её. Host не создаёт видимого
браузерного окна на рабочем столе. Граница процессов проверена тестами кадров,
RU/EN-ввода, мыши, сворачивания, звука, popup и закрытия. Подтверждены
изображение, RU/EN, клики, колесо, drag, сворачивание/восстановление, прекращение
звука, закрытие браузера и клиента. После выхода процессы L2 и helper отсутствуют.
Свидетельство и хеши — `game-validation.json`; manifest признаёт игровой тест
только при совпадении всех проверенных бинарников/UI.

## Установка

Семь файлов: `Core.dll`, `ExtensionL2.dll`, `GraciaBrowserHost.exe`, `Interface.u`,
`Interface.xdat`, `WebView2Loader.dll`, `options.config`. Helper должен лежать рядом
с ExtensionL2; отдельно запускать его не требуется. Для обновления предыдущей
версии с уже исправленным порядком окон достаточно заменить ExtensionL2 и добавить
GraciaBrowserHost.exe при закрытой игре.

**Исходники держать вне каталога игры.** Gracia проверяет соседнюю папку
`interface/Classes` и `uclist.int`; при несовпадении удаляет Interface.u и пытается
вызвать `Editor.MakeCommandlet -UIScriptCompile`, что в исследованном клиенте
приводило к assertion в CompileUIScripts. Папку выгрузки переносить, не удалять.

Из этой папки (Windows PowerShell, Python 3):

```powershell
$ClientSystem = Read-Host 'Полный путь к system целевого клиента Gracia'
py -3 install.py --system $ClientSystem --check
py -3 install.py --system $ClientSystem
py -3 install.py --restore 'backups\<каталог, выданный установщиком>'
```

Установщик проверяет профиль Engine/NWindow/D3DDrv, допустимые Core/UI и хеши
комплекта, делает резервную копию и сохраняет существующий options.config.
При откате вновь добавленный helper удаляется, прежние файлы восстанавливаются.
При ручном обновлении сначала сохранить заменяемые файлы.

```json
{"browser":{"startPage":"https://www.youtube.com/"}}
```

Конфигурация перечитывается при новом открытии, ошибочный файл даёт YouTube.
Helper получает собственный WebView-профиль, путь определяется каталогом комплекта.

## Устройство и жизненный цикл

- `browser_transport.cpp`: запуск helper, очередь команд, чтение свежих кадров.
- `browser_host.cpp`: обработка команд и публикация кадров/статуса.
- `browser_ipc.h`: версия протокола, очередь, mutex, BGRA 512×512.
- WebView2/COM и WGC/D3D11 принадлежат STA внутри helper; игровых UObject там нет.
- Скрытие немедленно блокирует выдачу кадров; команды обрабатываются по порядку.
- Смена состояния закрывает страницу; восстановление после сворачивания сохраняет её.
- Helper и его дочерние процессы находятся в Windows Job с kill-on-close:
  завершение игры освобождает их, в DllMain нет ожиданий/COM-вызовов.
- Коды `-30/-31/-32`: запуск IPC/helper, завершение helper, ошибка очереди/синхронизации.
  Старые WebView/WGC-коды передаются из helper без изменения.

## Сборка и проверки

```powershell
.\build.ps1 -ExportedClasses 'D:\путь-вне-игры\Classes'
.\build_native.ps1
py -3 tests\test_bundle.py
py -3 tests\test_recovery_guard.py
```

Полная цепочка: первичное исправление WOTgreal → генерация тел из байткода →
staging SDK/XDAT → UCC → verify_recovery → native/IPC-тесты → упаковка → manifest.
Отчёты: `recovery-validation.json`, `native-validation.json`, `result/manifest.json`.
Native-only сборка не публикует комплект. HF-результат сохраняется отдельно.

`bytecode_sources.py --all` восстанавливает тела с диспетчером `__RecoveredPC`:
адреса исходных переходов становятся case-метками. `verify_recovery.py` сравнивает
выражения/маршруты, инициализацию/выход, флаги, свойства, enum и наследование.
Дополнительная стоимость диспетчера в игре пока не измерена. Texture fixture
исполняет настоящий Engine::Init на тестовом layout, но не заменяет проверку
игрового UObject/Canvas/GC.

## Диагностика в игре

```powershell
powershell -ExecutionPolicy Bypass -File .\diagnose_browser.ps1
```

Открыть Browser, затем закрыть игру. Скрипт использует отдельный профиль и сохраняет
журналы в `tests/browser-diagnostic-*`; рабочие настройки клиента не меняет.
При обычном запуске смотреть `system/web-texture.log` и заголовок окна Browser.
