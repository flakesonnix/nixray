#include "commands.hh"
#include "runtime.hh"
#include "camera.hh"
#include "collision.hh"
#include "audio.hh"

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
           "and named render textures started transparent, plus fragment shaders with typed uniform defaults. "
           "Snapshots include press/release states, two-axis wheel deltas and UTF-8 text input. "
           "frame.measureText measures text using the default or a named font. "
           "Opt-in config.audio enables sound/music assets and playback snapshots under frame.audio. "
           "The callback returns { commands; audio ? []; state ? previousState; close ? false; }. "
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
           "Asset names and shader uniform schemas are resolved only by builtins.raylib.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        out.mkInt(static_cast<int64_t>(commands(state, pos, *args[0]).size()));
    },
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp validateAudioOp({
    .name = "__raylibValidateAudio",
    .args = {"actions"},
    .arity = 1,
    .doc = "Validate a flat audio action list without a window, device or asset loading; return its length. Pure.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        out.mkInt(static_cast<int64_t>(audioCommands(state, pos, *args[0]).size()));
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

RegisterPrimOp collisionRecsOp({
    .name = "__raylibCheckCollisionRecs",
    .args = {"rectangle1", "rectangle2"},
    .arity = 2,
    .doc = "Check two { x; y; width; height; } rectangles for collision. Pure; no window required.",
    .impl = checkCollisionRecs,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionCirclesOp({
    .name = "__raylibCheckCollisionCircles",
    .args = {"circle1", "circle2"},
    .arity = 2,
    .doc = "Check two { x; y; radius; } circles for collision, including tangency. Pure; no window required.",
    .impl = checkCollisionCircles,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionCircleRecOp({
    .name = "__raylibCheckCollisionCircleRec",
    .args = {"circle", "rectangle"},
    .arity = 2,
    .doc = "Check a { x; y; radius; } circle against a { x; y; width; height; } rectangle. Pure; no window required.",
    .impl = checkCollisionCircleRec,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionPointRecOp({
    .name = "__raylibCheckCollisionPointRec",
    .args = {"point", "rectangle"},
    .arity = 2,
    .doc = "Check a { x; y; } point against a rectangle; right/bottom edges are excluded. Pure; no window required.",
    .impl = checkCollisionPointRec,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionPointCircleOp({
    .name = "__raylibCheckCollisionPointCircle",
    .args = {"point", "circle"},
    .arity = 2,
    .doc = "Check a { x; y; } point against a { x; y; radius; } circle, including its boundary. Pure; no window required.",
    .impl = checkCollisionPointCircle,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionLinesOp({
    .name = "__raylibCheckCollisionLines",
    .args = {"line1", "line2"},
    .arity = 2,
    .doc = "Intersect two { x1; y1; x2; y2; } segments: return { x; y; } or null. Parallel/collinear lines return null. Pure.",
    .impl = checkCollisionLines,
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp collisionRecOp({
    .name = "__raylibGetCollisionRec",
    .args = {"rectangle1", "rectangle2"},
    .arity = 2,
    .doc = "Return the overlapping { x; y; width; height; }, or an all-zero rectangle when there is no area overlap. Pure.",
    .impl = getCollisionRec,
    .experimentalFeature = std::nullopt,
});

} // namespace
