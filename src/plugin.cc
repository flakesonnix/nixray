#include <nix/expr/eval.hh>
#include <nix/expr/eval-settings.hh>
#include <nix/expr/primops.hh>
#include <nix/util/signals.hh>
#include <raylib.h>

#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <limits>
#include <string>
#include <vector>

namespace {

using namespace nix;
constexpr auto context = "while evaluating a nixray argument";

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
