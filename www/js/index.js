
window.onFontStyleChange = fontStyle => {
    let fontFamily
    if (fontStyle === 'SquareDot') {
        fontFamily = 'Bitroot-SquareDot, sans-serif'
    } else if (fontStyle === 'CircleDot') {
        fontFamily = 'Bitroot-CircleDot, sans-serif'
    } else {
        fontFamily = 'Bitroot, sans-serif'
    }
    document.getElementById('title').style.fontFamily = fontFamily
    document.getElementById('input-box').style.fontFamily = fontFamily
}
