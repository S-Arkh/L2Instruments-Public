# Clear HF: от чистого клона до клиентского комплекта

Пример для Windows и профиля `clear_hf_0677e909` из `dll/core_profiles.json`.
Все команды выполняются **из корня репозитория в одной сессии PowerShell**.
Результат основного маршрута — `Core.dll`, `ExtensionL2.dll`, `ExtensionL2.u`
и манифест проверенного комплекта. Дополнительный шаг создаёт Interface.u
с кнопкой Credit. Браузер собирается по [отдельной инструкции](../gameAddWebWithD3D9/docs/PUBLICATION_BUILD.md).

## 1. Что понадобится

| Вход | Для чего нужен | Требование |
|---|---|---|
| Python 3.12 x64, VS2022 C++ x86/x64, Windows SDK, CMake 3.24+ | Сборка инструментов | Native-модули клиента собираются Win32 |
| Оригинальный compiler root с `System` и `Core/Classes` | Компиляция `.u` | Полный UCC System и `Core/Classes/Object.uc`; хеши в [SCRIPT_TOOLS](SCRIPT_TOOLS.md#импорт-компилятора-и-runtime-sdk) |
| Оригинальный Clear HF System | ABI, зависимости и упаковка | Core.dll с SHA-256 `0677e909b10ec398543dbd04cf4d8714ed97befd23d5f928aef17b1a5d844471`; согласованные `Engine.dll`, `l2.exe`, остальные DLL и `Interface.u` |
| Копия полного клиента для установки | Проверка результата | Та же исходная версия, включая ресурсы вне System |
| `UE2Runtime-22261903.exe` | Runtime SDK для пересборки Interface | Нужен только для дополнительного шага Credit; хеш проверяется импортёром |
| `Core.u`, `Engine.u`, `NWindow.u`, `Interface.u` и Interface Classes | Пересборка Interface | Для Credit нужны пакеты с полным сохранённым ScriptText, согласованные с исходным Interface; Classes предоставляются отдельно |

Для базового ExtensionL2 исходники `dll/ExtensionL2/Classes` уже есть в Git,
внешние Interface Classes и runtime SDK этому шагу не нужны.
Входной System сохраняйте как эталон, установку выполняйте в отдельную копию клиента.
Клиентская Core и Core компилятора не взаимозаменяемы.

## 2. Окружение и пути

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r interface_editor/requirements-release.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
$Repo = (Get-Location).Path
$CompilerSource = Read-Host 'Абсолютный путь к оригинальному компилятору (System и Core)'
$ClientSystem = (Resolve-Path (Read-Host 'Абсолютный путь к ОРИГИНАЛЬНОМУ Clear HF System')).Path
$InstallSystem = (Resolve-Path (Read-Host 'Абсолютный путь к System КОПИИ клиента для установки')).Path
$env:L2_CLIENT_SYSTEM = $ClientSystem
$env:L2_CLIENT_CORE = Join-Path $ClientSystem 'Core.dll'
$env:L2_CLIENT_PACKAGES = $ClientSystem
$env:L2_CLEAR_HF_SYSTEM = $ClientSystem
if ((Get-FileHash $env:L2_CLIENT_CORE -Algorithm SHA256).Hash -ne '0677e909b10ec398543dbd04cf4d8714ed97befd23d5f928aef17b1a5d844471') {
    throw 'This walkthrough requires the original clear_hf_0677e909 Core.dll'
}
```

`prepare_extension.ps1` и `build_smoke.ps1` внутри вызывают `py -3`.
При активированной `.venv` проверьте `py -3 --version`: должен быть доступен
совместимый Python (проверенная версия — 3.12).

## 3. Импорт UCC и проверка ABI

```powershell
python int64/tools/import_compiler.py $CompilerSource --destination int64/compiler
if ($LASTEXITCODE) { throw 'Compiler import failed' }
$env:L2_COMPILER_SYSTEM = (Resolve-Path int64/compiler/System).Path
python int64/tools/verify_profile.py
if ($LASTEXITCODE) { throw 'Compiler/client ABI check failed' }
```

`int64/compiler` должен отсутствовать до первого импорта. Для уже импортированного
и проверенного комплекта пропустите импорт и задайте `L2_COMPILER_SYSTEM`.
Импорт сверяет бинарники, а `verify_profile.py` дополнительно проверяет ABI
и извлекает INT64-регистрации выбранной клиентской Core.

## 4. Native-сборка и компиляция ExtensionL2.u

```powershell
cmake -S int64 -B int64/build -G 'Visual Studio 17 2022' -A Win32
if ($LASTEXITCODE) { throw 'INT64 configure failed' }
cmake --build int64/build --config Release
if ($LASTEXITCODE) { throw 'INT64 build failed' }
ctest --test-dir int64/build -C Release --output-on-failure
if ($LASTEXITCODE) { throw 'INT64 tests failed' }
cmake -S dll -B dll/build -G 'Visual Studio 17 2022' -A Win32
if ($LASTEXITCODE) { throw 'DLL configure failed' }
cmake --build dll/build --config Release
if ($LASTEXITCODE) { throw 'DLL build failed' }
$Launcher = (Resolve-Path int64/build/Release/ucc64.exe).Path
$NativeDll = (Resolve-Path dll/build/Release/ExtensionL2.dll).Path
$Prepared = Join-Path $Repo ('dll/work/clear-hf-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
./dll/prepare_extension.ps1 -Destination $Prepared -NativeDll $NativeDll `
    -Launcher $Launcher -ClientCore $env:L2_CLIENT_CORE -ClientSystem $ClientSystem `
    -ReferencePackage (Join-Path $ClientSystem 'Interface.u')
$Bundle = Join-Path $Prepared 'client'
```

Сценарий генерирует UC API, создаёт workspace, компилирует `.u`, проверяет
байткод, создаёт патченную копию Core и выполняет loader/VM-пробы.
При ошибке сценарий останавливается; выбирайте новый `$Prepared` для нового запуска.
Успешный результат: `$Bundle/bundle.json` с `validation.status = passed`,
три файла комплекта и каталог `validation` с логами. Готовый launcher нужно
передавать явно: default некоторых сценариев указывает на отсутствующий `dist/win32`.

## 5. Дополнительно: SDK, Classes и пример Credit

Этот шаг нужен, если требуется `Interface.u`, вызывающий native API из кнопки
Credit. Выполняйте его **до установки** в копию клиента. Требуются дополнительные
входы из таблицы; произвольный декомпилированный Interface не заменяет эталон.

```powershell
$RuntimeInstaller = Read-Host 'Абсолютный путь к UE2Runtime-22261903.exe'
python int64/tools/import_runtime_sdk.py $RuntimeInstaller int64/sdk/runtime2226
if ($LASTEXITCODE) { throw 'Runtime SDK import failed' }
$env:L2_RUNTIME_SDK = (Resolve-Path int64/sdk/runtime2226).Path
$env:L2_INTERFACE_CLASSES = (Resolve-Path (Read-Host 'Абсолютный путь к исходным Interface/Classes')).Path
# Если пакеты лежат отдельно от System, укажите их каталог здесь.
$env:L2_CLIENT_PACKAGES = (Resolve-Path (Read-Host 'Каталог эталонных Core.u, Engine.u, NWindow.u, Interface.u')).Path
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmssfff'
$Work = Join-Path $Repo "test_interfaces/work-$Stamp"
$CreditBundle = Join-Path $Repo "test_interfaces/result-$Stamp"
python test_interfaces/build.py --native-build dll/build/Release --launcher $Launcher `
    --client-core $env:L2_CLIENT_CORE --client-system $ClientSystem `
    --reference-package (Join-Path $env:L2_CLIENT_PACKAGES 'Interface.u') `
    --work $Work --out $CreditBundle
if ($LASTEXITCODE) { throw 'Credit build failed; inspect workspace logs' }
$Bundle = $CreditBundle
```

Каталог `int64/sdk/runtime2226` должен быть новым; при повторном использовании
уже импортированного SDK пропустите импорт. `prepare_interface.py`, вызываемый
из `build.py`, копирует Classes, извлекает ScriptText, проверяет полноту исходников
и готовит SDK. При первом запуске `test_interfaces/src/Classes` создаётся локально,
затем переиспользуется: при смене профиля используйте новую рабочую копию проекта.
Скрипт требует совпадения исходного Interface.u с файлом в `$ClientSystem` и
допускает только ожидаемое изменение `LoginMenuWnd.OnClickButton`.

## 6. Установка, проверка и откат

Закройте игру. В `$Bundle` находится либо базовый комплект шага 4, либо Credit
из шага 5. Следующий блок копирует только файлы, перечисленные в его манифесте,
и сохраняет прежние версии в уникальной папке внутри репозитория:

```powershell
$Manifest = Join-Path $Bundle 'bundle.json'
$Data = Get-Content $Manifest -Raw | ConvertFrom-Json
if ($Data.validation.status -ne 'passed') { throw 'Bundle validation has not passed' }
$Files = @($Data.bundle_files.PSObject.Properties.Name)
$Backup = Join-Path $Repo ('local/backups/clear-hf-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Path $Backup -Force | Out-Null
$Absent = @()
foreach ($Name in $Files) {
    $Target = Join-Path $InstallSystem $Name
    if (Test-Path $Target) { Copy-Item $Target (Join-Path $Backup $Name) }
    else { $Absent += $Name }
}
@{ absent = $Absent; files = $Files; system = $InstallSystem } |
    ConvertTo-Json | Set-Content (Join-Path $Backup 'restore.json') -Encoding UTF8
foreach ($Name in $Files) { Copy-Item (Join-Path $Bundle $Name) (Join-Path $InstallSystem $Name) -Force }
python dll/tools/check_installation.py $InstallSystem --manifest $Manifest
if ($LASTEXITCODE) { throw 'Installed files differ from the validated bundle' }
```

Ожидается `files_match: true`. Замечания о ресурсах клиента выводятся отдельно.
Затем запустите копию клиента; для Credit нажмите кнопку в меню входа и проверьте
`$InstallSystem/test.txt`: `PASS` и `SelfTest=True`. В базовом комплекте кнопка
не изменяется. Loader/VM и совпадение файлов не заменяют эту игровую проверку.

Откат при закрытой игре (укажите сохранённый каталог `$Backup`, если сессия новая):

```powershell
$Restore = Get-Content (Join-Path $Backup 'restore.json') -Raw | ConvertFrom-Json
foreach ($Name in $Restore.files) {
    $Target = Join-Path $Restore.system $Name
    if ($Name -in $Restore.absent) { Remove-Item $Target -ErrorAction SilentlyContinue }
    else { Copy-Item (Join-Path $Backup $Name) $Target -Force }
}
```

## Что проверено для этой инструкции

Native-сборки и автономные тесты воспроизведены на Windows из чистого клона.
Параметры импорта, подготовки и проверки сверены с исходным кодом скриптов.
Полный маршрут с внешними клиентскими файлами при подготовке этой инструкции
не запускался; исторические игровые результаты см. в [VALIDATION](VALIDATION.md).
