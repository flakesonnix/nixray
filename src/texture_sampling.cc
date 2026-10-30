#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <rlgl.h>
#include <algorithm>
#include <cmath>

namespace nixray {

namespace {

struct TextureQuery {
    using GetInt = void (*)(unsigned, int *);
    using Bind = void (*)(unsigned, unsigned);
    using Level = void (*)(unsigned, int, unsigned, int *);
    using Parameter = void (*)(unsigned, unsigned, float *);
    GetInt getInt;
    Bind bind;
    Level level;
    Parameter parameter;
    int previous = 0;
    static constexpr unsigned target = 0x0de1;

    TextureQuery(unsigned id, const Reader & r)
    {
        getInt = reinterpret_cast<GetInt>(glfwGetProcAddress("glGetIntegerv"));
        bind = reinterpret_cast<Bind>(glfwGetProcAddress("glBindTexture"));
        level = reinterpret_cast<Level>(glfwGetProcAddress("glGetTexLevelParameteriv"));
        parameter = reinterpret_cast<Parameter>(glfwGetProcAddress("glGetTexParameterfv"));
        if (!getInt || !bind || !level || !parameter) r.fail("texture sampling queries are unavailable in this OpenGL context");
        getInt(0x8069, &previous); // GL_TEXTURE_BINDING_2D on the current unit.
        bind(target, id);
    }
    ~TextureQuery() { bind(target, previous); }
    int dimension(int mip, unsigned field) const
    {
        int value = 0;
        level(target, mip, field, &value);
        return value;
    }
    float setting(unsigned field) const
    {
        float value = 0;
        parameter(target, field, &value);
        return value;
    }
};

} // namespace

void configureTexture(Texture2D & texture, const TextureOptions & options, const Reader & r)
{
    int anisotropy = !options.filter || *options.filter < TEXTURE_FILTER_ANISOTROPIC_4X ? 0 :
                     *options.filter == TEXTURE_FILTER_ANISOTROPIC_4X ? 4 :
                     *options.filter == TEXTURE_FILTER_ANISOTROPIC_8X ? 8 : 16;
    if (anisotropy) {
        if (!glfwExtensionSupported("GL_EXT_texture_filter_anisotropic")) r.fail("anisotropic texture filtering is unsupported by this driver");
        using GetFloat = void (*)(unsigned, float *);
        auto getFloat = reinterpret_cast<GetFloat>(glfwGetProcAddress("glGetFloatv"));
        if (!getFloat) r.fail("anisotropic texture filtering queries are unavailable");
        float maximum = 0;
        getFloat(0x84ff, &maximum); // GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT
        if (!std::isfinite(maximum) || maximum < anisotropy) r.fail("requested texture anisotropy exceeds driver support");
    }
    if (options.wrap == TEXTURE_WRAP_MIRROR_CLAMP && !glfwExtensionSupported("GL_EXT_texture_mirror_clamp"))
        r.fail("mirrorClamp texture wrapping is unsupported by this driver");
    if (options.mipmaps) {
        GenTextureMipmaps(&texture);
        TextureQuery query(texture.id, r);
        int w = texture.width, h = texture.height, mip = 0;
        for (;;) {
            if (query.dimension(mip, 0x1000) != w || query.dimension(mip, 0x1001) != h)
                r.fail("could not create complete texture mipmaps");
            ++mip;
            if (w == 1 && h == 1) break;
            w = std::max(1, w/2); h = std::max(1, h/2);
        }
        if (texture.mipmaps != mip) r.fail("native texture mipmap count is inconsistent");
    }
    if (options.filter) {
        int base = *options.filter;
        // Native anisotropy presets only change anisotropy, not min/mag filters.
        // Establish a complete trilinear base rather than inheriting point mode.
        if (anisotropy || base == TEXTURE_FILTER_TRILINEAR)
            base = texture.mipmaps > 1 ? TEXTURE_FILTER_TRILINEAR : TEXTURE_FILTER_BILINEAR;
        SetTextureFilter(texture, base);
        if (anisotropy) SetTextureFilter(texture, *options.filter);
    }
    if (options.wrap) SetTextureWrap(texture, *options.wrap);
    if (anisotropy || options.wrap == TEXTURE_WRAP_MIRROR_CLAMP) {
        TextureQuery query(texture.id, r);
        float applied = anisotropy ? query.setting(0x84fe) : 0;
        if (anisotropy && (!std::isfinite(applied) || applied < anisotropy)) r.fail("driver did not apply requested texture anisotropy");
        if (options.wrap == TEXTURE_WRAP_MIRROR_CLAMP &&
            (query.setting(0x2802) != RL_TEXTURE_WRAP_MIRROR_CLAMP || query.setting(0x2803) != RL_TEXTURE_WRAP_MIRROR_CLAMP))
            r.fail("driver did not apply mirrorClamp texture wrapping");
    }
}

void refreshTextureMipmaps(Texture2D texture)
{
    if (texture.mipmaps > 1) GenTextureMipmaps(&texture);
}

} // namespace nixray
