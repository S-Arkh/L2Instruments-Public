# Credit → отчёт native int64 в test.txt

**Публикационная копия:** включён сценарий `build.py`; `src/Classes` и `result`
создаются локально из внешних входных данных. Для настройки используйте
[общую инструкцию](../docs/BUILD.md#пример-credit). Ниже описан исходный эталонный
комплект и его исторические проверки, а не содержимое Git-репозитория.

Сборка в Windows, кнопка Credit и native INT64/file-I/O проверены в целевом
игровом клиенте. На Scryde это подтверждение не распространяется.

## Исходники и результат

- `src/Classes/` — 253 класса Interface для компиляции.
- `src/Classes/LoginMenuWnd.uc` — изменён только обработчик OnClickButton, ветка btnCredit.
- `result/ExtensionL2.dll` — 10 функций, включая чтение/запись файлов.
- `result/ExtensionL2.u` — соответствующий API и тестовый класс.
- `result/Interface.u` — интерфейс с изменённым действием Credit.
- `result/Core.dll` — проверенный патч родной Core Clear HF для автоподключения расширения.

Нажатие Credit выполняет:

```uc
if (!class'ExtensionL2API'.static.WriteTextFile("test.txt", "", class'ExtensionL2Tests'.static.Int64Report()))
    ShowMessageInLogin("Cannot write test.txt. Error: " $ string(class'ExtensionL2API'.static.GetFileError()));
```

Переход в CreditState и InitCreditState удалены из этой ветки. Файл создаётся
рядом с ExtensionL2.dll. Каждое нажатие заново выполняет native-вызовы и
перезаписывает отчёт (UTF-8, строки CRLF). При ошибке записи отображается её код.

Отчёт реализован в `dll/ExtensionL2/Classes/ExtensionL2Tests.uc` (от корня rebuild).
Значения actual получаются из вызовов DLL; expected служат только для сравнения.
При успешной работе ожидается:

```text
Credit button clicked.
ExtensionL2 native int64 tests
PASS | 2147483647 + 1 | actual=2147483648 | expected=2147483648
PASS | 5000000000 + 10 | actual=5000000010 | expected=5000000010
PASS | -5000000000 - 10 | actual=-5000000010 | expected=-5000000010
PASS | MAX + 1 (saturate) | actual=9223372036854775807 | expected=9223372036854775807
PASS | MIN - 1 (saturate) | actual=-9223372036854775808 | expected=-9223372036854775808
PASS | MAX + MIN | actual=-1 | expected=-1
PASS | 0 + 0 | actual=0 | expected=0
PASS | nested Add(Add(MAX, 1), -1) | actual=9223372036854775806 | expected=9223372036854775806
SelfTest=True
```

При несовпадении числа соответствующая строка получит FAIL и покажет фактический результат.

## Установка

`<HF_CLIENT>` — корень целевого клиента Clear HF. В командах PowerShell
`$ClientSystem` — полный путь к его подпапке `system`.

При закрытом клиенте сохраните прежние файлы и скопируйте из `result` в
`<HF_CLIENT>\system` четыре файла:

```text
Core.dll
ExtensionL2.dll
ExtensionL2.u
Interface.u
```

Запустите этот клиент и нажмите Credit в меню входа. Ожидаемый файл:
`<HF_CLIENT>\system\test.txt`.
Этот комплект сделан под предоставленный Clear HF и его исходный Interface.
Для обновления предыдущего рабочего теста достаточно заменить **Interface.u и
ExtensionL2.u** из нового result: отчёт добавлен в UC, файловая DLL та же.

Проверка после копирования, из `rebuild`:

```powershell
$ClientSystem = Read-Host 'Полный путь к system целевого клиента Clear HF'
py -3 dll/tools/check_installation.py $ClientSystem --manifest test_interfaces/result/bundle.json
```

## Пересборка

Из `rebuild`:

```powershell
.\dll\build.ps1
$ClientSystem = Read-Host 'Полный путь к эталонному system Clear HF с оригинальным Interface'
py -3 test_interfaces/build.py --client-system $ClientSystem --work test_interfaces/build-new --out test_interfaces/result-new
```

Для пересборки после установки изменённого Interface укажите в `--client-system`
эталонный System того же клиента с оригинальным Interface: сценарий проверяет,
что исходный пакет совпадает с тем, на основе которого подготовлены Classes.

Параметры `build.py`:

- `--native-build`: каталог свежей DLL и трёх EXE; по умолчанию dll/build/Release.
- `--launcher`: UCC launcher; по умолчанию int64/dist/win32/ucc64.exe.
- `--client-core`: оригинальная Core; по умолчанию `L2_CLEAR_HF_SYSTEM/Core.dll`.
- `--reference-package`: эталон Interface.u; по умолчанию из `L2_CLIENT_PACKAGES`.
- `--client-system`: обязательный целевой System с исходным Interface.
- `--work`: новый compiler workspace; по умолчанию test_interfaces/build.
- `--out`: каталог публикации; по умолчанию test_interfaces/result.
- `--replace`: разрешает заменить результат только после успешных проверок;
  прежняя папка переносится в backups с датой.
- `--wine`: путь к Wine для Linux; окружение WINEPREFIX задаётся отдельно.

При первом запуске сценарий создаёт src/Classes из подготовленных исходников
и меняет Credit. Если Classes уже существует, использует текущие файлы без
перегенерации. Исходная кодировка и байты остальных классов сохраняются.
Этот тестовый сценарий требует, чтобы единственное неэквивалентное изменение
байткода было в LoginMenuWnd.OnClickButton.

## Выполненные проверки

- MinGW-w64 x86: DLL и тестовые EXE собраны.
- UCC: 0 ошибок, 35 прежних предупреждений исходного Interface.
- 253 класса; 3715 функций совпадают по нормализованным инструкциям,
  76 эквивалентны после folding byte-констант; изменён только OnClickButton.
- DLL/UC API совпадает, импортирован класс ExtensionL2.ExtensionL2API.
- Loader Core+Engine и VM-пробы прошли в Wine на оригинальной и патченной Core.
- В байткоде Credit проверены вызов WriteTextFile, путь test.txt и вызов Int64Report.
- Native int64 и файловые операции проверены в VM и в игре; полный UC-отчёт
  с вызовами script-функций проверен нажатием Credit в клиенте.
- Логи, сравнение и хеши находятся в локальном result. Игровой UI и действие Credit проверены в исходном проекте.

Описание файлового API: [dll/FILE_IO.md](../dll/FILE_IO.md).
