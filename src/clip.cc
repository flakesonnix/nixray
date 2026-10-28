#include "clip.hh"
#include "reader.hh"

#include <algorithm>
#include <utility>

namespace nixray {

namespace {

// nullopt while the window receives output; a paint scope sets its target size.
std::optional<SurfaceSize> surface;

struct ScissorRectangle {
    int x, y, width, height;
};

ScissorRectangle windowBounds(ClipBounds bounds)
{
    auto surfaceWidth = surface ? surface->width : std::max<int64_t>(GetScreenWidth(), 0);
    auto surfaceHeight = surface ? surface->height : std::max<int64_t>(GetScreenHeight(), 0);
    auto left = std::clamp(bounds.left, int64_t{0}, surfaceWidth);
    auto top = std::clamp(bounds.top, int64_t{0}, surfaceHeight);
    auto right = std::clamp(bounds.right, left, surfaceWidth);
    auto bottom = std::clamp(bounds.bottom, top, surfaceHeight);
    // In particular, y + height now fits int in raylib's coordinate conversion.
    return {static_cast<int>(left), static_cast<int>(top),
            static_cast<int>(right - left), static_cast<int>(bottom - top)};
}

void beginClip(ScissorRectangle rectangle)
{
    BeginScissorMode(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
}

struct ClipScope {
    std::optional<ClipBounds> parent;

    ClipScope(ScissorRectangle rectangle, std::optional<ClipBounds> parent) : parent(parent)
    {
        // Raylib flushes queued geometry before changing the scissor state.
        beginClip(rectangle);
    }
    ~ClipScope()
    {
        if (parent) beginClip(windowBounds(*parent));
        else EndScissorMode();
    }
    ClipScope(const ClipScope &) = delete;
    ClipScope & operator=(const ClipScope &) = delete;
};

} // namespace

ClipBounds clipBounds(const Reader & r, Value & value, const std::optional<ClipBounds> & parent)
{
    r.fields(value, {"op", "x", "y", "width", "height", "commands"});
    int64_t x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    ClipBounds bounds{x, y, x + r.integerAttr(value, "width", 0), y + r.integerAttr(value, "height", 0)};
    if (parent) {
        bounds.left = std::max(bounds.left, parent->left);
        bounds.top = std::max(bounds.top, parent->top);
        bounds.right = std::max(bounds.left, std::min(bounds.right, parent->right));
        bounds.bottom = std::max(bounds.top, std::min(bounds.bottom, parent->bottom));
    }
    return bounds;
}

Command clipCommand(ClipBounds bounds, std::optional<ClipBounds> parent, std::vector<Command> batch)
{
    return [bounds, parent, batch = std::move(batch)] {
        auto rectangle = windowBounds(bounds);
        if (!rectangle.width || !rectangle.height) return;
        ClipScope scope(rectangle, parent);
        for (const auto & command : batch) command();
    };
}

void pauseWindowClip()
{
    EndScissorMode();
}

void resumeWindowClip(const std::optional<ClipBounds> & parent)
{
    if (parent) beginClip(windowBounds(*parent));
}

SurfaceGuard::SurfaceGuard(int64_t width, int64_t height)
{
    surface = SurfaceSize{width, height};
}

SurfaceGuard::~SurfaceGuard()
{
    // Paint scopes never nest, so discarding beats restoring the previous value.
    surface = std::nullopt;
}

} // namespace nixray
