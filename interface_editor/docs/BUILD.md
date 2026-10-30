# Подготовка portable-релиза

Обычная сборка и тесты описаны в корневом README.

Cross-build Windows использует `tools/package_windows.py` и MinGW-w64 x64.
В `--cache` предоставьте официальные архивы:

- `python-3.12.10-embed-amd64.zip`;
- `Python-3.12.10.tgz`;
- `pyside6_essentials-6.12.0-cp310-abi3-win_amd64.whl`;
- `shiboken6-6.12.0-cp310-abi3-win_amd64.whl`.

В среде сборки должны быть установлены pybind11 и nlohmann_json.

```sh
python tools/package_windows.py --cache /path/to/cache \
  --cxx /path/to/x86_64-w64-mingw32-g++ \
  --dlltool /path/to/x86_64-w64-mingw32-dlltool --out dist/windows
```

Для добавления notices и финального manifest используется
`tools/finalize_distribution.py` (параметры через `--help`). Этот инструмент
использует metadata установленных pybind11/nlohmann_json и сохраняет лицензии.
Архивы Python и колёса Qt включают свои лицензии; сохраняйте их при упаковке.

Перед выпуском запустите portable на Windows, проверьте открытие, повторное
сохранение, Undo/Redo, DAT и preview. Локальные проверки Linux/offscreen не
заменяют эту проверку runtime. GitHub workflow собирает и тестирует исходники;
автоматическая публикация релиза не настроена.
