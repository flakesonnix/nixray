// Test-only window mutation tracing and deterministic platform-state queries.
#include <raylib.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <limits>
#include <string>

namespace {

unsigned frame = 0;
bool ready = false;
bool fullscreen = false;
Vector2 position{12.5f, 34.25f};
const char * borrowedTitle = nullptr;
std::string expectedTitle;

template<typename Function>
Function original(const char * name)
{
    auto function = reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
    if (!function) { std::fputs("nixray window fixture: missing native function\n", stderr); std::abort(); }
    return function;
}

template<typename... Args>
void trace(const char * format, Args... args)
{
    if (auto * path = std::getenv("NIXRAY_TEST_WINDOW_TRACE")) if (auto * file = std::fopen(path, "a")) {
        if constexpr (sizeof...(args) == 0) std::fputs(format, file);
        else std::fprintf(file, format, args...);
        std::fputc('\n', file);
        std::fclose(file);
    }
}

void checkTitle()
{
    if (!borrowedTitle || expectedTitle != borrowedTitle) {
        std::fputs("nixray window fixture: native title storage did not survive\n", stderr);
        std::abort();
    }
}

} // namespace

extern "C" void InitWindow(int width, int height, const char * title)
{
    static const auto initialize = original<void (*)(int, int, const char *)>("InitWindow");
    frame = 0;
    ready = false;
    position = {12.5f, 34.25f};
    borrowedTitle = title;
    expectedTitle = title;
    trace("init:%d,%d", width, height);
    initialize(width, height, title);
    position = {12.5f, 34.25f};
    ready = true;
}

extern "C" void CloseWindow()
{
    static const auto close = original<void (*)()>("CloseWindow");
    checkTitle();
    if (fullscreen) { std::fputs("nixray window fixture: fullscreen leaked at close\n", stderr); std::abort(); }
    trace("close");
    ready = false;
    close();
    borrowedTitle = nullptr;
}

extern "C" void BeginDrawing()
{
    static const auto begin = original<void (*)()>("BeginDrawing");
    checkTitle();
    trace("begin:%u", frame);
    begin();
}

extern "C" void EndDrawing()
{
    static const auto end = original<void (*)()>("EndDrawing");
    end();
    trace("end:%u", frame);
    ++frame;
}

extern "C" void SetWindowTitle(const char * title)
{
    static const auto set = original<void (*)(const char *)>("SetWindowTitle");
    borrowedTitle = title;
    expectedTitle = title;
    trace("title:%s", title);
    set(title);
}

extern "C" void SetWindowSize(int width, int height)
{
    static const auto set = original<void (*)(int, int)>("SetWindowSize");
    trace("size:%d,%d", width, height);
    set(width, height);
}

extern "C" void SetWindowPosition(int x, int y)
{
    static const auto set = original<void (*)(int, int)>("SetWindowPosition");
    trace("position:%d,%d", x, y);
    set(x, y);
    position = {static_cast<float>(x), static_cast<float>(y)};
}

extern "C" void SetTargetFPS(int fps)
{
    static const auto set = original<void (*)(int)>("SetTargetFPS");
    trace("fps:%d", fps);
    set(fps);
}

extern "C" void SetWindowState(unsigned int flags)
{
    static const auto set = original<void (*)(unsigned int)>("SetWindowState");
    if (flags & FLAG_FULLSCREEN_MODE) {
        trace("fullscreen:1");
        if (!fullscreen) trace("fullscreen-transition:1");
        fullscreen = true;
    }
    if (flags & FLAG_WINDOW_RESIZABLE) trace("resizable:1");
    // Do not change monitor/video modes under a headless server. Other state
    // actions and real framebuffer resizing still reach the native backend.
    set(flags & ~FLAG_FULLSCREEN_MODE);
}

extern "C" void ClearWindowState(unsigned int flags)
{
    static const auto clear = original<void (*)(unsigned int)>("ClearWindowState");
    if (flags & FLAG_FULLSCREEN_MODE) {
        trace("fullscreen:0");
        if (fullscreen) trace("fullscreen-transition:0");
        fullscreen = false;
    }
    if (flags & FLAG_WINDOW_RESIZABLE) trace("resizable:0");
    clear(flags & ~FLAG_FULLSCREEN_MODE);
}

extern "C" void EnableCursor()
{
    static const auto enable = original<void (*)()>("EnableCursor");
    trace("cursor:normal");
    enable();
}

extern "C" void HideCursor()
{
    static const auto hide = original<void (*)()>("HideCursor");
    trace("cursor:hidden");
    hide();
}

extern "C" void DisableCursor()
{
    static const auto disable = original<void (*)()>("DisableCursor");
    trace("cursor:captured");
    disable();
}

extern "C" Vector2 GetWindowPosition()
{
    if (!ready) return original<Vector2 (*)()>("GetWindowPosition")();
    if (std::getenv("NIXRAY_TEST_WINDOW_NONFINITE")) return {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()};
    return position;
}

extern "C" Vector2 GetWindowScaleDPI()
{
    if (!ready) return original<Vector2 (*)()>("GetWindowScaleDPI")();
    if (std::getenv("NIXRAY_TEST_WINDOW_NONFINITE")) return {-std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()};
    return {1.5f, 2.0f};
}

extern "C" bool IsWindowFullscreen() { return fullscreen; }
extern "C" bool IsWindowMinimized() { return frame == 1; }
extern "C" bool IsWindowMaximized() { return frame == 2; }
extern "C" bool IsWindowFocused() { return frame % 2 == 0; }
extern "C" bool IsWindowResized() { return frame == 1; }
extern "C" bool IsCursorOnScreen() { return frame != 1; }

extern "C" bool IsKeyPressed(int key)
{
    static const auto pressed = original<bool (*)(int)>("IsKeyPressed");
    if (!std::getenv("NIXRAY_TEST_WINDOW_INPUT")) return pressed(key);
    if (frame == 0) return key == KEY_SPACE || key == KEY_F || key == KEY_R || key == KEY_C || key == KEY_T || key == KEY_P || key == KEY_M;
    if (frame == 1) return key == KEY_C;
    if (frame == 2) return key == KEY_C || key == KEY_SPACE;
    return frame == 3 && key == KEY_F;
}
