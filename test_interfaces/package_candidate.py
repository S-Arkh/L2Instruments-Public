"""Assemble a new candidate from hash-verified compilation, layout and native outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(compile_dir, layout_dir, native_dir, out):
    compile_dir, layout_dir, native_dir, out = [
        p.resolve() for p in (compile_dir, layout_dir, native_dir, out)]
    if out.exists() or any(out.is_relative_to(p) for p in (compile_dir, layout_dir, native_dir)):
        raise ValueError('Output must be new and outside input directories')
    build = json.loads((compile_dir/'result.json').read_text(encoding='utf-8'))
    layout = json.loads((layout_dir/'Interface.json').read_text(encoding='utf-8'))
    native = json.loads((native_dir/'report.json').read_text(encoding='utf-8'))
    adapters = {
        'korean': ('korea_native.XDAT', 'korean_modern_964ff724', 'left_of_login'),
        'gracia': ('ct24.XDAT', 'gracia_epilogue_0941cac5', 'bottom_right_menu'),
        'high_five': ('ct26.XDAT', 'clear_hf_0677e909', 'bottom_right_menu'),
        'japan': ('essence_native.XDAT', 'japan_modern_74eac821', 'login_screen_overlay'),
    }
    actual = (layout['schema'], native['patch']['profile'], layout['position'])
    if adapters.get(build['profile']) != actual:
        raise ValueError('Compilation, layout and native profiles do not match')
    if not (build['compiled'] and build['compiler_exit'] == 0 and
            layout['unrelated_bytes_preserved'] and native['native_bundle_verified'] and
            all(native['tests'][key]['passed'] for key in ('loader', 'vm'))):
        raise ValueError('Required validation did not pass')
    files = {
        'Interface.u': (compile_dir/'System/Interface.u', build['sha256']),
        'Interface.xdat': (layout_dir/'Interface.xdat', layout['output_sha256']),
        **{name: (native_dir/'client'/name, native['files'][name])
           for name in ('Core.dll', 'ExtensionL2.dll')},
    }
    for name, (source, expected) in files.items():
        if digest(source) != expected:
            raise ValueError('Artifact hash mismatch: ' + name)
    system = out/'System'
    system.mkdir(parents=True)
    for name, (source, expected) in files.items():
        shutil.copy2(source, system/name)
        if digest(system/name) != expected:
            raise ValueError('Copied artifact hash mismatch: ' + name)
    manifest = dict(schema=1, profile=build['profile'], build_identity=build['build_identity'],
                    files={name: expected for name, (_, expected) in files.items()},
                    original_core_sha256=native['patch']['original_sha256'],
                    original_layout_sha256=layout['input_sha256'],
                    checks=dict(package_compiled=True, layout_byte_verified=True,
                                native_loader_vm_verified=True, client_startup_verified=False,
                                client_button_verified=False),
                    report_identity='source build identity; use manifest for final artifact hashes')
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    instructions = '''# Кандидат для проверки Test

Компиляция, обратимость XDAT и отдельные native-проверки пройдены.
Запуск полного клиента и выполнение кнопки ещё требуют проверки.

## Проверка

1. Создайте отдельную копию клиента профиля из manifest.json.
2. Сохраните её исходные Interface.u, Interface.xdat, Core.dll и, если имеется,
   ExtensionL2.dll вне System. Сохраните сведения об отсутствии последней DLL.
3. Сверьте SHA256 файлов комплекта с manifest.json (`Get-FileHash -Algorithm SHA256`).
   Исходные Core и XDAT должны соответствовать original_*_sha256 в манифесте.
4. Скопируйте четыре файла из System комплекта в System тестовой копии клиента.
   Используйте соответствующий оригинальный NWindow.u. API и тестовые классы
   уже включены в Interface.u этого комплекта.
5. Запустите тестовую копию до экрана входа. Проверьте Test: для Korean — слева
   от входа, для Gracia/High Five — в правом нижнем меню под Replay,
   для Japan — отдельная кнопка с полем результата справа снизу на экране входа.
6. Нажмите Test один раз. Зафиксируйте итоговое сообщение и System/test.txt.
   Сервер для этих проверок не требуется. При сбое сохраните последнюю строку RUN.
7. Повторите нажатие: отчёт должен начинаться заново. Передайте test.txt,
   manifest.json и снимок расположения кнопки для проверки результата.

Отчёт содержит идентификатор исходной сборки. Итоговые хеши пакета и DLL указаны
в manifest.json; сам runtime-отчёт пока их не вычисляет. SKIP не означает PASS.
Набор тестов пока покрывает только часть добавленных возможностей компилятора.

## Откат

Закройте тестовый клиент. Восстановите сохранённые четыре файла; если ExtensionL2.dll
изначально отсутствовала, удалите добавленную копию. Сохраните test.txt отдельно.
'''
    (out/'README_RU.md').write_text(instructions, encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compile-dir', 'layout-dir', 'native-dir', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(assemble(args.compile_dir, args.layout_dir, args.native_dir, args.out), indent=2))


if __name__ == '__main__':
    main()
