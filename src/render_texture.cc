#include "render_texture.hh"
#include "blend.hh"
#include "texture.hh"

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
                     const std::optional<Camera2D> & camera, BlendMode parentBlend,
                     ShaderState parentShader, bool clear, std::vector<Command> batch)
{
    return [target, parent, camera, parentBlend, parentShader = std::move(parentShader), clear, batch = std::move(batch)] {
        if (parent) pauseWindowClip();
        {
            // Child clips clamp against the target, not against the window.
            SurfaceGuard guard{target.texture.width, target.texture.height};
            BeginTextureMode(target);
            // Target drawing starts with alpha, independently of its later stamps.
            BlendScope blend(BLEND_ALPHA, parentBlend);
            ShaderScope shader({}, parentShader);
            // Repainting replaces, never composes with, previous contents.
            if (clear) {
                rlClearColor(0.0f, 0.0f, 0.0f, 0.0f);
                rlClearScreenBuffers();
            }
            for (const auto & command : batch) command();
            EndTextureMode();
            refreshTextureMipmaps(target.texture);
        }
        // EndTextureMode restores the window viewport but keeps the suspended
        // scissor; re-apply both before following window commands.
        resumeWindowClip(parent);
        if (camera) BeginMode2D(*camera);
    };
}

} // namespace nixray
