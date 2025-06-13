import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import png
from pixel_font_builder import Glyph, FontBuilder, WeightName, SerifStyle, SlantStyle, WidthStyle, opentype
from pixel_font_knife.mono_bitmap import MonoBitmap

from tools import path_define


def _load_src_png(file_path: Path) -> MonoBitmap:
    """
    The source image uses white as pixel,
    so we need to customize the loading to convert white to 1 and others to 0
    :param file_path: '.png' file path
    :return: MonoBitmap
    """
    width, height, pixels, _ = png.Reader(filename=file_path).read()
    bitmap = MonoBitmap()
    bitmap.width = width
    bitmap.height = height
    for pixels_row in pixels:
        bitmap_row = []
        for i in range(0, width * 4, 4):
            red = pixels_row[i]
            green = pixels_row[i + 1]
            blue = pixels_row[i + 2]
            alpha = pixels_row[i + 3]
            bitmap_row.append(1 if (red, green, blue, alpha) == (255, 255, 255, 255) else 0)
        bitmap.append(bitmap_row)
    return bitmap


def main():
    # -------------
    # source glyphs
    # -------------

    src_bitmap = _load_src_png(path_define.src_dir.joinpath('font-sheet.png'))
    src_alphabet = [
        'ABCDEFGHIJKLMNOPQR',
        'STUVWXYZ',
        'abcdefghijklmnopqr',
        'stuvwxyz',
        '0123456789',
        '$₵€£¥¤+-*/÷=%"\'#@&',
        '_(),.;:¿?¡!\\{}<>[]',
        '§¶µ´^~©®™',
    ]

    # ------------------
    # Crop Mono bitmaps
    # ------------------

    bitmap_mapping = {}  # code_point -> bitmap
    for row, line in enumerate(src_alphabet):
        for col, c in enumerate(line):
            code_point = ord(c)
            bitmap = src_bitmap.crop(7 * col + 2, 12 * row + 2, 5, 10)
            bitmap_mapping[code_point] = bitmap
    bitmap_mapping[-1] = src_bitmap.crop(7 * 8 + 2, 12 * 0 + 2, 5, 10)  # notdef
    bitmap_mapping[32] = src_bitmap.crop(7 * 8 + 2, 12 * 1 + 2, 5, 10)  # space

    # -----------------------------------------------------
    # Create glyph mapping, this is what the font file need
    # Keep glyphs array is sorted as Unicode
    # ------------------------------------------------------

    character_mapping = {}  # code_point -> glyph_name
    glyphs = []
    for code_point, bitmap in sorted(bitmap_mapping.items()):
        if code_point == -1:
            glyph_name = '.notdef'
            c = '.notdef'
        else:
            glyph_name = f'u{code_point:04X}'
            c = chr(code_point)
            character_mapping[code_point] = glyph_name

        glyphs.append(Glyph(
            name=glyph_name,
            horizontal_offset=(0, -3),
            advance_width=6,  # Right 1px as char-gap
            vertical_offset=(-3, 1),
            advance_height=11,  # Top 1px as line-gap
            bitmap=bitmap.data,
        ))

        # Print and check if the bitmap is correct
        print('--------------------\n')
        print(f'glyph: {glyph_name}, char: {c}\n')
        print(bitmap.draw(end='*'))

    # ------------
    # Fill in font
    # ------------

    builder = FontBuilder()
    builder.font_metric.font_size = 11
    builder.font_metric.horizontal_layout.ascent = 8  # Top 1px as line-gap
    builder.font_metric.horizontal_layout.descent = -3
    builder.font_metric.vertical_layout.ascent = 3
    builder.font_metric.vertical_layout.descent = -3
    builder.font_metric.x_height = 5
    builder.font_metric.cap_height = 7
    builder.font_metric.underline_position = -3
    builder.font_metric.underline_thickness = 1
    builder.font_metric.strikeout_position = 3
    builder.font_metric.strikeout_thickness = 1

    builder.meta_info.version = '0.0.0'  # TODO <-- modify this each release
    builder.meta_info.created_time = datetime.fromisoformat('2025-06-12T00:00:00Z')  # TODO <-- modify this each release
    builder.meta_info.modified_time = builder.meta_info.created_time
    builder.meta_info.family_name = 'Bitroot'
    builder.meta_info.weight_name = WeightName.REGULAR
    builder.meta_info.serif_style = SerifStyle.SERIF
    builder.meta_info.slant_style = SlantStyle.NORMAL
    builder.meta_info.width_style = WidthStyle.MONOSPACED
    builder.meta_info.manufacturer = 'Rio'
    builder.meta_info.designer = 'Rio'
    builder.meta_info.description = 'Sweet fonts to leave your worries behind you'
    builder.meta_info.copyright_info = 'Copyright (c) 2025, Rio (engineer@disroot.org)'
    builder.meta_info.license_info = 'SIL Open Font License 1.1'
    builder.meta_info.vendor_url = 'https://github.com/serialexperimentsrio/bitroot'
    builder.meta_info.designer_url = 'https://github.com/serialexperimentsrio'
    builder.meta_info.license_url = 'https://github.com/serialexperimentsrio/bitroot/blob/main/LICENSE.txt'
    builder.meta_info.sample_text = 'Jackfruit groves with zinc-fed topsoil maximize bounty'

    builder.character_mapping.update(character_mapping)
    builder.glyphs.extend(glyphs)

    # ------------------
    # Clean 'build' dir
    # ------------------

    if path_define.build_dir.exists():
        shutil.rmtree(path_define.build_dir)
    path_define.outputs_dir.mkdir(parents=True)
    path_define.releases_dir.mkdir(parents=True)

    # ------------------
    # Build normal fonts
    # ------------------

    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot.otf'))
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot.otf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot.otf.woff2'), flavor=opentype.Flavor.WOFF2)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot.ttf'))
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot.ttf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot.ttf.woff2'), flavor=opentype.Flavor.WOFF2)
    builder.save_bdf(path_define.outputs_dir.joinpath('Bitroot.bdf'))
    builder.save_pcf(path_define.outputs_dir.joinpath('Bitroot.pcf'))

    # ----------------------
    # Build square dot fonts
    # ----------------------

    builder.meta_info.family_name = 'Bitroot SquareDot'
    builder.opentype_config.outlines_painter = opentype.SquareDotOutlinesPainter()
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.otf'))
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.otf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.otf.woff2'), flavor=opentype.Flavor.WOFF2)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.ttf'))
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.ttf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-SquareDot.ttf.woff2'), flavor=opentype.Flavor.WOFF2)

    # ----------------------
    # Build circle dot fonts
    # ----------------------

    builder.meta_info.family_name = 'Bitroot CircleDot'
    builder.opentype_config.outlines_painter = opentype.CircleDotOutlinesPainter()
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.otf'))
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.otf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_otf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.otf.woff2'), flavor=opentype.Flavor.WOFF2)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.ttf'))
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.ttf.woff'), flavor=opentype.Flavor.WOFF)
    builder.save_ttf(path_define.outputs_dir.joinpath('Bitroot-CircleDot.ttf.woff2'), flavor=opentype.Flavor.WOFF2)

    # -------------------
    # Pack release '.zip'
    # -------------------

    with zipfile.ZipFile(path_define.releases_dir.joinpath(f'bitroot-v{builder.meta_info.version}.zip'), 'w') as file:
        file.write(path_define.project_root_dir.joinpath('LICENSE.txt'), 'LICENSE.txt')
        for font_file_path in path_define.outputs_dir.iterdir():
            if font_file_path.suffix in ('.otf', '.ttf', '.woff', '.woff2', '.bdf', '.pcf'):
                file.write(font_file_path, font_file_path.name)

    # -------------------------------------
    # Copy '.otf.woff2' to 'www/fonts' dir
    # -------------------------------------

    if path_define.www_fonts_dir.exists():
        shutil.rmtree(path_define.www_fonts_dir)
    path_define.www_fonts_dir.mkdir(parents=True)

    for font_file_path in path_define.outputs_dir.iterdir():
        if font_file_path.name.endswith('.otf.woff2'):
            shutil.copyfile(font_file_path, path_define.www_fonts_dir.joinpath(font_file_path.name))


if __name__ == '__main__':
    main()
