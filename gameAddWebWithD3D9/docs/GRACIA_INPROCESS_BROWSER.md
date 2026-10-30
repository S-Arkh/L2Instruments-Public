# Gracia: WebView2 внутри ExtensionL2, без дополнительного EXE

## Результат

Исходная in-process сборка: `profiles/gracia/result-inprocess/system`.
Актуальная подтверждённая версия с аргументами OpenBrowser:
`out/gracia/system` (см. [UC API](BROWSER_OPEN_API.md)).
Браузером управляет `ExtensionL2.dll` внутри процесса клиента; `GraciaBrowserHost.exe`
не поставляется и не запускается. Обычные процессы **msedgewebview2.exe** остаются:
это штатная многопроцессная архитектура WebView2 Runtime.

В отдельной копии Gracia проверено отображение страницы YouTube поверх логина,
закрытие Browser, выход через игровую кнопку Exit и отсутствие оставшихся L2,
helper или WebView-процессов этого клиента. Подтверждена работа в основном клиенте.
Хеш установленной ExtensionL2.dll совпал с опубликованной сборкой.
Сборка в Windows и все реализованные игровые функции также проверены.

Прежний комплект с helper сохранён отдельно в `profiles/gracia/result/system`.

## Что было сломано

Симптом: `CreateCoreWebView2EnvironmentWithOptions` завершается успешно,
но callback создания контроллера получает `0x80010108` (`RPC_E_DISCONNECTED`),
игровое окно Browser показывает код `-22` и чёрную область.

Первая реализация уже имела отдельный STA-поток, `CoInitializeEx`, message loop
и удержание Environment. Повторная реализация этих механизмов не устраняла причину.

### Подтверждённая причина

В исследованном клиенте `integrity.dll` устанавливает detours на `ntdll!NtReadFile`
и `ntdll!NtWriteFile`. Оба обработчика делают следующее:

```text
GetFileType(FileHandle)
if result == FILE_TYPE_PIPE (3):
    return STATUS_ACCESS_DENIED (0xC0000022)
else:
    jump original_function_trampoline
```

WebView2 использует именованные pipes Mojo для связи host ↔ browser Runtime.
В этом клиенте наблюдались имена:

```text
\LOCAL\mojo.<PID клиента>.<TID>.<случайная часть>
```

Поэтому Environment создавался локально, но обмен при создании контроллера
прерывался. В Chromium-логе виден запуск и затем shutdown браузерного процесса.
`0x80010108` — следствие разрыва канала, не доказательство ошибки COM apartment.
Вынесенный helper работал потому, что игровые перехваты в нём отсутствовали.

### Привязка к исследованному бинарнику

`integrity.dll` SHA-256:
`537a9d62171abbe2677425de17f815e25d990351ae12098d7fda31070cde12e0`.

RVA относительно integrity.dll:

| Назначение | RVA |
|---|---|
| Перехват NtWriteFile | `0x113D60` |
| Перехват NtReadFile | `0x113D80` |
| Указатель trampoline NtWriteFile | `0x216444` |
| Указатель trampoline NtReadFile | `0x216440` |

Фрагмент перехвата чтения (image base в файле `0x10000000`):

```asm
10113D80  push dword ptr [esp+4]       ; FileHandle
10113D84  call [101A68A0]              ; GetFileType
10113D8A  cmp eax,3
10113D8D  jne 10113D97
10113D8F  mov eax,0C0000022h
10113D94  ret 24h
10113D97  jmp [10216440]              ; исходный NtReadFile
```

Адреса выше нужны для воспроизводимости анализа. Реализация **не использует
фиксированные адреса ntdll/syscall numbers**: распознаёт текущую цепочку по
модулю, байтам обработчика, импорту GetFileType и сохранённому trampoline.

## Ход проверки гипотез

1. Старый in-process вариант воспроизвёл `0x80010108` в копии клиента.
2. COM-инициализация дала S_OK; FPU control на STA был `0x0009001F`.
3. Environment callback дал S_OK; Runtime — `156.0.4314.50`.
4. Диагностика не зафиксировала уничтожения host HWND до отказа контроллера
   или first-chance исключений в клиенте на этом пути.
