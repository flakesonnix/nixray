#include "runtime.hh"
#include "assets.hh"
#include "commands.hh"
#include "input.hh"
#include "reader.hh"
#include "text.hh"
#include "audio.hh"
#include "window.hh"
#include "model.hh"
#include "log.hh"

#include <nix/expr/eval-settings.hh>
#include <nix/util/signals.hh>
#include <cstdlib>

namespace nixray {

namespace {

struct Window {
    Window(int width, int height, const std::string & title, bool hidden, bool resizable)
    {
        configureLogging();
        SetConfigFlags((hidden ? FLAG_WINDOW_HIDDEN : 0) |
                       (resizable ? FLAG_WINDOW_RESIZABLE : 0));
        // Empty titles must still replace raylib's pointer from a previous run.
        InitWindow(width, height, title.empty() ? "nixray" : title.c_str());
        // SetConfigFlags only ORs flags and raylib keeps them after CloseWindow.
        // Reconcile both flags so a later run can undo an earlier run's config.
        if (IsWindowReady()) {
            if (title.empty()) SetWindowTitle(title.c_str());
            if (hidden) SetWindowState(FLAG_WINDOW_HIDDEN);
            else ClearWindowState(FLAG_WINDOW_HIDDEN);
            if (resizable) SetWindowState(FLAG_WINDOW_RESIZABLE);
            else ClearWindowState(FLAG_WINDOW_RESIZABLE);
        }
    }
    ~Window()
    {
        if (!IsWindowReady()) return;
        // CloseWindow leaves native flags behind. Exit fullscreen while its
        // platform window/context still exist, including on evaluation errors.
        if (IsWindowFullscreen()) ClearWindowState(FLAG_FULLSCREEN_MODE);
        ClearWindowState(FLAG_WINDOW_UNDECORATED);
        CloseWindow();
    }
    Window(const Window &) = delete;
    Window & operator=(const Window &) = delete;
};

} // namespace

void run(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    if (state.settings.pureEval || state.settings.restrictEval)
        r.fail("builtins.raylib requires impure, unrestricted evaluation");
    r.fields(*args[0], {"width", "height", "title", "fps", "maxFrames", "hidden", "resizable", "audio", "gestures", "state", "assets"});
    int width = r.defaultInt(*args[0], "width", 800, 1);
    int height = r.defaultInt(*args[0], "height", 450, 1);
    int fps = r.defaultInt(*args[0], "fps", 60);
    int maxFrames = r.defaultInt(*args[0], "maxFrames", 0);
    bool hidden = r.defaultBool(*args[0], "hidden", false);
    bool resizable = r.defaultBool(*args[0], "resizable", false);
    bool audio = r.defaultBool(*args[0], "audio", false);
    auto gestures = gestureFlags(state, pos, r.optional(*args[0], "gestures"));
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

    auto specs = assetSpecs(state, pos, r.optional(*args[0], "assets"));
    if (!audio && (!specs.sounds.empty() || !specs.music.empty()))
        r.fail("audio assets require config.audio = true");
    auto * initial = r.optional(*args[0], "state");
    auto current = allocRootValue(initial ? initial : &Value::vNull);
    state.forceValueDeep(**current);
    WindowState windowState{std::move(title), fps};
    Window window(width, height, windowState.title, hidden, resizable);
    if (!IsWindowReady()) r.fail("could not initialize a raylib window; check DISPLAY and OpenGL support");
    // Gesture flags are native global state; set defaults too on every new run.
    SetGesturesEnabled(gestures);
    AudioDevice device(audio, r);
    // Assets (including partial loads) are destroyed before device and Window.
    Assets assets(specs, r);
    auto measureText = allocRootValue(textMeasurer(state, assets, specs));
    auto models = allocRootValue(state.allocValue());
    modelSnapshot(state, assets, **models);
    SetTargetFPS(fps);

    int64_t frames = 0;
    while ((!maxFrames || frames < maxFrames) && !WindowShouldClose()) {
        checkInterrupt();
        auto frame = state.buildBindings(24);
        frame.alloc("frame").mkInt(frames);
        frame.alloc("time").mkFloat(GetTime());
        frame.alloc("delta").mkFloat(GetFrameTime());
        frame.alloc("width").mkInt(GetScreenWidth());
        frame.alloc("height").mkInt(GetScreenHeight());
        addInput(state, frame);
        audioSnapshot(state, audio, assets, frame.alloc("audio"));
        windowSnapshot(state, windowState, frame.alloc("window"));
        frame.insert(state.symbols.create("state"), *current);
        frame.insert(state.symbols.create("measureText"), *measureText);
        frame.insert(state.symbols.create("models"), *models);
        // Callbacks may retain their input inside state (including closures).
        // Never hand the evaluator a pointer to a stack-allocated Value.
        auto input = allocRootValue(state.allocValue());
        (**input).mkAttrs(frame);
        auto output = allocRootValue(state.allocValue());
        state.callFunction(*args[1], **input, **output, pos);
        r.fields(**output, {"commands", "audio", "window", "state", "close"});
        auto batch = commands(state, pos, r.required(**output, "commands"), &assets);
        std::vector<Command> effects;
        if (auto * actions = r.optional(**output, "audio")) {
            effects = audioCommands(state, pos, *actions, audio ? &assets : nullptr);
            if (!audio && !effects.empty()) r.fail("audio actions require config.audio = true");
        }
        std::vector<Command> windowEffects;
        if (auto * actions = r.optional(**output, "window")) windowEffects = windowCommands(state, pos, *actions, &windowState);
        bool close = r.defaultBool(**output, "close", false);
        if (auto * next = r.optional(**output, "state")) {
            // Force state at the frame boundary, avoiding a chain of numeric
            // thunks retaining every previous frame. Keep it rooted across GC.
            auto nextRoot = allocRootValue(next);
            state.forceValueDeep(**nextRoot);
            current = std::move(nextRoot);
        }
        // Finish all evaluation/validation before changing playback or drawing.
        for (const auto & action : effects) action();
        assets.updateMusic();
        BeginDrawing();
        for (auto & command : batch) command();
        EndDrawing();
        // Geometry and clips were compiled against this frame's dimensions.
        // Change window state only after the entire frame has been drawn.
        for (const auto & action : windowEffects) action();
        ++frames;
        if (close) break;
    }
    auto result = state.buildBindings(2);
    result.alloc("frames").mkInt(frames);
    result.insert(state.symbols.create("state"), *current);
    out.mkAttrs(result);
}

} // namespace nixray
