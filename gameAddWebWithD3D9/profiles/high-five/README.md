# High Five REVISION 268 EN

Текущий комплект: `../../out/high-five/system`.
Подтверждена работа сборки с аргументами OpenBrowser на High Five
и Gracia. Сборка в Windows и все реализованные функции проверены в игре.
[Подтверждение и хеши](../../reports/browser-options-validation.json).

- [UC API](../../docs/BROWSER_OPEN_API.md): URL и скрытие четырёх элементов панели.
- `Classes/BrowserWnd.uc` — общий исходник окна для HF и Gracia.
- `native/`, `stage/`, `workspace/` — native-код и подготовленные продукты сборки.
- `result/` — предыдущий базовый комплект; install.py использует его.
- `../../out/high-five/` — актуальный комплект и manifest.
- `tests/` — проверки; `archive/pre-layout-build` — старый CMake cache до переноса.

Базовая сборка из этого каталога: `build.ps1`.
Browser Options для обоих профилей: `../../build_browser_options.ps1`.
Для уже установленного соответствующего HF-комплекта достаточно заменить
`Interface.u` при закрытой игре, сохранив прежний. Настройки options.config
пользователя сохраняются. Детали: [общий README](../../README.md).
