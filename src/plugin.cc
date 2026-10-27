#include "commands.hh"
#include "runtime.hh"

#include <nix/expr/primops.hh>
#include <raylib.h>

namespace {

using namespace nix;
using namespace nixray;

RegisterPrimOp raylibOp({
    .name = "__raylib",
    .args = {"config", "render"},
    .doc = "Open a raylib window and call render with a fresh input snapshot each frame. "
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
    .doc = "Validate a list of nixray drawing commands without opening a window; return its length.",
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

} // namespace
