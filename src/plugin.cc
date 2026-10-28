#include "commands.hh"
#include "runtime.hh"
#include "camera.hh"

#include <nix/expr/primops.hh>
#include <raylib.h>

namespace {

using namespace nix;
using namespace nixray;

RegisterPrimOp raylibOp({
    .name = "__raylib",
    .args = {"config", "render"},
    .doc = "Open a raylib window and call render with a fresh input snapshot each frame. "
           "Optional config.assets declares named textures and fonts loaded once per window "
           "and named render textures started transparent. "
           "Snapshots include press/release states, two-axis wheel deltas and UTF-8 text input. "
           "frame.measureText measures text using the default or a named font. "
           "The callback returns { commands; state ? previousState; close ? false; }. "
           "Returns { frames; state; }. Impure evaluation only.",
    .impl = run,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp runOp({
    .name = "__raylibRun",
    .args = {"config", "render"},
    .doc = "Compatibility alias for builtins.raylib.",
    .impl = run,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp validateOp({
    .name = "__raylibValidate",
    .args = {"commands"},
    .doc = "Recursively validate command structure without opening a window or loading assets; return the top-level list length. "
           "Texture and font names are resolved only by builtins.raylib.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        out.mkInt(static_cast<int64_t>(commands(state, pos, *args[0]).size()));
    },
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp versionOp({
    .name = "__raylibVersion",
    .args = {},
    .arity = 0,
    .doc = "The version of raylib linked into nixray.",
    .impl = [](EvalState & state, PosIdx, Value **, Value & out) {
        out.mkString(RAYLIB_VERSION, state.mem);
    },
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp worldToScreenOp({
    .name = "__raylibWorldToScreen2D",
    .args = {"camera", "point"},
    .doc = "Convert a world-space { x; y; } point to screen coordinates using a 2D camera. Pure; no window required.",
    .impl = worldToScreen2D,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp screenToWorldOp({
    .name = "__raylibScreenToWorld2D",
    .args = {"camera", "point"},
    .doc = "Convert a screen-space { x; y; } point to world coordinates using a 2D camera. Pure; no window required.",
    .impl = screenToWorld2D,
    .experimentalFeature = std::nullopt,
});

} // namespace
