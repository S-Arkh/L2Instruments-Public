"""Read-only resource routing; package decoding remains in the C++ core."""
import json

MODES = (
    ('code', 'Код'), ('textures', 'Текстуры'), ('sounds', 'Звуки'),
    ('materials', 'Материалы'), ('models', 'Модели'),
    ('animations', 'Анимации'), ('other', 'Прочее'),
)
TEXTURES = {'Texture', 'Cubemap', 'MaskTexture', 'WetTexture'}
MATERIALS = {
    'Shader', 'FinalBlend', 'Combiner', 'TexCoordSource', 'TexPanner', 'FadeColor',
    'TexOscillator', 'TexEnvMap', 'VertexColor', 'TexRotator', 'ColorModifier',
    'TexPannerTriggered', 'TexScaler', 'ConstantColor', 'TexOscillatorTriggered',
    'TexPlanningPanner', 'FresnelMaterial', 'MaterialSequence', 'L2ColorModifier',
}
OPERATIONS = {
    'StaticMesh': 'static_mesh', 'SkeletalMesh': 'skeletal_mesh',
    'VertMesh': 'vert_mesh', 'Model': 'model', 'Polys': 'polys',
    'KMeshProps': 'karma_props', 'MeshAnimation': 'mesh_animation',
    'Sound': 'sound', 'Palette': 'palette', 'Package': 'resource_group',
    'BlockingVolume': 'blocking_volume',
}


def classify(info):
    kind = info['class'].rsplit('.', 1)[-1]
    if kind in TEXTURES:
        return 'textures', 'texture'
    if kind in MATERIALS:
        return 'materials', 'material'
    if kind == 'Sound':
        return 'sounds', 'sound'
    if kind == 'MeshAnimation' or kind.startswith('AnimNotify_'):
        return 'animations', ('mesh_animation' if kind == 'MeshAnimation' else 'animation_notify')
    if kind in {'StaticMesh', 'SkeletalMesh', 'VertMesh', 'Model', 'Polys', 'KMeshProps'}:
        return 'models', OPERATIONS[kind]
    return 'other', OPERATIONS.get(kind)


def groups(inventory):
    result = {key: [] for key, _ in MODES}
    for entry in inventory.get('candidates', []):
        mode, operation = classify(entry)
        result[mode].append(dict(entry, operation=operation))
    for entries in result.values():
        entries.sort(key=lambda row: row['path'].casefold())
    return result


def read_model_preview(core,path,identifier):
    """Use an explicitly partial collision prefix only for the rejected profile."""
    try:
        return core.request(operation='model',path=path,object_id=identifier)
    except RuntimeError as error:
        if str(error)!='Unsupported Model class/profile':raise
    try:
        return core.request(operation='model_collision',path=path,object_id=identifier)
    except RuntimeError as error:
        if str(error)!='Unsupported Model zones':raise
    return core.request(operation='model_level_geometry',path=path,object_id=identifier)


def summary_text(value):
    """Bound display size, preserving full decoded data for future visual viewers."""
    def compact(item, depth=0):
        if depth > 12:
            return '(глубина просмотра ограничена)'
        if isinstance(item, dict):
            return {key: (f'<{len(val)//2} байт>' if key.endswith('_hex') and key!='raw_preview_hex'
                          and isinstance(val, str)
                          else compact(val, depth+1)) for key, val in item.items()}
        if isinstance(item, list):
            result = [compact(v, depth+1) for v in item[:64]]
            if len(item) > 64:
                result.append(f'… ещё {len(item)-64} элементов')
            return result
        if isinstance(item, str) and len(item) > 4096:
            return item[:4096] + '…'
        return item
    text = json.dumps(compact(value), ensure_ascii=False, indent=2)
    return text[:200000] + ('\n… вывод ограничен' if len(text) > 200000 else '')
