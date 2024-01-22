#version 450 core

precision lowp float;

layout (binding = 0) uniform usampler2D image;

layout (location = 1) uniform float global_alpha = 1;
layout (location = 2) uniform vec4[256] palette;

in VS_OUT {
  vec2 texcoord;
} fs_in;

layout (location=0) out vec4 color;

void main(void) {
  uvec4 pixel = texture(image, fs_in.texcoord);
  uint index;
  index = pixel.r;
  vec4 palette_color = palette[index];
  if (pixel.a == 0 || palette_color.a == 0)
    discard;
  color = vec4(palette_color.rgb, global_alpha);
}
