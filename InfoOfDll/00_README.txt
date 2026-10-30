СПРАВОЧНИК DLL, ИССЛЕДОВАННЫХ ПРИ РАЗРАБОТКЕ
Дата: 29.10.2026. Кодировка: UTF-8.
Корень проекта: каталог репозитория с папками dll, int64, interface_editor и другими проектами.
Все относительные пути ниже и в карточках отсчитываются от этого корня.
<GRACIA_CLIENT> обозначает корень установленного клиента Gracia; подставьте свой путь.

Состав
Core.dll.txt             — VM, native-таблица, строки, INT64, профили и загрузка расширения.
Engine.dll.txt           — UTexture, mip, Init, dirty/revision, различия HF/Gracia.
NWindow.dll.txt          — игровой UI, загрузчик Interface, удаление/перекомпиляция пакета.
D3DDrv.dll.txt           — штатный D3D9-renderer и совместимость с Core.
Editor.dll.txt           — исследованный ABI компилятора UnrealScript.
Ucc64Bridge.dll.txt      — собственное расширение компилятора для INT64.
ExtensionL2.dll.txt      — собственное клиентское расширение и браузерный мост.
WebView2Loader.dll.txt   — загрузчик WebView2 и история сбоя в Gracia.
d3d9.dll.txt             — системный D3D9 и отдельный эксперимент sharing.
d3d11.dll.txt            — системный D3D11, WGC и readback кадров.
windowscodecs.dll.txt    — WIC в предыдущем PNG-пути.
integrity.dll.txt        — ограниченная проверка строк, без установленной причинной связи.
ifc23.dll.txt            — ограниченная проверка импортов и наличие в комплекте UCC.
elmorelab.dll.txt        — ограниченная проверка при диагностике Gracia.

Как читать
1. Карточки описывают конкретные изученные участки, не полный SDK/декомпиляцию DLL.
2. RVA — смещение от базы загруженного PE; VA — адрес с явно указанной preferred base.
   Файловый offset не равен RVA. Для вызова использовать actual module base + RVA.
3. Offset поля отсчитывается от указанного объекта; поле одного объекта нельзя
   смешивать с одноимённым полем другого. Все игровые/компиляторские профили здесь x86.
4. SHA256 относится к файлу на диске. Релокации и IAT меняют загруженный образ.
5. HF/Gracia — краткие обозначения наших исследованных сборок, не всех клиентов
   соответствующих хроник. Совпадение названия DLL не означает совпадение ABI.
6. «Использована через API» отличается от «дизассемблирована»; уровень исследования
   указан в каждой карточке. Непроверенные гипотезы не представлены как факты.

Главные источники
dll/core_profiles.json; dll/CORE_PROFILES.md; dll/src/client_abi.h
int64/docs/ABI.md; int64/tools/verify_profile.py
gameAddWebWithD3D9/client_profiles.json
gameAddWebWithD3D9/reports/inventory.json
gameAddWebWithD3D9/reports/gracia-ui-loader.md
gameAddWebWithD3D9/gracia/game-validation.json
gameAddWebWithD3D9/docs/GUIDE.md и docs/PORTING.md

Что подтверждено в игре
HF и Gracia: сборка в Windows и все реализованные игровые функции подтверждены.
Актуальная архитектура Gracia работает внутри ExtensionL2.dll без helper EXE;
GraciaBrowserHost.exe относится к прежнему проверенному комплекту. Изображение, RU/EN,
клики, колесо, drag, сворачивание/восстановление, прекращение звука и закрытие
подтверждены; после выхода L2/GraciaBrowserHost отсутствовали. Хеши установленного
комплекта сверены с manifest. Это не проверка каждой функции перечисленных DLL.

Дополнительно
В inventory есть Scryde DLL: зафиксированы хеши/импорты, но браузерный профиль
Scryde не запущен, исследование прекращено. Из проектов набора на Scryde работает
только pinkDream. CRT/аудиобиблиотеки из исходного UCC являлись зависимостями;
самостоятельный анализ их внутреннего ABI здесь не заявляется.
Interface.u/Core.u/Engine.u/NWindow.u — пакеты UE, не DLL; GraciaBrowserHost.exe —
наш helper. Они упоминаются в карточках как связанные компоненты.
