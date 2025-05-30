# Bitroot

<div style="text-align: center;">
    <img src="preview.png" alt="Bitroot Typeface Preview" style="max-width: 75%; height: 75%;">
    <p><b>5×10 px proportions per glyph, 7 px to baseline.</b></p>
</div>

This typeface was designed using [Aseprite](https://www.aseprite.org/) and later exported to [PixelFont](https://yellowafterlife.itch.io/pixelfont) for font generation.

## Specifications

- **Box Dimensions (W×H)**: 5×10 px
- **Glyph width:** 5 px (all alphabet characters)
- **Baseline:** 7 px from top
- **Uppercase height:** 7 px
- **Lowercase height:** 5 px (in general)
    - **Ascenders:** Some lowercase characters such as `b, d, f, h, i, j` reach 7px height
    - **Descenders**: Other such lowercase characters such as `g, j, p, q` extend 3px below baseline
- **Symbols:** Ink width is usually 1-2 px wide, but it may be more within the 5 px gridbox

## Contributing

Please keep the commit messages imperative in grammar with proper casing.

### Workflow

1. Edit `bitroot-typeface.aseprite` in [Aseprite](https://www.aseprite.org/)
2. Export updated font sheet as `font-sheet.png` (scale as 100%)
3. Pick the image `font-sheet.png` on [PixelFont](https://yellowafterlife.itch.io/pixelfont) and import settings via `pixelfont-settings.json`
3. Generate the font as scalable `ttf` or `otf` format
4. Submit PR with updated `bitroot-typeface.aseprite`, font files, and JSON (if modified)

## License

[SIL Open Font License 1.1](https://scripts.sil.org/OFL)
