#include "render_texture.hh"

#include <rlgl.h>
#include <utility>

namespace nixray {

void initializeRenderTexture(RenderTexture2D target)
{
    // BeginTextureMode flushes queued geometry before switching targets.
    BeginTextureMode(target);
    rlClearColor(0.0f, 0.0f, 0.0f, 0.0f);
    rlClearScreenBuffers();
    EndTextureMode();
}

Command paintCommand(RenderTexture2D target, const std::optional<ClipBounds> & parent,
                     const std::optional<Camera2D> & camera, bool clear, std::vector<Command> batch)
{
    return [target, parent, camera, clear, batch = std::move(batch)] {
        if (parent) pauseWindowClip();
        {
            // Child clips clamp against the target, not against the window.
            SurfaceGuard guard{target.texture.width, target.texture.height};
            BeginTextureMode(target);
            // Repainting replaces, never composes with, previous contents.
            if (clear) {
                rlClearColor(0.0f, 0.0f, 0.0f, 0.0f);
                rlClearScreenBuffers();
            }
            for (const auto & command : batch) command();
            EndTextureMode();
        }
        // EndTextureMode restores the window viewport but keeps the suspended
        // scissor; re-apply both before following window commands.
        resumeWindowClip(parent);
        if (camera) BeginMode2D(*camera);
    };
}

} // namespace nixray
