# Чтение и запись текстовых файлов

Реализация находится в `src/extensionL2.cpp` (`TextFiles`). Добавлены три native:

```uc
native(4007) static final function bool WriteTextFile(string FileName, string Directory, string Text);
native(4008) static final function string ReadTextFile(string FileName, string Directory);
native(4009) static final function int GetFileError();
```

Имена аргументов в сгенерированном API — Arg0/Arg1/Arg2; порядок тот же.

## Пути и формат

- `Directory == ""`: папка **загруженной ExtensionL2.dll**, то есть System при обычной установке.
- Относительный Directory, например `logs`, также отсчитывается от папки DLL.
- Абсолютный Directory, например `D:/Logs`, используется напрямую.
- Каталог должен существовать. Файл при записи создаётся либо полностью перезаписывается.
- Запись — UTF-8 без BOM, чтение — UTF-8 с необязательным BOM.
- Пустой текст создаёт/обнуляет файл. Чтение пустого файла возвращает пустую строку без ошибки.
- Ошибка записи: `false`. Ошибка чтения: пустая строка. Для различения ошибки и пустого файла
  вызовите `GetFileError()` сразу после операции: 0 — успех, иначе код Win32.
- Последняя ошибка хранится отдельно для каждого потока и обновляется при каждом чтении/записи.

Примеры:

```uc
class'ExtensionL2API'.static.WriteTextFile("test.txt", "", "Credit button clicked.");
class'ExtensionL2API'.static.WriteTextFile("test.txt", "D:/Logs", "Hello");
```

Чтение:

```uc
local string Text;
local int ErrorCode;

Text = class'ExtensionL2API'.static.ReadTextFile("test.txt", "");
ErrorCode = class'ExtensionL2API'.static.GetFileError();
if (ErrorCode != 0)
    Log("ReadTextFile failed: " $ string(ErrorCode));
else
    Log(Text);
```

В старом UCC для перевода строки используйте `Chr(13) $ Chr(10)`, а не
C++-экранирование `\r\n` (оно компилируется в обычные буквы r/n).

## Строковый ABI

C++ `std::wstring` соответствует UC `string`. Адаптер читает аргументы через
FFrame::Step в временный FString (12 байт: указатель, длина, ёмкость), копирует
текст и освобождает память через деструктор **той Core, которая загружена**.
Результат присваивается через экспорт FString::operator=(const wchar_t*) Core.
Память Core не освобождается CRT расширения. `std::string`, out/string-ссылки
и массивы не являются поддержанными сигнатурами адаптера.

VM-probe проверяет оба формата строковых констант (UTF-16 и реальный ASCII-байткод
от UCC), Unicode/UTF-8, вложенное чтение в аргумент записи, освобождение строк,
другую текущую папку процесса, абсолютный/относительный путь, перезапись,
пустой/отсутствующий файл, отсутствующий каталог, BOM и повреждённый UTF-8.

## Готовый тест кнопки Credit

Исходники Interface: `../test_interfaces/src/Classes`.
Готовая пара пакетов и DLL: `../test_interfaces/result`.
Инструкция: [test_interfaces/README.md](../test_interfaces/README.md).
Именно этот комплект содержит новые функции; прежние `dist`-комплекты
с семью native-функциями не заменяют обновлённую DLL и ExtensionL2.u.
