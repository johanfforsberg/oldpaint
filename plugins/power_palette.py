from oldpaint.ui.colors import PaletteColors


class Plugin:

    def __init__(self):
        self.selection = None
        self.palette_colors = PaletteColors()
    
    def __call__(self, imgui, window):
        imgui.text(str(window.drawing.palette.size))
        self.palette_colors.render(window, pages=1)
        
        
