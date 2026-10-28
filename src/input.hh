#pragma once

#include <nix/expr/eval.hh>

namespace nixray {

void addInput(nix::EvalState & state, nix::BindingsBuilder & frame);

} // namespace nixray
