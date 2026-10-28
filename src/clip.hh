#pragma once

#include "commands.hh"
#include <cstdint>
#include <optional>

namespace nixray {

class Reader;

struct ClipBounds {
    int64_t left, top, right, bottom;
};

ClipBounds clipBounds(const Reader & reader, nix::Value & value, const std::optional<ClipBounds> & parent);
Command clipCommand(ClipBounds bounds, std::optional<ClipBounds> parent, std::vector<Command> batch);

} // namespace nixray
