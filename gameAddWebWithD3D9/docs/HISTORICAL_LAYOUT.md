# Исторические браузерные комплекты

Эта страница описывает исходное рабочее дерево. Перечисленные готовые каталоги
не включены в Git; для чистого клона используйте [PUBLICATION_BUILD](PUBLICATION_BUILD.md).

- `out/<клиент>/system` — прежние пользовательские сборки с Browser Options.
- `profiles/<клиент>/result` — предыдущий базовый комплект; у Gracia он содержал
  helper `GraciaBrowserHost.exe`.
- `profiles/gracia/result-inprocess` — предыдущий вариант без helper.
- `profiles/<клиент>/archive/pre-layout-build*` — сохранённые в исходном дереве
  старые CMake-каталоги с абсолютным cache; для новых сборок они не подходят.

Прежние `install.py` обслуживают `result`, а не `out`. Для обновления именно
совместимого ранее установленного комплекта на Browser Options заменялся
Interface.u из `out/<клиент>/system` при закрытом клиенте и с сохранением прежнего
файла. Это не инструкция установки native-DLL из чистого клона: ей нужны
согласованные `.u`, Core и клиентские ресурсы.

Подтверждения прежних запусков: [перенос](../reports/profile-layout-validation.json),
[Browser Options](../reports/browser-options-validation.json). Новая сборка
требует собственных проверок; исторические хеши на неё не распространяются.
