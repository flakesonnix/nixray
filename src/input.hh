#pragma once

#include <nix/expr/eval.hh>

namespace nixray {

unsigned int gestureFlags(nix::EvalState & state, nix::PosIdx pos, nix::Value * value);
void addInput(nix::EvalState & state, nix::BindingsBuilder & frame);

} // namespace nixray
