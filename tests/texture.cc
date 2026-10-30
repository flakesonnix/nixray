// Test-only sampler readback, upload ordering and capability failures. All
// successful loading, filtering, uploads and mipmap generation use real raylib.
#include <raylib.h>
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

namespace {
template<typename F> F original(const char * name)
{
    auto f = reinterpret_cast<F>(dlsym(RTLD_NEXT, name));
    if (!f) std::abort();
    return f;
}
bool mode(const char * value)
{
    auto * selected = std::getenv("NIXRAY_TEST_TEXTURE_CAPS");
    return selected && std::strcmp(selected, value) == 0;
}
template<typename... A> void trace(const char * format, A... args)
{
    if (auto * path = std::getenv("NIXRAY_TEST_TEXTURE_TRACE")) if (auto * file = std::fopen(path, "a")) {
        if constexpr (sizeof...(args) == 0) std::fputs(format, file);
        else std::fprintf(file, format, args...);
        std::fputc('\n', file); std::fclose(file);
    }
}
using Float = void (*)(unsigned, float *);
Float realGetFloat = nullptr;
void limitedGetFloat(unsigned field, float * value)
{
    realGetFloat(field, value);
    if (field == 0x84ff && mode("low-anisotropy")) *value = 2;
}
template<typename F> F proc(const char * name)
{
    return reinterpret_cast<F>(glfwGetProcAddress(name));
}
void sample(Texture2D texture, const char * event)
{
    auto getInt = proc<void (*)(unsigned, int *)>("glGetIntegerv");
    auto bind = proc<void (*)(unsigned, unsigned)>("glBindTexture");
    auto parameter = proc<void (*)(unsigned, unsigned, float *)>("glGetTexParameterfv");
    auto level = proc<void (*)(unsigned, int, unsigned, int *)>("glGetTexLevelParameteriv");
    auto pixels = proc<void (*)(unsigned, int, unsigned, unsigned, void *)>("glGetTexImage");
    if (!getInt || !bind || !parameter || !level || !pixels) std::abort();
    int saved = 0; getInt(0x8069, &saved); bind(0x0de1, texture.id);
    float min = 0, mag = 0, wrapS = 0, wrapT = 0, anisotropy = 0;
    parameter(0x0de1, 0x2801, &min); parameter(0x0de1, 0x2800, &mag);
    parameter(0x0de1, 0x2802, &wrapS); parameter(0x0de1, 0x2803, &wrapT);
    if (glfwExtensionSupported("GL_EXT_texture_filter_anisotropic")) parameter(0x0de1, 0x84fe, &anisotropy);
    int w = 0, h = 0, mip = texture.mipmaps > 0 ? texture.mipmaps - 1 : 0;
    level(0x0de1, mip, 0x1000, &w); level(0x0de1, mip, 0x1001, &h);
    unsigned char color[4]{};
    if (w == 1 && h == 1) pixels(0x0de1, mip, 0x1908, 0x1401, color);
    bind(0x0de1, saved);
    trace("{\"event\":\"%s\",\"id\":%u,\"levels\":%d,\"min\":%.0f,\"mag\":%.0f,\"wrapS\":%.0f,\"wrapT\":%.0f,\"anisotropy\":%.0f,\"lastSize\":[%d,%d],\"lastPixel\":[%u,%u,%u,%u]}",
          event, texture.id, texture.mipmaps, min, mag, wrapS, wrapT, anisotropy, w, h, color[0], color[1], color[2], color[3]);
}
} // namespace

extern "C" GLFWglproc glfwGetProcAddress(const char * name)
{
    auto raw = original<GLFWglproc (*)(const char *)>("glfwGetProcAddress")(name);
    if (raw && std::strcmp(name, "glGetFloatv") == 0 && mode("low-anisotropy")) {
        realGetFloat = reinterpret_cast<Float>(raw);
        return reinterpret_cast<GLFWglproc>(limitedGetFloat);
    }
    return raw;
}
extern "C" int glfwExtensionSupported(const char * name)
{
    if ((mode("no-anisotropy") && std::strcmp(name, "GL_EXT_texture_filter_anisotropic") == 0) ||
        (mode("no-mirror-clamp") && std::strcmp(name, "GL_EXT_texture_mirror_clamp") == 0)) return GLFW_FALSE;
    return original<int (*)(const char *)>("glfwExtensionSupported")(name);
}
extern "C" Texture2D LoadTextureFromImage(Image image)
{
    Image converted{};
    if (mode("float-texture") && image.width == 2 && image.height == 2) {
        converted = ImageCopy(image);
        ImageFormat(&converted, PIXELFORMAT_UNCOMPRESSED_R32G32B32A32);
        image = converted;
    }
    auto texture = original<Texture2D (*)(Image)>("LoadTextureFromImage")(image);
    if (converted.data) UnloadImage(converted);
    trace("{\"event\":\"load-image\",\"id\":%u,\"width\":%d,\"height\":%d}", texture.id, texture.width, texture.height);
    return texture;
}
extern "C" void SetTextureFilter(Texture2D texture, int filter)
{
    original<void (*)(Texture2D, int)>("SetTextureFilter")(texture, filter);
    sample(texture, "filter");
}
extern "C" void SetTextureWrap(Texture2D texture, int wrap)
{
    original<void (*)(Texture2D, int)>("SetTextureWrap")(texture, wrap);
    sample(texture, "wrap");
}
extern "C" void GenTextureMipmaps(Texture2D * texture)
{
    if (!mode("bad-mipmaps")) original<void (*)(Texture2D *)>("GenTextureMipmaps")(texture);
    sample(*texture, "mipmaps");
}
extern "C" void UpdateTexture(Texture2D texture, const void * data)
{
    original<void (*)(Texture2D, const void *)>("UpdateTexture")(texture, data);
    trace("{\"event\":\"update\",\"id\":%u,\"format\":%d}", texture.id, texture.format);
}
extern "C" void UpdateTextureRec(Texture2D texture, Rectangle rect, const void * data)
{
    original<void (*)(Texture2D, Rectangle, const void *)>("UpdateTextureRec")(texture, rect, data);
    trace("{\"event\":\"update-rec\",\"id\":%u,\"format\":%d,\"rect\":[%.0f,%.0f,%.0f,%.0f]}",
          texture.id, texture.format, rect.x, rect.y, rect.width, rect.height);
}
extern "C" void UnloadTexture(Texture2D texture)
{
    trace("{\"event\":\"unload\",\"id\":%u}", texture.id);
    original<void (*)(Texture2D)>("UnloadTexture")(texture);
}
extern "C" void BeginDrawing()
{
    trace("{\"event\":\"begin\"}"); original<void (*)()>("BeginDrawing")();
}
extern "C" void EndDrawing()
{
    original<void (*)()>("EndDrawing")(); trace("{\"event\":\"end\"}");
}
extern "C" void CloseWindow()
{
    trace("{\"event\":\"close\"}"); original<void (*)()>("CloseWindow")();
}
