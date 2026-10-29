#include "window.hh"
#include "reader.hh"

#include <cmath>
#include <utility>

namespace nixray {

namespace {

void vectorSnapshot(EvalState & state, Value & out, Vector2 vector)
{
    auto result = state.buildBindings(2);
    result.alloc("x").mkFloat(std::isfinite(vector.x) ? vector.x : 0.0f);
    result.alloc("y").mkFloat(std::isfinite(vector.y) ? vector.y : 0.0f);
    out.mkAttrs(result);
}

} // namespace

std::vector<Command> windowCommands(EvalState & state, PosIdx pos, Value & value, WindowState * window)
{
    Reader r(state, pos);
    state.forceList(value, pos, context);
    std::vector<Command> result;
    result.reserve(value.listSize());
    for (auto * entry : value.listView()) {
        auto op = r.string(r.required(*entry, "op"));
        if (op == "setWindowTitle") {
            r.fields(*entry, {"op", "title"});
            auto title = r.string(r.required(*entry, "title"));
            result.emplace_back([window, title = std::move(title)] {
                window->title = title;
                SetWindowTitle(window->title.c_str());
            });
        } else if (op == "setWindowSize") {
            r.fields(*entry, {"op", "width", "height"});
            int width = r.integer(r.required(*entry, "width"), "width", 1, 16384);
            int height = r.integer(r.required(*entry, "height"), "height", 1, 16384);
            result.emplace_back([=] { SetWindowSize(width, height); });
        } else if (op == "setWindowPosition") {
            r.fields(*entry, {"op", "x", "y"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            result.emplace_back([=] { SetWindowPosition(x, y); });
        } else if (op == "setTargetFPS") {
            r.fields(*entry, {"op", "fps"});
            int fps = r.integer(r.required(*entry, "fps"), "fps", 0);
            result.emplace_back([=] { window->targetFPS = fps; SetTargetFPS(fps); });
        } else if (op == "setWindowFullscreen" || op == "setWindowResizable") {
            r.fields(*entry, {"op", "enabled"});
            bool enabled = state.forceBool(r.required(*entry, "enabled"), pos, context);
            unsigned int flag = op == "setWindowFullscreen" ? FLAG_FULLSCREEN_MODE : FLAG_WINDOW_RESIZABLE;
            result.emplace_back([=] {
                if (enabled) SetWindowState(flag);
                else ClearWindowState(flag);
            });
        } else if (op == "setCursorMode") {
            r.fields(*entry, {"op", "mode"});
            auto mode = r.string(r.required(*entry, "mode"));
            if (mode != "normal" && mode != "hidden" && mode != "captured") r.fail("unknown cursor mode '" + mode + "'");
            result.emplace_back([window, mode = std::move(mode)] {
                // Enable first: hiding a captured cursor alone would not release it.
                EnableCursor();
                if (mode == "hidden") HideCursor();
                else if (mode == "captured") DisableCursor();
                window->cursorMode = mode;
            });
        } else r.fail("unknown window operation '" + op + "'");
    }
    return result;
}

void windowSnapshot(EvalState & state, const WindowState & window, Value & out)
{
    auto result = state.buildBindings(16);
    result.alloc("title").mkString(window.title, state.mem);
    result.alloc("targetFPS").mkInt(window.targetFPS);
    vectorSnapshot(state, result.alloc("position"), GetWindowPosition());
    result.alloc("renderWidth").mkInt(GetRenderWidth());
    result.alloc("renderHeight").mkInt(GetRenderHeight());
    vectorSnapshot(state, result.alloc("dpiScale"), GetWindowScaleDPI());
    result.alloc("monitor").mkInt(GetCurrentMonitor());
    result.alloc("fullscreen").mkBool(IsWindowFullscreen());
    result.alloc("resizable").mkBool(IsWindowState(FLAG_WINDOW_RESIZABLE));
    result.alloc("hidden").mkBool(IsWindowHidden());
    result.alloc("minimized").mkBool(IsWindowMinimized());
    result.alloc("maximized").mkBool(IsWindowMaximized());
    result.alloc("focused").mkBool(IsWindowFocused());
    result.alloc("resized").mkBool(IsWindowResized());
    result.alloc("cursorMode").mkString(window.cursorMode, state.mem);
    result.alloc("cursorOnScreen").mkBool(IsCursorOnScreen());
    out.mkAttrs(result);
}

} // namespace nixray
