#pragma once

#include "commands.hh"
#include <cstdint>
#include <optional>

namespace nixray {

class Reader;

struct ClipBounds {
    int64_t left, top, right, bottom;
};

// Drawing surface that currently running commands feed: the window, or a fixed
// render texture. Nested clips clamp against that surface instead of the window.
struct SurfaceSize { int64_t width, height; };

// Render textures raise this while feeding their children.
class SurfaceGuard {
public:
    SurfaceGuard(int64_t width, int64_t height);
    ~SurfaceGuard();
    SurfaceGuard(const SurfaceGuard &) = delete;
    SurfaceGuard & operator=(const SurfaceGuard &) = delete;
};

// Render textures suspend the enclosing window scissor while their target is
// active and re-apply it for following window commands.
void pauseWindowClip();
void resumeWindowClip(const std::optional<ClipBounds> & parent);

ClipBounds clipBounds(const Reader & reader, nix::Value & value, const std::optional<ClipBounds> & parent);
Command clipCommand(ClipBounds bounds, std::optional<ClipBounds> parent, std::vector<Command> batch);

} // namespace nixray
