КОМПИЛЯТОР UNREALSCRIPT / ucc64

Windows + Windows PowerShell 5.1. Установка Python/Visual Studio не нужна.
Переносите всю папку целиком в короткий путь: старый SDK ограничивает длину путей.

ГОТОВЫЕ ПРОФИЛИ INTERFACE
  Compile_Gracia_152.cmd    — Gracia Epilogue, протокол 152.
  Compile_HighFive_268.cmd  — High Five, протокол 268.
  Compile_Japan_591.cmd     — Japan, протокол 591.
  Compile_Korea_606.cmd     — Korea, протокол 606.
Это командные файлы запуска, а не отдельные компиляторы.
Исходники: Profiles\<профиль>\Classes.
Результат при PASS: Profiles\<профиль>\Output\Interface.u.
Лог попытки: Profiles\<профиль>\Logs\<номер сборки>\compiler.log.
Статус проверки поставленных исходников указан в BUILD_STATUS.txt.

СВОИ ИСХОДНИКИ
Положите *.uc одного пакета в корневую Classes и запустите Compile.cmd.
По умолчанию получится Output\Interface.u. Другое имя:
  Compile.cmd -Package MyPackage
Кодировка исходников: UTF-8 либо UTF-16 с BOM. Пустая Classes выдаёт FAIL.
Дополнительные готовые .u: Dependencies; имена без .u, в порядке зависимостей:
Dependencies.txt. Для профилей эти каталоги/списки находятся внутри профиля.

При ошибке прежний файл в Output не является результатом новой попытки.
Смотрите свежий Logs\<номер сборки>\result.json. Work содержит рабочие копии;
после окончания сборки старые Work/Logs можно удалить.

Дополнительные режимы для своих исходников:
  Compile.cmd -ClientSort -ScopedEnumCasts
  Compile.cmd -ClientSort -ScopedEnumCasts -EnumProfile korea290
Готовые Japan/Korea включают нужные режимы автоматически. Имя korea290 —
историческое имя настройки; протокол Korea — 606, Japan — 591.

SDK\System и Profiles\<профиль>\CompilerDependencies содержат зависимости
компилятора. Не заменяйте их клиентскими DLL/базовыми .u. Это подготовленный
SDK, а не универсальная поддержка всех native-классов каждого клиента.
Для Interface используется сохранённый в пакетах исходный ScriptText, где он
доступен; при его отсутствии — восстановление из байткода. Сборка не доказывает
полного совпадения метаданных или работы в игре. Результат — обычный .u,
без клиентского XOR-конверта и без подмены версии пакета.
Протоколы указаны по сохранённым проверкам -L2ProtocolVersion.

Без паузы, для автоматизации:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Compile.ps1 -Package MyPackage
Код выхода: 0 — успех, 1 — ошибка. Для профиля добавьте -Profile Korea_606
(либо другое имя профиля из списка выше).