5. Отдельная установка DPI awareness на STA не устранила ошибку.
6. Standalone тесты с Core/Engine, Core/Engine/NWindow и Core/Engine/D3DDrv
   проходили: простая загрузка этих DLL сама по себе проблему не создаёт.
7. В живом клиенте обнаружены переходы NtReadFile/NtWriteFile в integrity.dll;
   дизассемблирование показало безусловный отказ для FILE_TYPE_PIPE.
8. Обычный CreatePipe + WriteFile внутри клиента вернул ERROR_ACCESS_DENIED (5).
9. После установки ограниченной совместимости контроллер создался и пошли кадры.
10. Синтетический fixture воспроизвёл ту же блокировку: без совместимости тест
    WebView падает, с ней весь набор кадров/ввода проходит, обычный pipe остаётся
    заблокированным.

Свидетельства находятся в `profiles/gracia/tests/inprocess-client-20261029-040141`,
`profiles/gracia/tests/inprocess-20261029-035839`, `profiles/gracia/tests/pipe-compat-*` и
`profiles/gracia/tests/inprocess-exit-*`. Первые диагностические журналы накопительные:
различайте запуски по PID и tick. Итоговая привязка — `profiles/gracia/inprocess-validation.json`.

## Решение

### Потоки и отрисовка

```text
L2.exe
  игровой UI-поток → native API ExtensionL2 → очередь команд
  STA WebView2 → browser Runtime → WGC/D3D11 → BGRA буфер
  игровой UI-поток → UTexture → штатный Canvas/D3D9
```

Используется прежний внутрипроцессный код WebView/WGC, без shared-memory транспорта
и запуска GraciaBrowserHost. COM-объекты остаются на STA; UObject обновляется
в игровом UI-потоке. Native API и UnrealScript/XDAT интерфейс сохранены.

### Совместимость pipe I/O

Файлы: `profiles/gracia/inprocess/pipe_compat.h/.cpp`.

После загрузки Environment, до запроса контроллера:

1. Находится модуль реализации Environment (`EmbeddedBrowserWebView.dll`).
2. Проверяется, что detours принадлежат integrity.dll и точно соответствуют
   наблюдаемому обработчику FILE_TYPE_PIPE. Проверяются GetFileType и trampoline.
3. Только в таблице импортов модуля WebView заменяются указатели ReadFile/WriteFile.
4. Обёртка проверяет тип дескриптора и имя через NtQueryInformationFile.
5. Для `\mojo.<текущий PID>.…` / `\LOCAL\mojo.<текущий PID>.…` вызывается сохранённый
   оригинальный NT trampoline. Поддержаны overlapped I/O, IO_STATUS_BLOCK,
   контекст IOCP, event и перевод NTSTATUS в Win32 error.
6. Для любого другого дескриптора вызывается прежний Win32 ReadFile/WriteFile.

Код ntdll и integrity.dll не переписывается. Файлы/пакеты игры и остальные
pipe-операции сохраняют прежний путь вызова. Собственная DLL закрепляется до
завершения процесса, чтобы IAT-обёртки не стали недействительными после FreeLibrary.

Это совместимость с конкретной изученной схемой перехвата. При неизвестной
схеме распознавание отказывается менять IAT и пишет диагностику; произвольный
новый integrity.dll или новый механизм I/O Runtime требует проверки.

### Завершение

При штатном shutdown закрываются controller/WGC на STA. При завершении процесса
DllMain вызывает AbandonOnProcessExit: отсоединяет удерживаемые COM/WinRT ссылки
без Release, ожиданий и межпоточных вызовов под loader lock. Проверен также
ExitProcess при активных WebView/WGC в DLL и включённом синтетическом pipe-блокере.

## Сборка Visual Studio 2022

