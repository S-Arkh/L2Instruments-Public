# Сборка публикационной копии

Работайте из корня `L2Instruments`. Windows, VS2022 C++/Windows SDK, Python 3.12,
CMake 3.24+. Native-компоненты клиента собираются **Win32**; редактор XDAT — x64.

## Native без игровых файлов

```powershell
python -m pip install -r gameAddWebWithD3D9/requirements.txt
python gameAddWebWithD3D9/tools/fetch_dependencies.py
python gameAddWebWithD3D9/profiles/high-five/prepare.py --native-only
python gameAddWebWithD3D9/profiles/gracia/prepare.py --native-only

cmake -S gameAddWebWithD3D9/profiles/high-five -B gameAddWebWithD3D9/profiles/high-five/build -G "Visual Studio 17 2022" -A Win32
cmake --build gameAddWebWithD3D9/profiles/high-five/build --config Release
cmake -S gameAddWebWithD3D9/profiles/gracia -B gameAddWebWithD3D9/profiles/gracia/build-inprocess -G "Visual Studio 17 2022" -A Win32 -DGRACIA_INPROCESS_BROWSER=ON
cmake --build gameAddWebWithD3D9/profiles/gracia/build-inprocess --config Release
```

`fetch_dependencies.py` устанавливает JSON-заголовки и WebView2 SDK 1.0.4314.35
в игнорируемые каталоги. Для офлайн-установки передайте `--webview-package`.
WebView2 Evergreen Runtime устанавливается отдельно на машине запуска.

`archive/addWeb/native`, собственные UC API и `prepare_ui.py` — **активные
зависимости** цепочки подготовки HF. Они включены в Git. Сгенерированные stage,
старые клиентские копии и результаты экспериментов не включены.

## Внешние данные и UI

1. Соберите `int64`, `dll`, `interface_editor` по общей инструкции.
2. Подготовьте `int64` workspace и внешний compiler/runtime SDK согласно
   [SCRIPT_TOOLS](../../docs/SCRIPT_TOOLS.md).
3. HF workflow использует соответствующий профиль HF с уже подготовленными
   `ExtensionL2.u` и патченной `Core.dll`. Они должны совпадать с native ABI;
   исходный игровой каталог сценариями импорта не изменяется.
4. Импортируйте локальные файлы:

```powershell
python gameAddWebWithD3D9/tools/prepare_inputs.py --profile high-five --client-system C:\LocalInputs\HF\System --compiler-workspace C:\LocalInputs\compiler-workspace --launcher-dir int64/build/Release
python gameAddWebWithD3D9/tools/prepare_inputs.py --profile gracia --client-system C:\LocalInputs\Gracia\System
```

Импорт HF создаёт исходный BrowserWnd и handlers из внешних Classes/ScriptText,
без включения извлечённого игрового кода в Git. Используйте тот же Python x64,
которым собран редактор. Runtime SDK Gracia ожидается в `int64/sdk/runtime2226`.

5. Соберите HF:
   `gameAddWebWithD3D9/profiles/high-five/build.ps1 -Python python -ClientSystem C:\LocalInputs\HF\System`.
6. Для Gracia сначала подготовьте baseline UI/восстановленные Classes через
   `profiles/gracia/build.ps1 -Python python -ExportedClasses C:\LocalInputs\Gracia\Classes -ClientSystem C:\LocalInputs\Gracia\System`.
   Затем выполните `profiles/gracia/build_inprocess.ps1 -Python python`.
7. `gameAddWebWithD3D9/build_browser_options.ps1 -Python python` пересобирает UI
   с API `OpenBrowser(url, hideControls)` из подготовленных workspace.

Полный путь с внешними данными зависит от конкретного профиля. Подтверждение
игровой работы в старых отчётах относится к старым хешам. В текущей подготовке
отдельно фиксируются native-сборка и доступные автономные тесты.

Scryde содержит исследовательские сценарии и документацию; готового поддерживаемого
браузерного профиля нет. Инструменты Procmon предоставляются пользователем отдельно.
# Диагностика устройства renderer_probe

Сборка из каталога `gameAddWebWithD3D9` (нужны VS2022 C++ и Windows SDK):

```powershell
cmake -S tools/renderer_probe -B C:/Build/renderer-probe -G "Visual Studio 17 2022" -A Win32
cmake --build C:/Build/renderer-probe --config Release
```

Запуск диагностики и статус GPU/CPU: [GPU_CPU_BACKENDS.md](GPU_CPU_BACKENDS.md).
Сборка не требует клиентских данных или WebView2 SDK. CI собирает её в Windows x86.
