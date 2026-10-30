"""Move class-level type/constant declarations before their uses.

The supplied decompiler puts properties before their enum/struct declarations.
This pass changes declaration placement only; variable order, expressions and
function bodies are preserved. Comments and quoted literals are tokenized.
"""
from dataclasses import dataclass


@dataclass
class Token:
    text: str
    start: int
    end: int


def tokens(text):
    result = []
    i = 1 if text.startswith('\ufeff') else 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        if text[i] == '#' and not text[text.rfind('\n', 0, i) + 1:i].strip():
            end = text.find('\n', i)
            i = len(text) if end == -1 else end + 1
            continue
        if text.startswith('//', i):
            end = text.find('\n', i)
            i = len(text) if end == -1 else end + 1
            continue
        if text.startswith('/*', i):
            depth = 1
            i += 2
            while i < len(text) and depth:
                if text.startswith('/*', i):
                    depth += 1
                    i += 2
                elif text.startswith('*/', i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError('Unterminated block comment')
            continue
        start = i
        if text[i] in '\"\'':
            quote = text[i]
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise ValueError('Unterminated quoted literal')
        elif text[i].isalnum() or text[i] == '_':
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] == '_'):
                i += 1
        else:
            i += 1
        result.append(Token(text[start:i], start, i))
    return result


def extract_inline_enums(text):
    ts = tokens(text)
    header = next((i for i, t in enumerate(ts) if t.text.casefold() == 'class'), None)
    if header is None:
        return text, []
    header = next((i for i in range(header, len(ts)) if ts[i].text == ';'), None)
    if header is None:
        raise ValueError('Class declaration has no semicolon')
    depth, boundary, variable = 0, True, False
    edits, blocks, names = [], [], []
    i = header + 1
    while i < len(ts):
        t = ts[i]
        if depth == 0 and boundary:
            variable = t.text.casefold() == 'var'
            boundary = False
        if depth == 0 and variable and t.text.casefold() == 'enum':
            if i + 2 >= len(ts) or not ts[i + 1].text.isidentifier() or ts[i + 2].text != '{':
                raise ValueError('Unsupported inline enum declaration')
            end = next((j for j in range(i + 3, len(ts)) if ts[j].text == '}'), None)
            if end is None:
                raise ValueError('Unterminated inline enum')
            name = ts[i + 1].text
            blocks.append(text[t.start:ts[end].end] + ';')
            edits.append((t.start, ts[end].end, name))
            names.append(name.casefold())
            i = end + 1
            continue
        if t.text == '{':
            depth += 1
        elif t.text == '}':
            depth -= 1
            if depth == 0:
                boundary = True
        elif t.text == ';' and depth == 0:
            boundary = True
        i += 1
    if edits:
        newline = '\r\n' if '\r\n' in text else '\n'
        for start, end, replacement in reversed(edits):
            text = text[:start] + replacement + text[end:]
        pos = ts[header].end
        text = text[:pos] + newline * 2 + (newline * 2).join(blocks) + newline + text[pos:]
    return text, names


def normalize(text):
    text, extracted = extract_inline_enums(text)
    ts = tokens(text)
    start = next((i for i, t in enumerate(ts) if t.text.casefold() == 'class'), None)
    if start is None:
        return text, extracted
    header = next((i for i in range(start, len(ts)) if ts[i].text == ';'), None)
    if header is None:
        raise ValueError('Class declaration has no semicolon')
    i, depth, boundary = header + 1, 0, True
    declarations = []
    first_other = len(text)
    while i < len(ts):
        t = ts[i]
        kind = t.text.casefold()
        if depth == 0 and boundary and kind in ('struct', 'enum', 'const'):
            j = i + 1
            while ts[j].text.casefold() in ('native', 'export', 'transient'):
                j += 1
            name = ts[j].text.casefold()
            if not name.isidentifier():
                raise ValueError(f'Invalid {kind} name: {ts[j].text}')
            if kind == 'const':
                end = next((k for k in range(j + 1, len(ts)) if ts[k].text == ';'), None)
            else:
                opening = next((k for k in range(j + 1, len(ts)) if ts[k].text == '{'), None)
                if opening is None:
                    raise ValueError(f'{kind} {name} has no body')
                level, end = 1, opening + 1
                while end < len(ts) and level:
                    level += (ts[end].text == '{') - (ts[end].text == '}')
                    end += 1
                if level or end == len(ts) or ts[end].text != ';':
                    raise ValueError(f'{kind} {name} has no closing }};')
            if end is None:
                raise ValueError(f'{kind} {name} has no semicolon')
            declarations.append((name, i, end))
            i = end + 1
            continue
        if depth == 0 and boundary:
            first_other = min(first_other, t.start)
            boundary = False
        if t.text == '{':
            depth += 1
        elif t.text == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Unbalanced closing brace')
            if depth == 0:
                boundary = True
        elif t.text == ';' and depth == 0:
            boundary = True
        i += 1
    # Do not repair or guess broken function braces here. Already identified
    # top-level declarations can still be moved; the compiler diagnoses bodies.
    names = {name for name, _, _ in declarations}
    if len(names) != len(declarations):
        raise ValueError('Duplicate type/constant declaration')
    pending = list(declarations)
    ordered = []
    emitted = set()
    while pending:
        for index, (name, begin, end) in enumerate(pending):
            uses = {t.text.casefold() for t in ts[begin + 1:end]} & names - {name}
            if uses <= emitted:
                ordered.append(pending.pop(index))
                emitted.add(name)
                break
        else:
            raise ValueError('Cyclic or ambiguous local type/constant dependencies')
    if not declarations or (ordered == declarations and ts[declarations[-1][2]].end <= first_other):
        return text, extracted
    newline = '\r\n' if '\r\n' in text else '\n'
    blocks = [text[ts[begin].start:ts[end].end] for _, begin, end in ordered]
    result = text
    for _, begin, end in reversed(declarations):
        result = result[:ts[begin].start] + result[ts[end].end:]
    position = ts[header].end
    result = result[:position] + newline * 2 + (newline * 2).join(blocks) + newline + result[position:]
    return result, list(dict.fromkeys(extracted + [name for name, _, _ in ordered]))


def normalize_file(path):
    raw = path.read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        encoding = 'utf-16'
    else:
        try:
            raw.decode('utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            encoding = 'latin1'  # lossless preservation; no charset guessing
    text = raw.decode(encoding)
    cleaned, constructive = strip_constructive(text)
    result, moved = normalize(cleaned)
    if result != text:
        path.write_bytes(result.encode(encoding))
    return {'moved': moved, 'constructive_removed': constructive}


def strip_constructive(text):
    """Drop a native C++ header-generation modifier in the -NoBind staging SDK.

    This does not synthesize C++ constructors. The target client keeps its
    original native DLLs; UStruct serialized metadata has no such modifier.
    """
    ts = tokens(text)
    depth, edits, names = 0, [], []
    for i, token in enumerate(ts):
        if depth == 0 and token.text.casefold() == 'struct':
            j = i + 1
            while j < len(ts) and ts[j].text not in ('{', ';'):
                if ts[j].text.casefold() == 'constructive' and j + 1 < len(ts) and ts[j + 1].text.isidentifier():
                    if not any(t.text.casefold() == 'native' for t in ts[i + 1:j]):
                        raise ValueError('constructive without native is not supported')
                    edits.append((ts[j].start, ts[j].end))
                    names.append(ts[j + 1].text)
                j += 1
        depth += (token.text == '{') - (token.text == '}')
    for start, end in reversed(edits):
        text = text[:start] + text[end:]
    return text, names
