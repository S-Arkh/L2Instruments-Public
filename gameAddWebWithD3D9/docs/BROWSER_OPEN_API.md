# Открытие браузера из UnrealScript

Общий исходник HF/Gracia: `profiles/high-five/Classes/BrowserWnd.uc`.

```uc
function OpenBrowser(optional string StartURL, optional bool HideControls)
```

Пример из другого класса интерфейса, наследующего UICommonAPI:

```uc
local BrowserWnd Browser;

Browser = BrowserWnd(GetScript("BrowserWnd"));
if (Browser != None)
    Browser.OpenBrowser("https://example.com", true);
```

Вызовы:

```uc
Browser.OpenBrowser("https://example.com", false); // указанная страница, панель видна
Browser.OpenBrowser("https://example.com", true);  // указанная страница, четыре элемента скрыты
Browser.OpenBrowser();                            // страница options.config, панель видна
Browser.OpenBrowser("", true);                    // страница options.config, панель скрыта
```

## Поведение

- HideControls скрывает только `btnHome`, `btnReload`, `Address`, `btnGo`.
  Back/Forward, сворачивание и закрытие сохраняются.
- Размер и положение страницы/окна не меняются; место скрытых элементов
  не заполняется страницей. XDAT не изменялся.
- StartURL передаётся существующему TextureWebNavigate после TextureWebOpen.
  Адрес без http/https получает префикс https://, как при обычном Go.
  Это начальный переход после открытия, а не изменение native-настройки Home:
  Home продолжает использовать options.config. Инициализация Runtime сохраняет
  прежний путь открытия страницы конфигурации перед обработкой очереди навигации.
- Повторный вызов для видимого окна применяет новые параметры и открывает страницу
  заново. OpenBrowser без аргументов возвращает поведение по умолчанию.
- Сворачивание/восстановление сохраняет текущую страницу и режим панели.
- Обычный ShowWindow после закрытия открывает страницу конфигурации и показывает
  панель; постоянных изменений options.config нет.

## Сборки

Из каталога gameAddWebWithD3D9:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_browser_options.ps1
```

Для проверки компиляции без изменения опубликованных комплектов добавьте
`-CompileOnly`. При обычной пересборке подтверждение работы сохраняется
только при совпадении хешей Interface.u и ExtensionL2.dll с подтверждённым отчётом.

Скрипт использует уже подготовленные workspace HF и Gracia, копирует их в
отдельные work/<клиент>/<дата-время> и подставляет актуальный общий BrowserWnd.uc.
Обычная подготовка Gracia также берёт этот класс из profiles/high-five/Classes.

Результаты:

- HF: `out/high-five/system/Interface.u`;
- Gracia без helper: `out/gracia/system/Interface.u`.

В out/<клиент>/system находятся также сопутствующие файлы из соответствующих
рабочих комплектов. Для установленной соответствующей версии достаточно заменить
Interface.u при закрытом клиенте, сохранив предыдущий файл. Исходники вызывающего
UC-класса нужно перекомпилировать вместе с новым BrowserWnd для использования API.
В установленные игровые каталоги эта сборка автоматически не копируется.

## Проверка

Оба Interface.u успешно скомпилированы UCC. Наличие BrowserWnd.OpenBrowser
проверено парсером в обоих упакованных файлах; оболочки проверены package_client.
Хеши XDAT и ExtensionL2.dll совпадают с прежними соответствующими комплектами.
Сборка в Windows и работа всех реализованных функций в игре подтверждены
на High Five и Gracia.
В manifest обеих сборок отмечено game_tested=true и user_confirmed_working=true.
Это общее подтверждение работы; отдельные расширенные сценарии не перечислялись.
Подтверждение привязано к хешам в reports/browser-options-validation.json.
