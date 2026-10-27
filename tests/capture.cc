// Test-only LD_PRELOAD hook: capture the actual back buffer before the swap.
#include <raylib.h>
#include <rlgl.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>

namespace {

void capture(const char * path)
{
    // Commands are batched until EndDrawing; flush before reading their pixels.
    rlDrawRenderBatchActive();
    Image image = LoadImageFromScreen();
    if (!image.data) return;
    Color * colors = LoadImageColors(image);
    if (colors) {
        if (auto * file = std::fopen(path, "wb")) {
            std::fprintf(file, "P6\n%d %d\n255\n", image.width, image.height);
            auto count = static_cast<size_t>(image.width) * image.height;
            for (size_t i = 0; i < count; ++i) {
                unsigned char rgb[] = {colors[i].r, colors[i].g, colors[i].b};
                std::fwrite(rgb, sizeof(rgb), 1, file);
            }
            std::fclose(file);
        }
        UnloadImageColors(colors);
    }
    UnloadImage(image);
}

} // namespace

extern "C" void EndDrawing()
{
    static const auto finish = reinterpret_cast<void (*)()>(dlsym(RTLD_NEXT, "EndDrawing"));
    if (!finish) {
        std::fputs("nixray test capture: cannot find raylib EndDrawing\n", stderr);
        std::abort();
    }
    if (auto * path = std::getenv("NIXRAY_TEST_CAPTURE"); path && *path) capture(path);
    finish();
}
