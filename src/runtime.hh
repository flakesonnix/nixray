#pragma once

#include <nix/expr/eval.hh>

namespace nixray {

void run(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);

} // namespace nixray
