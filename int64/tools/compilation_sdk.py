"""Keep native UObject storage compatible while importing client script APIs."""
from uc_declarations import tokens


def native_storage(text):
    ts = tokens(text)
    class_at = next(i for i, t in enumerate(ts) if t.text.casefold() == 'class')
    header = next(i for i in range(class_at, len(ts)) if ts[i].text == ';')
    i, depth, boundary = header + 1, 0, True
    spans = []
    while i < len(ts):
        t = ts[i]
        if depth == 0 and boundary and t.text.casefold() == 'var':
            end = next(j for j in range(i + 1, len(ts)) if ts[j].text == ';')
            if not any(t.text.casefold() == 'native' for t in ts[i + 1:end]):
                raise ValueError('Object contains non-native storage; manual review is required')
            spans.append((t.start, ts[end].end))
            i = end + 1
            continue
        if depth == 0 and boundary:
            boundary = False
        depth += (t.text == '{') - (t.text == '}')
        if (t.text == ';' or t.text == '}') and depth == 0:
            boundary = True
        i += 1
    return ts[header].end, spans


def object_with_runtime_storage(client_text, runtime_text):
    header, client_spans = native_storage(client_text)
    _, runtime_spans = native_storage(runtime_text)
    if len(runtime_spans) != 5:
        raise ValueError('Unexpected runtime UObject declaration layout')
    blocks = [runtime_text[a:b] for a, b in runtime_spans]
    result = client_text
    for start, end in reversed(client_spans):
        result = result[:start] + result[end:]
    newline = '\r\n' if '\r\n' in result else '\n'
    result = result[:header] + newline * 2 + newline.join(blocks) + newline + result[header:]
    return result
