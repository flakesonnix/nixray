#pragma once

#include "clip.hh"
#include "commands.hh"
#include <raylib.h>
#include <optional>

namespace nixray {

// Paint a render texture with transparent black so stamps are deterministic
// even before the first repaint. Only valid while the window is current.
void initializeRenderTexture(RenderTexture2D target);

Command paintCommand(RenderTexture2D target, const std::optional<ClipBounds> & parent,
                     const std::optional<Camera2D> & camera, BlendMode parentBlend,
                     bool clear, std::vector<Command> batch);

} // namespace nixray
