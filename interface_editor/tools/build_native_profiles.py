"""Reproduce native-reader-derived profiles from the bundled Salvation baseline.

No client files or memory images are inputs. See docs/ESSENCE_XDAT_RESEARCH.md
for native evidence and the distinction between reader and full UI validation.
"""
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(catalog, korean=False):
    prefix = 'korea_native' if korean else 'essence_native'
    def remap(value):
        if isinstance(value, str):
            return prefix + value[5:] if value.startswith('etoa5.') else value
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {remap(k): remap(v) for k, v in value.items()}
        return value
    records = remap({k: v for k, v in catalog['records'].items() if k.startswith('etoa5.')})
    def rec(name):
        return records[prefix + '.' + name]
    def field(name, kind='int', default=0):
        return {'op': 'field', 'name': name, 'kind': kind,
                'default': '' if kind == 'string' and default == 0 else default}
    def fields(names, kind='int'):
        return [field(n, kind) for n in names.split()]
    def obj(name, typ):
        return dict(field(name, 'object'), type=prefix + '.' + typ, poly=False)
    def array(name, typ, count='int', poly=False):
        return dict(field(name, 'list'), type=prefix + '.' + typ, count=count, poly=poly)
    def record(name, ops, base=None):
        records[prefix + '.' + name] = {'base': prefix + '.' + base if base else None,
                                      'abstract': False, 'ops': ops}

    base = rec('DefaultProperty')['ops']
    base[11:11] = fields('rotationAngle axisVectorX axisVectorY axisVectorZ', 'float') + fields('noFocus', 'bool')
    for op in base:
        if op.get('name') == 'relativeDrag':
            op['name'] = 'superChild'
        elif op.get('name') == 'superChild':
            op['name'] = 'relativeDrag'
        elif op.get('name') == 'unk24':
            op['name'] = 'nWindowStyleLow'
    index = next(i for i, op in enumerate(base) if op.get('name') == 'nWindowStyleLow')
    base.insert(index + 1, field('nWindowStyleHigh'))

    ops = fields('parent backTex script state', 'string')
    ops += fields('iconable stuckable hidden alwaysFullAlpha savePosition saveSize', 'bool')
    ops += [field('title'), field('draggable', 'bool'), field('frame', 'bool')] + fields('frameSize frameDirection')
    ops += fields('exitbutton movable resizeFrame', 'bool') + [field('resizeFrameDirection'), field('resizeFrameTexture', 'string')]
    ops += fields('resizeTextureX resizeTextureY resizeTextureWidth resizeTextureHeight resizeFrameX resizeFrameY resizeFrameWidth resizeFrameHeight', 'float')
    ops += fields('resizeMaxIncrease drawerDirection offsetX offsetY')
    ops += [field('directionFixed', 'bool'), field('drawerSeconds', 'float'), field('ownerWindow', 'string')]
    ops += fields('showAnimType hideAnimType showAnimDirection')
    ops += [field('showAnimSeconds', 'float'), field('hideAnimDirection'), field('hideAnimSeconds', 'float')]
    ops += [field('iconName', 'string'), field('tooltipIdx'), field('hookKeyInput', 'bool')]
    ops += fields('workingConfiguration leftTextureName midTextureName rightTextureName minimizeBtnTexture closeBtnTexture', 'string')
    ops += fields('leftBackTextureWidth midBackTextureWidth backTextureHeight btnSize') + [field('titleFontName', 'string')]
    ops += [array('additionalState', 'Window.State', 'compact')]
    ops += fields('useParentClipRect showInArena alwaysProcessScroll', 'bool')
    ops += fields('minimizeBtnOffsetX minimizeBtnOffsetY closeBtnOffsetX closeBtnOffsetY') + [field('scalable', 'bool')]
    ops += [array('children', 'DefaultProperty', poly=True)]
    rec('Window')['ops'] = ops

    button = rec('Button')['ops']
    button.insert(4, field('collisionTex', 'string'))
    button += fields('defaultTextEnableColor defaultTextDisableColor', 'color')
    item = {o['name']: o for o in rec('ItemWindow')['ops']}
    item['pressCtrlTooltip'] = field('pressCtrlTooltip', 'bool')
    order = ('wndType col row maxItemNum iconWidth iconHeight gapX gapY offsetX offsetY '
             'backgroundItemWidth backgroundItemHeight backgroundItemTex selectedItemWidth selectedItemHeight selectedItemTex '
             'newToggleItemWidth newToggleItemHeight newToggleItemTex newToggleItemOffSetX newToggleItemOffSetY '
             'unselectedItemWidth unselectedItemHeight unselectedItemTex blankItemWidth blankItemHeight blankItemTex '
             'blankItemDependency noSelectItem noItemDrag buttonClick useCoolTime noScroll simpleTooltip compareTooltip '
             'pressCtrlTooltip showIconFrame outLineUp outLineDown buttonTypePrevButtonPosX buttonTypePrevButtonPosY '
             'buttonTypeNextButtonPosX buttonTypeNextButtonPosY expandItem').split()
    rec('ItemWindow')['ops'] = [item[n] for n in order] + fields('useIconSize64 rButtonClick', 'bool') + fields('scaleTypeTextSizeSmall scaleTypeTextSizeMedium scaleTypeTextSizeLarge')
    rec('ComboBox')['ops'].insert(0, field('maxDropDownList'))
    listing = rec('ListCtrl')['ops']
    columns = listing.pop()
    listing += fields('useRButtonSelect useRollOverTexture noUseArrowBtn', 'bool')
    listing += fields('headerFontName headerTextureName headerSortIconTextureName', 'string')
    listing += fields('headerSortIconWidth headerSortIconHeight headerSortIconOffsetX', 'byte')
    listing += fields('sliderTexTop sliderTexMid sliderTexBottom selectionTex unselectedOverTex selectedOverTex', 'string') + [columns]
    rich = copy.deepcopy(rec('ListCtrl'))
    rich['ops'] = [o for o in rich['ops'] if o['name'] not in ('selectionTex', 'unselectedOverTex', 'selectedOverTex')]
    rich['ops'][-1]['type'] = prefix + '.RichListCtrl.Column'
    records[prefix + '.RichListCtrl'] = rich
    column = copy.deepcopy(rec('ListCtrl.ListElement')['ops'])
    column += fields('textColor', 'color') + fields('align valign offsetX offsetY individualAlign individualVAlign')
    record('RichListCtrl.Column', column)
    rec('ScrollArea')['ops'][1:1] = fields('hScroll noUseArrowBtn', 'bool') + fields('sliderTexTop sliderTexMid sliderTexBottom', 'string')
    rec('EditBox')['ops'] += fields('checkByteLen', 'bool') + fields('align vAlign') + fields('enableTex disableTex highlightTex', 'string') + fields('uSize vSize')
    rec('CheckBox')['ops'] += fields('padding')
    rec('HtmlCtrl')['ops'] += fields('noUseArrowBtn', 'bool') + fields('sliderTexTop sliderTexMid sliderTexBottom', 'string')
    rec('ShortcutItemWindow')['ops'] += fields('showMacroText showShortcutKey', 'bool')
    record('StatusBar.GaugeTexture', [field('texture', 'string')] + fields('width height') + [field('color', 'color'), field('ratio')])
    record('StatusBar.ScaleMark', [field('markTexture', 'string')] + fields('numberOfMarks markWidth markHeight'))
    rec('StatusBar')['ops'] = [field('title', 'string'), field('titleIndex'), field('unit', 'string'), field('drawPoint'), field('renewal', 'bool')]
    rec('StatusBar')['ops'] += [obj('gaugeTexture' + str(i), 'StatusBar.GaugeTexture') for i in range(25)]
    rec('StatusBar')['ops'] += [field('gaugeTextTexture', 'string')] + fields('fontWidth fontHeight') + [array('scaleMarks', 'StatusBar.ScaleMark')]
    rec('CharacterViewportWindow')['ops'] += fields('useBackbuffer' if korean else 'isCostume useBackbuffer', 'bool')
    record('EffectViewportWnd', fields('scale offsetX offsetY offsetZ cameraDist', 'float') + fields('cameraPitch cameraYaw') + fields('backgroundTex maskTex', 'string') + fields('useBackbuffer', 'bool'), 'DefaultProperty')
    rec('ChatWindow')['ops'] = fields('lineGap bgPadding bgHeight bgHeightOffset', 'byte')
    record('StatusRound', [obj('gaugeTexture' + str(i), 'StatusBar.GaugeTexture') for i in range(6)] + fields('trailerU trailerV trailerUSize trailerVSize maskU maskV maskUSize maskVSize', 'float'), 'DefaultProperty')
    rec('InvenWeight')['ops'] += fields('scaleTypeTextSizeSmall scaleTypeTextSizeMedium scaleTypeTextSizeLarge')
    textlist = rec('TextListBox')['ops']
    textlist[0], textlist[1] = textlist[1], textlist[0]
    textlist += fields('sliderTexTop sliderTexMid sliderTexBottom', 'string')
    radio = rec('RadioButton')['ops']
    radio[2], radio[3] = radio[3], radio[2]
    radio += fields('padding')
    rec('ListBox')['ops'] += fields('sliderTexTop sliderTexMid sliderTexBottom', 'string')
    rec('Font')['ops'].insert(1, field('editDefaultFontName', 'string'))
    rec('ChatChannelDefinition')['ops'] += fields('subColor', 'color')
    rec('HeadDisplayDefinition')['ops'] += [field('deadTextColor', 'color'), field('deadTextureScale')]
    element = rec('HeadDisplayDefinition.HeadDisplayElement.Element')['ops']
    element[1]['enum'].append({'label': 'ComplexType', 'value': 2})
    old = element.pop()
    element.append({'op': 'if', 'condition': 'drawType == 0', 'yes': old['no'], 'no': [
        {'op': 'if', 'condition': 'drawType == 1', 'yes': old['yes'], 'no': [
            {'op': 'if', 'condition': 'drawType == 2', 'yes': copy.deepcopy(old['yes']) +
             [field('complexColor', 'color'), field('complexText', 'string')], 'no': []}]}]})
    record('ScalableGlobal', fields('widthRate heightRate'))
    record('FontMapping', fields('name fontName', 'string'))
    record('FontMappingTable', [field('defaultFontName', 'string'), array('mappings', 'FontMapping')])
    record('ScalableData', [obj('scale' + str(i), 'ScalableGlobal') for i in range(101)] + [obj('fontScale' + str(i), 'FontMappingTable') for i in range(101)])
    rec('XDAT')['ops'] += [obj('scalableData', 'ScalableData')]
    record('DefaultPositionGroup', [array('positions', 'WndDefPos')])
    rec('XDAT')['ops'][2:5] = [array('defaultPositionGroups', 'DefaultPositionGroup'), field('hasFontDefinition', 'bool'),
                             {'op': 'if', 'condition': 'hasFontDefinition != 0', 'yes': [obj('fontDefinition', 'Font')], 'no': []}]
    label = ('Korea (protocol 290, user-reported; native-reader verified)' if korean else
             'Essence (protocol 591) / Japan (protocol 230, user-reported) — native-reader verified')
    return {'format': 1, 'versions': [[label, prefix + '.XDAT']], 'records': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'schemas/schemas.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--korean', action='store_true')
    parser.add_argument('--update-builtin', action='store_true', help='Regenerate both native profiles in the selected catalog')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    if args.update_builtin:
        if args.output or args.korean:
            parser.error('--update-builtin cannot be combined with --output or --korean')
        packages = [build(catalog, korean) for korean in (False, True)]
        identifiers = {p['versions'][0][1] for p in packages}
        catalog['versions'] = [v for v in catalog['versions'] if v[1] not in identifiers]
        for package in packages:
            catalog['records'].update(package['records'])
            catalog['versions'].extend(package['versions'])
        args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        return
    if not args.output:
        parser.error('--output is required unless using --update-builtin')
    package = build(catalog, args.korean)
    # Exclusive creation keeps a local research package from being overwritten.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(package, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
