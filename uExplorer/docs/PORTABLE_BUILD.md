# Portable-сборка и выпуск релизов

## Релиз через GitHub Actions

Workflow `.github/workflows/release-uexplorer.yml` работает по той же схеме,
что и релиз Interface Editor. После появления workflow в основной ветке:

1. Откройте **Actions → Release uExplorer → Run workflow**.
2. Выберите ветку с нужной ревизией и задайте `version`, например `0.1.0-rc.1`.
3. Для предварительной версии оставьте `prerelease` включённым. Версия с
   суффиксом требует этот флаг; для стабильной версии вроде `0.1.0` его снимите.

Workflow закрепляет SHA выбранной ревизии, собирает Windows x64, запускает
CTest, синтетический smoke и launcher-тесты. Затем упаковщик скачивает зависимости
с проверкой закреплённых хешей и проверяет реальный Start.cmd из распакованного ZIP.
Игровой клиент и SDK для этих проверок не требуются.

В GitHub Releases публикуются `uExplorer-<version>-windows-x64.zip` и
`SHA256SUMS.txt`; описание берётся из автоматически созданного `RELEASE_NOTES.md`.
Тег: `uexplorer-v<version>`. Существующий тег или релиз останавливает запуск.
Публикация идёт через draft; если загрузка оборвалась, разберите оставшийся draft
перед повторным запуском. Готовые файлы также доступны как artifact
`uexplorer-release` в течение одного дня. Дополнительные секреты не нужны:
используется встроенный GitHub token, право `contents: write` есть только у
публикующего job. Предварительный релиз не помечается latest; стабильный помечается.

## Сборка вручную

Цель: Windows x64, Visual Studio 2022 C++/Windows SDK, Python 3.12.10 x64.
Все команды ниже выполняются из `uExplorer` в PowerShell. Нужны Git и CMake.

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-release.txt
if ($LASTEXITCODE) { throw 'Dependencies failed' }
$python = (Resolve-Path .venv/Scripts/python.exe).Path
& $python -m cmake -S . -B build-portable -G 'Visual Studio 17 2022' -A x64 "-DPython_EXECUTABLE=$python"
if ($LASTEXITCODE) { throw 'Configure failed' }
& $python -m cmake --build build-portable --config Release --parallel 2
if ($LASTEXITCODE) { throw 'Build failed' }
& .\.venv\Scripts\ctest.exe --test-dir build-portable -C Release --output-on-failure
if ($LASTEXITCODE) { throw 'CTest failed' }
& $python -m cmake --install build-portable --config Release --prefix .
if ($LASTEXITCODE) { throw 'Install failed' }
& $python -B tests/portable_smoke.py
if ($LASTEXITCODE) { throw 'Synthetic smoke failed' }
& $python -B -m unittest discover -s tests -p test_launcher.py -v
if ($LASTEXITCODE) { throw 'Launcher tests failed' }
& $python -B tools/package_windows.py --version 0.1.0-dev.1 --bin bin --cache local/portable-cache --out dist/portable-0.1.0-dev.1 --download
if ($LASTEXITCODE) { throw 'Packaging failed' }
```

`--out` должен указывать на новый каталог. `--download` разрешает скачивание
отсутствующих входов из `tools/portable_inputs.json`; без него используется
только локальный cache. SHA-256 проверяется в обоих режимах. Версия передаётся
явно; упаковщик записывает текущий Git SHA и признак dirty рабочей копии.
Если Git доступен только в WSL, передайте полный SHA через `--revision <SHA>`;
в этом режиме `dirty` в manifest равен `null` (состояние рабочей копии неизвестно).

Результат — `dist/portable-0.1.0-dev.1/publish/`: ZIP, `SHA256SUMS.txt` и
русское описание релиза `RELEASE_NOTES.md`.
Каталог `publish` появляется только после успешной проверки распакованного ZIP.
Проверка запускает реальный `Start.cmd` с Qt offscreen, из другого рабочего
каталога, с ограниченным PATH, из пути с кириллицей и пробелами. Проверяются
загрузка bundled DLL, CLI, чтение синтетического пакета, preview, побайтовый
экспорт ScriptText, отказ перезаписи и локальное хранение настроек. После проверки
manifest подтверждает отсутствие изменений в дистрибутиве.

Для повторной проверки распакуйте ZIP в новый каталог и выполните:

```powershell
& $python -B tools/validate_distribution.py 'D:\Проверка portable\uExplorer-0.1.0-dev.1-windows-x64'
```

Проверка предназначена для свежей тестовой копии без пользовательских настроек.
Для проверки GUI без offscreen вручную откройте `Start.cmd` из распакованного ZIP.
Проверки на игровых эталонах описаны отдельно в [BUILD_AND_TEST.md](BUILD_AND_TEST.md).
