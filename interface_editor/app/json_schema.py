"""Read a document's top-level schema without materializing its potentially huge tree.

The native JSON reader still validates the complete document afterwards.
"""
import json
from pathlib import Path


def document_schema(filename):
    path = Path(filename)
    if path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError('JSON document too large')
    with path.open(encoding='utf-8-sig') as source:
        def characters():
            while chunk := source.read(65536):
                yield from chunk
        chars = characters()
        def take():
            try:
                return next(chars)
            except StopIteration:
                raise ValueError('Incomplete JSON document') from None
        def nonspace():
            char = take()
            while char.isspace():
                char = take()
            return char
        def string(capture=False):
            text = ['"'] if capture else None
            escaped = False
            while True:
                char = take()
                if capture:
                    text.append(char)
                    if len(text) > 65536:
                        raise ValueError('JSON header string too large')
                if char == '"' and not escaped:
                    return json.loads(''.join(text)) if capture else None
                escaped = char == '\\' and not escaped
        if nonspace() != '{':
            raise ValueError('Expected JSON document object')
        while True:
            if nonspace() != '"':
                raise ValueError('Missing JSON document schema')
            key = string(True)
            if nonspace() != ':':
                raise ValueError('Invalid JSON document header')
            char = nonspace()
            if key == 'schema':
                if char != '"':
                    raise ValueError('Invalid JSON document schema')
                return string(True)
            if char == '"':
                string()
                char = nonspace()
            elif char in '{[':
                stack = [char]
                while stack:
                    char = take()
                    if char == '"':
                        string()
                    elif char in '{[':
                        stack.append(char)
                        if len(stack) > 512:
                            raise ValueError('JSON nesting limit exceeded')
                    elif char in '}]':
                        if stack.pop() != ('{' if char == '}' else '['):
                            raise ValueError('Invalid JSON nesting')
                char = nonspace()
            else:
                while char not in ',}':
                    char = take()
            if char != ',':
                raise ValueError('Missing JSON document schema')
