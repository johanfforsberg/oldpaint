#version 450 core

layout (binding = 0) uniform sampler2D image;
layout (binding = 1) uniform sampler2D overlay;

layout (location = 1) uniform vec4[256] palette;

in VS_OUT {
  vec2 texcoord;
} fs_in;

layout (location=0) out vec4 color;

void main(void) {
  // TODO should use an integer sampler instead
  vec4 pixel = texture(image, fs_in.texcoord);
  vec4 over_pixel = texture(overlay, fs_in.texcoord);
  int index;
  if (over_pixel.a > 0) {
    index = int(over_pixel.r*255);
    vec4 color_ = palette[index];
    if (color_.a == 0)
      discard;
    color = vec4(color_.rgb, over_pixel.a * color.a);
  } else {
    index = int(pixel.r*255);
    vec4 color_ = palette[index];
    if (pixel.a == 0 || color_.a == 0)
      discard;
    color = vec4(color_.rgb, pixel.a * color.a);
    //color = vec4(pixel.a, pixel.r, 0, 1);
  }
}
