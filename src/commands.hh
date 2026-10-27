#pragma once

#include <nix/expr/eval.hh>
#include <functional>
#include <vector>

namespace nixray {

class Assets;
using Command = std::function<void()>;
// A null registry validates syntax only; the resulting commands must not run.
std::vector<Command> commands(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                              const Assets * assets = nullptr);

} // namespace nixray
