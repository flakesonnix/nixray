#pragma once

#include "commands.hh"
#include <string>

namespace nixray {

Command curveCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value, const std::string & op);

} // namespace nixray
