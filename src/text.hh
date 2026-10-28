#pragma once

#include "commands.hh"

namespace nixray {

struct AssetSpecs;

Command textCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value, const Assets * assets);

// A partially applied native function owning only immutable CPU font metrics.
nix::Value * textMeasurer(nix::EvalState & state, const Assets & assets, const AssetSpecs & specs);

} // namespace nixray
