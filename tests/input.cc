// Test-only raylib query fixture: deterministic press/release edges per window.
#include <raylib.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>

namespace {

unsigned frame = 0;
size_t character = 0;

template<typename Function>
Function original(const char * name)
{
    auto function = reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
    if (!function) {
        std::fprintf(stderr, "nixray input fixture: cannot find %s\n", name);
        std::abort();
    }
    return function;
}

} // namespace

extern "C" void InitWindow(int width, int height, const char * title)
{
    static const auto initialize = original<void (*)(int, int, const char *)>("InitWindow");
    frame = 0;
    character = 0;
    initialize(width, height, title);
}

extern "C" void EndDrawing()
{
    static const auto finish = original<void (*)()>("EndDrawing");
    finish();
    ++frame;
    character = 0;
}

extern "C" bool IsKeyDown(int key)
{
    return (frame == 0 && key == KEY_A) || (frame == 2 && key == KEY_KB_MENU) ||
           (frame == 5 && key == KEY_ENTER);
}

extern "C" bool IsKeyPressed(int key) { return IsKeyDown(key); }

extern "C" bool IsKeyReleased(int key)
{
    return (frame == 1 && key == KEY_A) || (frame == 3 && key == KEY_KB_MENU) ||
           (frame == 6 && key == KEY_ENTER);
}

extern "C" bool IsMouseButtonDown(int button)
{
    return (frame == 0 && button == MOUSE_BUTTON_LEFT) || (frame == 2 && button == MOUSE_BUTTON_BACK);
}

extern "C" bool IsMouseButtonPressed(int button) { return IsMouseButtonDown(button); }

extern "C" bool IsMouseButtonReleased(int button)
{
    return (frame == 1 && button == MOUSE_BUTTON_LEFT) || (frame == 3 && button == MOUSE_BUTTON_BACK);
}

extern "C" Vector2 GetMouseWheelMoveV()
{
    if (frame == 0) return {1.5f, -2.0f};
    if (frame == 1) return {0.0f, 1.25f};
    if (frame == 2) return {-0.5f, 0.0f};
    return {0.0f, 0.0f};
}

extern "C" int GetCharPressed()
{
    static constexpr int first[] = {'A', 0x00e4, 0x1f642, 0};
    static constexpr int second[] = {0x03bb, 0x20ac, '\n', 0};
    static constexpr int invalid[] = {0xd800, 0xdfff, 0x110000, -1, 0};
    static constexpr int boundaries[] = {0x7f, 0x80, 0x7ff, 0x800, 0xffff, 0x10000, 0x10ffff, 0};
    const int * queued = nullptr;
    if (frame == 0) queued = first;
    else if (frame == 1) queued = second;
    else if (frame == 2) queued = invalid;
    else if (frame == 4) queued = boundaries;
    if (!queued) return 0;
    int codepoint = queued[character];
    if (codepoint) ++character;
    return codepoint;
}
