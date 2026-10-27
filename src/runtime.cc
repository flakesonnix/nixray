#include "runtime.hh"
#include "commands.hh"
#include "reader.hh"

#include <nix/expr/eval-settings.hh>
#include <nix/util/signals.hh>
#include <cstdio>
#include <cstdlib>

namespace nixray {

namespace {

struct Window {
    Window(int width, int height, const std::string & title, bool hidden, bool resizable)
    {
        // Raylib's default logger uses stdout, which would corrupt --json.
        SetTraceLogCallback([](int, const char * message, va_list args) {
            std::fputs("nixray: ", stderr);
            std::vfprintf(stderr, message, args);
            std::fputc('\n', stderr);
        });
        SetTraceLogLevel(LOG_WARNING);
        SetConfigFlags((hidden ? FLAG_WINDOW_HIDDEN : 0) |
                       (resizable ? FLAG_WINDOW_RESIZABLE : 0));
        InitWindow(width, height, title.c_str());
        // SetConfigFlags only ORs flags and raylib keeps them after CloseWindow.
        // Reconcile both flags so a later run can undo an earlier run's config.
        if (IsWindowReady()) {
            if (hidden) SetWindowState(FLAG_WINDOW_HIDDEN);
            else ClearWindowState(FLAG_WINDOW_HIDDEN);
            if (resizable) SetWindowState(FLAG_WINDOW_RESIZABLE);
            else ClearWindowState(FLAG_WINDOW_RESIZABLE);
        }
    }
    ~Window() { if (IsWindowReady()) CloseWindow(); }
    Window(const Window &) = delete;
    Window & operator=(const Window &) = delete;
};

Value * inputList(EvalState & state, int count, bool (*read)(int))
{
    std::vector<int> active;
    for (int i = 0; i < count; ++i) if (read(i)) active.push_back(i);
    auto list = state.buildList(active.size());
    for (size_t i = 0; i < active.size(); ++i) {
        list[i] = state.allocValue();
        list[i]->mkInt(active[i]);
    }
    auto * value = state.allocValue();
    value->mkList(list);
    return value;
}

} // namespace

void run(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    if (state.settings.pureEval || state.settings.restrictEval)
        r.fail("builtins.raylib requires impure, unrestricted evaluation");
    r.fields(*args[0], {"width", "height", "title", "fps", "maxFrames", "hidden", "resizable", "state"});
    int width = r.defaultInt(*args[0], "width", 800, 1);
    int height = r.defaultInt(*args[0], "height", 450, 1);
    int fps = r.defaultInt(*args[0], "fps", 60);
    int maxFrames = r.defaultInt(*args[0], "maxFrames", 0);
    bool hidden = r.defaultBool(*args[0], "hidden", false);
    bool resizable = r.defaultBool(*args[0], "resizable", false);
    auto * titleValue = r.optional(*args[0], "title");
    auto title = titleValue ? r.string(*titleValue) : "nixray";
    state.forceFunction(*args[1], pos, context);
    if (IsWindowReady()) r.fail("only one builtins.raylib window may be active (nested runs are not supported)");
    auto hasEnvironment = [](const char * name) {
        const char * value = std::getenv(name);
        return value && *value;
    };
    if (!hasEnvironment("DISPLAY") && !hasEnvironment("WAYLAND_DISPLAY"))
        r.fail("builtins.raylib requires a graphical session (DISPLAY or WAYLAND_DISPLAY)");

    auto * initial = r.optional(*args[0], "state");
    auto current = allocRootValue(initial ? initial : &Value::vNull);
    state.forceValueDeep(**current);
    Window window(width, height, title, hidden, resizable);
    if (!IsWindowReady()) r.fail("could not initialize a raylib window; check DISPLAY and OpenGL support");
    SetTargetFPS(fps);

    int64_t frames = 0;
    while ((!maxFrames || frames < maxFrames) && !WindowShouldClose()) {
        checkInterrupt();
        auto frame = state.buildBindings(12);
        frame.alloc("frame").mkInt(frames);
        frame.alloc("time").mkFloat(GetTime());
        frame.alloc("delta").mkFloat(GetFrameTime());
        frame.alloc("width").mkInt(GetScreenWidth());
        frame.alloc("height").mkInt(GetScreenHeight());
        frame.alloc("mouseX").mkInt(GetMouseX());
        frame.alloc("mouseY").mkInt(GetMouseY());
        frame.insert(state.symbols.create("keysDown"), inputList(state, 349, IsKeyDown));
        frame.insert(state.symbols.create("keysPressed"), inputList(state, 349, IsKeyPressed));
        frame.insert(state.symbols.create("mouseDown"), inputList(state, 7, IsMouseButtonDown));
        frame.insert(state.symbols.create("mousePressed"), inputList(state, 7, IsMouseButtonPressed));
        frame.insert(state.symbols.create("state"), *current);
        // Callbacks may retain their input inside state (including closures).
        // Never hand the evaluator a pointer to a stack-allocated Value.
        auto input = allocRootValue(state.allocValue());
        (**input).mkAttrs(frame);
        auto output = allocRootValue(state.allocValue());
        state.callFunction(*args[1], **input, **output, pos);
        r.fields(**output, {"commands", "state", "close"});
        auto batch = commands(state, pos, r.required(**output, "commands"));
        bool close = r.defaultBool(**output, "close", false);
        if (auto * next = r.optional(**output, "state")) {
            // Force state at the frame boundary, avoiding a chain of numeric
            // thunks retaining every previous frame. Keep it rooted across GC.
            auto nextRoot = allocRootValue(next);
            state.forceValueDeep(**nextRoot);
            current = std::move(nextRoot);
        }
        BeginDrawing();
        for (auto & command : batch) command();
        EndDrawing();
        ++frames;
        if (close) break;
    }
    auto result = state.buildBindings(2);
    result.alloc("frames").mkInt(frames);
    result.insert(state.symbols.create("state"), *current);
    out.mkAttrs(result);
}

} // namespace nixray
