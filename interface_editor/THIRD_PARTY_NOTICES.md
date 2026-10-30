# Сторонние компоненты

Собственный код и собственные демонстрационные PNG в `examples/artwork`
распространяются по MIT (`LICENSE`). Сторонние copyright сохраняются:

- Схемы XDAT и производные материалы формата: `LICENSE.acmi` (acmi, 2016).
- Форматы и ключевые константы DAT: `LICENSE.dat-format` (acmi, 2021).
- Поставляемый Windows runtime zlib: `third_party/windows/ZLIB-LICENSE.txt`.

Зависимости сборки и исполнения устанавливаются отдельно: Python (PSF),
PySide6/Shiboken6/Qt (LGPL/GPL либо коммерческая лицензия), pybind11 (BSD),
nlohmann/json (MIT), OpenSSL 3 (Apache-2.0), zlib (zlib).
При подготовке бинарного релиза включайте их соответствующие лицензии и
уведомления вместе с runtime. Корневая MIT-лицензия не заменяет условия
сторонних компонентов.
