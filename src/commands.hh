#pragma once

#include <nix/expr/eval.hh>
#include <functional>
#include <vector>

namespace nixray {

using Command = std::function<void()>;
std::vector<Command> commands(nix::EvalState & state, nix::PosIdx pos, nix::Value & value);

} // namespace nixray