В `gracia`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_inprocess.ps1
```

Скрипт подготавливает адаптеры, создаёт `build-inprocess` с
`-DGRACIA_INPROCESS_BROWSER=ON`, собирает Win32 Release, запускает тесты и
формирует `result-inprocess/system` + отдельный manifest.

По умолчанию прежняя CMake-конфигурация (`GRACIA_INPROCESS_BROWSER=OFF`)
продолжает собирать транспорт helper. `result/system` не перепаковывается.

Файлы реализации:

- `inprocess/web_frames.cpp`: включение общего WebView-кода, точка установки
  совместимости, журнал и дополнительные диагностические перехваты вызовов.
- `inprocess/pipe_compat.cpp`: проверка detour, IAT-адаптеры ReadFile/WriteFile.
- `native/web_frames.cpp`, `native/gpu_capture.cpp`: генерируемые общие исходники;
  их изменения должны проходить через preparation/adapter, иначе будут затёрты.
- `tests/pipe_block_fixture.cpp`: отдельная **тестовая** integrity.dll с имитацией
  наблюдаемого отказа; никогда не копируется в комплект клиента.

## Установка новой сборки

В комплекте шесть файлов:

```text
Core.dll
ExtensionL2.dll
Interface.u
Interface.xdat
WebView2Loader.dll
options.config
```

Для уже установленного рабочего Gracia-комплекта достаточно при закрытом клиенте
сохранить прежнюю `ExtensionL2.dll` и заменить её из `result-inprocess/system`.
`GraciaBrowserHost.exe` больше не нужен: можно перенести его в резервную папку
вместе со старой DLL. Собственный `options.config` сохраните.

Для чистой установки используются все шесть файлов этого каталога с резервным
копированием заменяемых. Старый `install.py` обслуживает **helper-комплект**;
его нельзя использовать для установки нового варианта без адаптации установщика.
Исходники `interface/Classes` по-прежнему должны находиться вне каталога клиента.

Первичная проверка новой DLL выполнялась в изолированной копии без установки
в основной клиент. Последующая работа в основном клиенте подтверждена.

## Проверки

Последняя сборка:

| Проверка | Результат |
|---|---|
| Без совместимости, синтетический pipe-блокер | Ожидаемый отказ WebView |
| С совместимостью | Полный frame/input suite проходит |
| Обычный pipe после установки совместимости | Остаётся заблокированным |
| Анимация, смена страницы, fresh frames | Пройдены |
| Click, RU/EN, Windows RU layout, Unicode bridge, drag, wheel | Пройдены в native host |
| Focus loss, hide/resume, mute, close/unload, popup/alert | Пройдены в native host |
| ExitProcess с активными WebView/WGC в DLL | Пройден |
| Реальный Gracia в копии, без helper | Страница отображается; Browser/клиент закрываются |
| Работа новой DLL в основном клиенте | Подтверждена; установленный хеш совпал |

Не переносите автоматически прежний `game-validation.json` на новую DLL:
его хеши относятся к helper-варианту. Для новой версии создан отдельный
`inprocess-validation.json`; в manifest отмечено `user_confirmed_working:true`.
`full_user_game_validation:false` означает отсутствие отдельного отчёта по всем
расширенным сценариям на момент создания отчёта. Текущий статус: все реализованные
функции проверены в игре; исторические поля отчёта относятся к прежнему этапу.

## Диагностика и дальнейшие изменения

- `system/web-texture.log`: Environment, controller, ошибки WGC/navigation.
- `system/inprocess-diagnostic.log`: Runtime, совместимость, первые pipe-операции.
- `system/browser-performance.json`: свежие кадры и стоимость CPU readback/copy.
- `GRACIA_WEBVIEW_DIAGNOSTICS=1`: расширенный дамп модулей/API и first-chance событий.
- `GRACIA_WEBVIEW_PIPE_COMPAT=0`: отключение совместимости для контрольного опыта.
- `GRACIA_TEST_DPI=1`: только исследовательский опыт с DPI контекстом STA;
  в обычном запуске не используется и не требуется.

Переменные задаются процессу диагностического запуска, не системно.
Дополнительный Chromium logging включается через `-ChromiumLog` у тестового
restart-скрипта; при исследовании он создавал консоль Runtime, поэтому обычная
сборка/запуск его не включает.

Для повторения игрового smoke-test `tests/prepare_inprocess_client.ps1` создаёт
копию system и junctions к большим ресурсным каталогам; исходный клиент не меняет.
`tests/interact_inprocess_client.ps1` выбирает окно **по PID и заголовку Lineage II**:
Process.MainWindowHandle после открытия браузера может указывать на offscreen
capture host, поэтому для автоматизации он непригоден.

При расширении совместимости проверять: namespace Mojo, PID, lifetime IAT,
overlapped/IOCP семантику, отказ для посторонних дескрипторов и выход при активной
странице. Не заменять этот адаптер глобальным отключением всех detours.
