# Сборка и тесты

Все команды — из корня репозитория, кроме явно отмеченных.
Основная среда: Python 3.12; Visual Studio 2022 C++/Windows SDK; CMake 3.24+.
Используйте активированное виртуальное окружение и совпадающую разрядность Python/C++.

## UCC INT64 и ExtensionL2 (Win32)

```powershell
cmake -S int64 -B int64/build -G "Visual Studio 17 2022" -A Win32
cmake --build int64/build --config Release
ctest --test-dir int64/build -C Release --output-on-failure
cmake -S dll -B dll/build -G "Visual Studio 17 2022" -A Win32
cmake --build dll/build --config Release
cmake --build dll/build --config Release --target generate_native_uc
python -B -m unittest discover -s int64/tests -v
python -B -m unittest discover -s dll/tests -v
```

Сборка C++ не требует оригинальных DLL. Для компиляции UC настройте внешние
пути по [SCRIPT_TOOLS.md](SCRIPT_TOOLS.md). Генерация native API обновляет
`dll/ExtensionL2/Classes/ExtensionL2API.uc` в рабочей копии.

## Interface Editor и uExplorer (x64)

Установите `interface_editor/requirements-release.txt`; он включает зависимости
сборки обоих C++ ядер. Команды Windows находятся в [README](../README.md).

Linux: нужны компилятор C++17, Python development headers, OpenSSL 3, zlib,
библиотеки Qt (`libegl1`, `libopengl0`, `libxkbcommon0`, `libdbus-1-3`).

```sh
python -m cmake -S interface_editor -B interface_editor/build -G Ninja -DCMAKE_BUILD_TYPE=Release
python -m cmake --build interface_editor/build --parallel 2
python -m cmake -S uExplorer -B uExplorer/build -G Ninja -DCMAKE_BUILD_TYPE=Release
python -m cmake --build uExplorer/build --parallel 2
```

Тесты редактора запускаются **из его каталога**:

```powershell
cd interface_editor
$env:QT_QPA_PLATFORM = 'offscreen'
python -B -m pytest -q
```

Linux: `QT_QPA_PLATFORM=offscreen python -B -m pytest -q`.
Фикстуры генерируются из схем и собственных данных. Настоящие XDAT подключаются
через `INTERFACE_XDAT_FIXTURES`, дополнительные текстуры — `INTERFACE_CLIENT_RESOURCES`.
uExplorer использует `UEXPLORER_CORE` для нестандартного пути к собранному ядру.
Его интеграционные сценарии в `tests/` рассчитаны на эталоны Gracia и подготовленные
внешние пакеты; они не включены в автономный прогон CI. Для `tests/validate.py`
и `tests/test_gui.py` задайте `UEXPLORER_GRACIA_SYSTEM` (Interface.u и NWindow.u).

## Браузер

[Полная инструкция](../gameAddWebWithD3D9/docs/PUBLICATION_BUILD.md): установка SDK,
native-сборка без клиента, затем подготовка и сборка UI с внешними входами.

## pinkDream

```powershell
python -m pip install -r pinkDream/requirements.txt
python -B -m unittest discover -s pinkDream/tools -p "test_*.py" -v
python pinkDream/tools/library.py --help
python pinkDream/tools/create_library.py --help
python pinkDream/tools/build_theme.py --help
```

В Git включены рецепты Christmas/Halloween/Glamour Pink, генератор и инструменты.
`assets/libraries`, `assets/objects` и готовые UTX создаются локально из собственных
входов. Формат и порядок импорта: [ADDING_THEMES](../pinkDream/docs/ADDING_THEMES.md).

## Пример Credit

`python test_interfaces/build.py --help` описывает параметры. Настройте переменные
из `SCRIPT_TOOLS.md`, передайте `--client-system`, `--client-core`,
`--reference-package` и `--launcher int64/build/Release/ucc64.exe`.
Classes будут созданы локально; в Git сохраняется только сценарий внесения изменения.
