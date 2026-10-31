"""Create original synthetic XDAT coverage for independent native-reader checks."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document


def fixture(catalog_text, schema):
    prefix = schema.removesuffix('.XDAT')
    doc = Document(catalog_text)
    doc.create(schema)
    def child(node, name):
        return next(n['id'] for n in doc.children(node) if n['name'] == name)
    def add(node, typ, values=None):
        return doc.add_configured(node, prefix + '.' + typ, values or {})
    windows = child(0, 'windows')
    window = add(windows, 'Window', {'name': 'NativeFixture', 'size': 1,
                 'size_absolute_values': 1, 'size_absolute_width': 321, 'size_absolute_height': 123})
    controls = child(window, 'children')
    for typ in doc.allowed_types(controls):
        node = doc.add(controls, typ)
        if typ.endswith('.ChatWindow'):
            doc.set_many(node, {'lineGap': 255, 'bgPadding': 128, 'bgHeight': 1, 'bgHeightOffset': 0})
        if typ.endswith(('.ListCtrl', '.RichListCtrl')):
            doc.set_many(node, {'headerSortIconWidth': 255, 'headerSortIconHeight': 128, 'headerSortIconOffsetX': 1})
            columns = child(node, 'values')
            column_type = doc.allowed_types(columns)[0]
            doc.add_configured(columns, column_type, {'textStringId': 123, 'width': 47, 'bAscend': 1, 'bNumber': 0, 'bClickEnable': 1})
    groups = child(0, 'defaultPositionGroups')
    for index in range(2):
        group = add(groups, 'DefaultPositionGroup')
        add(child(group, 'positions'), 'WndDefPos', {'wnd': 'PositionFixture' + str(index), 'x': index + 11, 'y': index + 22})
    doc.set(0, 'hasFontDefinition', 1)
    font = child(0, 'fontDefinition')
    doc.set_many(font, {'defaultFontName': 'FixtureFont', 'editDefaultFontName': 'FixtureEditFont'})
    add(child(font, 'fonts'), 'Font.FontData', {'name': 'FixtureFont'})
    head = child(0, 'headDisplay')
    entry = add(child(head, 'headDisplayElements'), 'HeadDisplayDefinition.HeadDisplayElement', {'typeName': 0})
    elements = child(entry, 'elements')
    for draw_type in (0, 1, 2, 3):
        state = add(elements, 'HeadDisplayDefinition.HeadDisplayElement.Element', {'drawType': draw_type})
        if draw_type in (1, 2):
            doc.set_many(state, {'texName': 'Fixture.Texture', 'u1': 1, 'v1': 2, 'u2': 3, 'v2': 4})
        if draw_type == 2:
            doc.set_many(state, {'complexColor': 0xff102030, 'complexText': 'Fixture complex text'})
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'schemas/schemas.json')
    parser.add_argument('--schema', choices=['essence_native.XDAT', 'korea_native.XDAT'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    doc = fixture(args.catalog.read_text(encoding='utf-8'), args.schema)
    with args.output.open('xb') as stream:
        stream.write(doc.serialize())


if __name__ == '__main__':
    main()
