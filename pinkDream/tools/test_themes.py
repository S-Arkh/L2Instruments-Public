import json
import unittest
from PIL import Image
from inventory import ROOT
from theme_render import render
from build_theme import encode
from texture import decode


class Themes(unittest.TestCase):
    def test_dxt_alpha_blocks_survive_colour_import_and_small_mips(self):
        for fmt in (7, 8):
            for size in ((2, 2), (4, 4), (8, 8)):
                blocks = ((size[0]+3)//4)*((size[1]+3)//4)
                alpha = bytes.fromhex('0123456789abcdef') if fmt == 7 else bytes.fromhex('ff00123456789abc')
                reference = (alpha + bytes.fromhex('ffff000012345678')) * blocks
                source = decode(reference, size, fmt)
                replacement = Image.new('RGBA', size, (220, 30, 40, 255))
                payload = encode(replacement, fmt, reference)
                self.assertEqual(len(payload), len(reference))
                self.assertEqual(decode(payload, size, fmt).getchannel('A').tobytes(), source.getchannel('A').tobytes())
                self.assertNotEqual(payload, reference)

    def test_christmas_is_deterministic_and_preserves_silhouette(self):
        recipe = json.loads((ROOT / 'themes/christmas/theme.json').read_text())
        source = Image.new('RGBA', (128, 64), (80, 75, 60, 255))
        source.putpixel((0, 0), (0, 0, 0, 0))
        a, role = render(source, 'test.Frames.Frame_Hor_Center', recipe)
        b, _ = render(source, 'test.Frames.Frame_Hor_Center', recipe)
        self.assertEqual(role, 'title')
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertEqual(a.getchannel('A').tobytes(), source.getchannel('A').tobytes())
        self.assertGreater(len(a.getcolors(100000)), 8)

    def test_candy_edge_alternates_red_and_cream_without_snow(self):
        recipe = json.loads((ROOT / 'themes/christmas/theme.json').read_text())
        self.assertNotIn('snow', recipe['palette'])
        source = Image.new('RGBA', (32, 16), (80, 75, 60, 255))
        image, _ = render(source, 'test.edge', recipe, 'trim')
        from PIL import ImageColor
        colours = {image.getpixel((x, 0))[:3] for x in range(32)}
        self.assertEqual(colours, {ImageColor.getrgb(recipe['palette'][k]) for k in ('candy', 'cream')})

    def test_halloween_decorates_titles_but_keeps_atlas_alpha(self):
        recipe = json.loads((ROOT / 'themes/halloween/theme.json').read_text())
        source = Image.new('RGBA', (128, 64), (80, 75, 60, 255))
        source.putpixel((0, 0), (0, 0, 0, 0))
        title, _ = render(source, 'test.title', recipe, 'title')
        atlas, _ = render(source, 'test.slots', recipe, 'atlas')
        self.assertEqual(title.getchannel('A').tobytes(), source.getchannel('A').tobytes())
        self.assertEqual(atlas.getchannel('A').tobytes(), source.getchannel('A').tobytes())
        self.assertNotEqual(title.tobytes(), atlas.tobytes())
        again, _ = render(source, 'test.title', recipe, 'title')
        self.assertEqual(title.tobytes(), again.tobytes())

    def test_small_frames_and_scroll_controls_have_no_procedural_pattern(self):
        from theme_render import role
        resources = [
            ('L2UI_CT1.Frames.Frame_DF_Ver_Small_Tile', (16, 8), 'stretch'),
            ('L2UI_CT1.Frames.Frame_DF_Hor_Small_Center', (8, 16), 'stretch'),
            ('L2UI_CT1.Frames.Frame_DF_Hor_Large_Tile', (4, 64), 'stretch'),
            ('L2UI_CH3.SCROLLBAR.sliderbarcenter_over', (16, 8), 'stretch'),
            ('L2UI_CH3.SCROLLBAR.ScrollBarUpOnBtn', (16, 16), 'plain-control'),
            ('L2UI_CH3.Button.slider_cursor_down', (16, 32), 'stretch'),
            ('patch.Windows.Windows_DF_Vertical_SizeControl_Bg', (32, 16), 'stretch'),
        ]
        for theme in ('christmas', 'halloween'):
            recipe = json.loads((ROOT / 'themes' / theme / 'theme.json').read_text())
            for name, size, expected in resources:
                with self.subTest(theme=theme, resource=name):
                    source = Image.new('RGBA', size, (80, 75, 60, 190))
                    self.assertEqual(role(name, size), expected)
                    image, actual = render(source, name, recipe)
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(image.getcolors(10000)), 1)
                    self.assertEqual(image.getchannel('A').tobytes(), source.getchannel('A').tobytes())
            self.assertEqual(role('patch.Frames.Frame_Hor_Center', (128, 64)), 'title')


if __name__ == '__main__':
    unittest.main()
