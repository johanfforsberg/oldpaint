"""
This plugin does not use the "automatic" widgets
but instead builds its own GUI using imgui directly.
This can be neccessary when you need more specialized
GUI components like the dropdowns used here, as well
as the brush preview.
"""

class Plugin:

    """
    Import brushes from other loaded images.
    Assumes compatible palettes, or colors will be messed up!
    """

    def __init__(self, selected_drawing=None, selected_brush=None):
        self.selected_drawing = selected_drawing
        self.selected_brush = selected_brush

    def __call__(self, oldpaint, imgui, window):
        
        drawings = [d for d in window.drawings if d != window.drawing]
        if drawings:
            if not self.selected_drawing:
                self.selected_drawing = drawings[0]
            index = drawings.index(self.selected_drawing)
            clicked, new_index = imgui.combo("Drawing", index, [d.filename for d in drawings])
            if clicked:
                self.selected_drawing = drawings[new_index]
                self.selected_brush = None
            if self.selected_drawing:
                brushes = list(self.selected_drawing.brushes)
                if brushes:
                    if not self.selected_brush:
                        self.selected_brush = brushes[0]
                    index = brushes.index(self.selected_brush)
                    clicked, new_index = imgui.combo("Brush", index, [str(b) for b in brushes])
                    if clicked:
                        self.selected_brush = self.selected_drawing.brushes[new_index]
                    if self.selected_brush:
                        # We can ask the application to generate a "preview" texture for us
                        tex = window.get_brush_preview_texture(self.selected_brush, size=self.selected_brush.size)
                        palette = self.selected_drawing.palette
                        r, g, b, _ = palette.get_color_as_float(palette[0])
                        imgui.push_style_color(imgui.COLOR_BUTTON, r, g, b)
                        if imgui.image_button(tex.name, *self.selected_brush.size):
                            window.drawing.brushes.append(self.selected_brush)
                        imgui.pop_style_color()
                else:
                    imgui.text("Drawing contains no brushes!")


        

        
        
        
