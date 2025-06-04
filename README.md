# Bitroot

<p align="center">
  <img src="preview.png" alt="Bitroot Typeface Preview" width="75%">
</p>

<p align="center"><b>5×10 px dimensions per glyph, 7 px to baseline</b></p>

**Bitroot** typeface was designed using [Aseprite](https://www.aseprite.org/) and then exported to [PixelFont](https://yellowafterlife.itch.io/pixelfont) for font generation.

## Specifications

- **Grid dimensions**: 5×10 px
- **Baseline:** 7 px from top
- **Cap height:** 7 px
- **X-height:** 5 px (in general)
    - **Ascenders:** Some lowercase characters such as `b, d, f, h, i, j` reach 7px height
    - **Descenders**: Other such lowercase characters such as `g, j, p, q` extend 3px below baseline
- **Effective width:** 5 px (all alphabet and number characters)
- **Symbols:** Drawn width is typically 1-3 px, but can extend up to the full 5 px

## Contributing

Please keep the commit messages imperative in grammar with proper casing.

### Workflow

1. Edit `bitroot-typeface.aseprite` in [Aseprite](https://www.aseprite.org/)
2. Export updated font sheet as `font-sheet.png` (scale as 100%)
3. Pick the image `font-sheet.png` on [PixelFont](https://yellowafterlife.itch.io/pixelfont) and import settings via `pixelfont-settings.json`
4. Generate the font as scalable `ttf` or `otf` format
5. Submit PR with updated `bitroot-typeface.aseprite`, font files, and JSON (if modified)

## License

This font is under [SIL Open Font License 1.1](LICENSE.txt)
