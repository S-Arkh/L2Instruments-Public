# Interface Editor

Самостоятельный редактор XDAT на C++17, Python 3.12 и PySide6 Essentials.
Версия приложения: 0.6.0. Целевая Windows-сборка — **x64**.

Сборка и GUI в Windows, работа с UTX/DAT и результаты редактирования в игре
проверены в исходном проекте. Scryde не входит в подтверждённые интеграции.
Полное [руководство пользователя](USER_GUIDE.md).

Возможности:

- Две независимые панели дерева и поиска, общая история Undo/Redo.
- Редактирование свойств, сравнение узлов, JSON roundtrip с сохранением raw.
- Русский и английский интерфейс, статический preview для Gracia Epilogue / High Five / Японии / Кореи
  (Window, Button, Texture, TextBox, ScrollArea) и экспорт PNG.
- Чтение UTX, собственные текстурные проекты из PNG/TGA и сборка RGBA8 UTX.
- Таблицы SysString, несколько языков, привязка текста кнопок к ID.
- DAT plain (явно), XOR111/120/121, Blowfish211/212, RSA411–414 l2encdec.
  Оригинальные RSA-профили доступны только для чтения.
- Анализ XDAT-схем и создание пользовательского черновика: [SCHEMA_DETECTION.md](docs/SCHEMA_DETECTION.md).
- Исследование неизвестных XDAT: трассировка полей, HEX, проверка гипотез на
  нескольких образцах, импорт/экспорт самостоятельных пакетов схем.
  [Инструкция и ограничения](docs/SCHEMA_RESEARCH.md).
- Встроенные профили `essence_native.XDAT` (Essence/Япония) и
  `korea_native.XDAT` (Корея): шесть normal/Classic файлов читаются до EOF;
  в названиях указаны протоколы Essence 591, Японии 230 и Кореи 290.
  Номера 230/290 предоставлены пользователем и независимо не подтверждены.
  изменённые файлы проверены собственными native-reader клиентов.
  Проверка полного игрового интерфейса ещё не выполнена.
  [Подробности](docs/ESSENCE_XDAT_RESEARCH.md).
- High Five (протокол 268) / Gracia Epilogue (протокол 152): распознавание
  необязательного 20-байтового хвоста с CRC32, показ его слов только для чтения
  и сохранение исходных байтов. Протоколы проверены в предоставленных лаунчерах.
  [Native-проверки и ограничения](docs/XDAT_LEGACY_TAILS.md).

## Windows: сборка и запуск

Установите Python **3.12 x64** и Visual Studio 2022 C++ tools:

```powershell
./build.ps1
./run.cmd
```

`build.ps1` создаёт `.venv`, устанавливает зависимости, собирает модуль и
запускает тесты. `run.cmd` использует локальную сборку либо готовый portable
из `dist/windows`. Java для работы редактора не требуется.

## Linux: сборка и тесты

Нужны компилятор C++17, Python 3.12 с development headers, OpenSSL 3 и zlib.
Для Qt offscreen на Ubuntu могут потребоваться `libegl1`, `libopengl0`,
`libxkbcommon0` и `libdbus-1-3`.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-release.txt
python -m cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
python -m cmake --build build
QT_QPA_PLATFORM=offscreen python -B -m pytest -q
python app/main.py
```

`requirements.txt` задаёт допустимые диапазоны, `requirements-release.txt` —
версии, использованные для проверки публикационной копии.
Windows использует OpenSSL из Python runtime и поставляемый `zlib1.dll`.

## Тестовые данные

Обычный `pytest` генерирует небольшие синтетические XDAT из схем и собственные
таблицы SysString. Генератор — `tests/synthetic_fixtures.py`; каталог
`tests/fixtures` создаётся автоматически и исключён из Git. Для standalone
unittest-сценариев сначала выполните `python tests/synthetic_fixtures.py`.
API `Document.create(schema)` создаёт пустой документ из значений схемы.

Дополнительные проверки реальных файлов включаются явно:

- `INTERFACE_XDAT_FIXTURES`: внешний каталог XDAT, соответствующий
  `tests/integration/fixture-manifest.json` (в репозитории только имена и хеши).
- `INTERFACE_CLIENT_RESOURCES`: внешний каталог клиентских ресурсов для UTX.

Актуальные сборки и результаты тестов этой публикационной копии:
[общий отчёт](../docs/VALIDATION.md). В корне репозитория находится единый CI.
Собственный UTX и DAT encoder подтверждены в целевом игровом клиенте. Синтетические
roundtrip-тесты проверяют внутреннюю согласованность, а не совместимость со
всеми клиентами. Для оригинальных RSA-профилей нет реальных эталонов в этом наборе.

## Примеры и релизы

`examples/artwork` содержит собственные PNG. Новый демопроект создаётся командой
`python tools/create_texture_demo.py --out build/texture-demo`.
`tools/package_windows.py --help` описывает cross-build portable из явно
предоставленных архивов Python и Qt; дополнительные шаги — в `docs/BUILD.md`.
Сборочные результаты и runtime предназначены для GitHub Releases.

Собственный код — MIT (`LICENSE`). Сторонние лицензии и атрибуция перечислены
в `THIRD_PARTY_NOTICES.md`.
