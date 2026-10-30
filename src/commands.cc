#include "commands.hh"
#include "assets.hh"
#include "reader.hh"
#include "texture.hh"
#include "text.hh"
#include "shapes.hh"
#include "curves.hh"
#include "clip.hh"
#include "camera.hh"
#include "blend.hh"
#include "render_texture.hh"
#include "shader.hh"
#include "three_d.hh"
#include "model.hh"
#include "lighting.hh"

#include <rlgl.h>
#include <utility>

namespace nixray {

namespace {

struct Scene3D {
    Camera3D camera;
    std::optional<LightingSpec> lighting;
    MaterialSpec material;
};

// Parse every command before BeginDrawing: evaluation errors cannot leave an
// unfinished drawing batch, and command execution never re-enters the evaluator.
// activeTexture names a render texture currently receiving output, if any.
std::vector<Command> compileCommands(EvalState & state, PosIdx pos, Value & value, const Assets * assets,
                                     std::optional<ClipBounds> parent, std::optional<Camera2D> activeCamera,
                                     const std::string * activeTexture, BlendMode activeBlend,
                                     const ShaderState & activeShader, unsigned depth, std::optional<Scene3D> scene)
{
    Reader r(state, pos);
    bool in3D = scene.has_value();
    state.forceList(value, pos, context);
    std::vector<Command> result;
    result.reserve(value.listSize());
    auto values = value.listView();
    for (auto * entry : values) {
        auto op = r.string(r.required(*entry, "op"));
        bool model = op == "model" || op == "modelWires";
        if (in3D && !isShape3D(op) && !model && op != "clip" && op != "blend" && op != "shader" && op != "clear" && op != "lighting" && op != "material")
            r.fail("drawing operation '" + op + "' is not supported inside camera3D");
        if (isShape3D(op) || model) {
            if (!in3D) r.fail("3D drawing operation '" + op + "' requires a camera3D scope");
            bool vertexNormals = op == "model" || op == "cube" || op == "sphere" || op == "plane";
            bool solid = vertexNormals || op == "triangle3D" || op == "triangleStrip3D" || op == "cylinder" ||
                         op == "cylinderEx" || op == "capsule";
            const LightingShader * lighting = scene->lighting && solid && assets ? &assets->lighting(r) : nullptr;
            const Shader * shader = lighting ? &lighting->resource.program : activeShader.asset ? &activeShader.asset->program : nullptr;
            auto draw = model ? modelCommand(state, pos, *entry, op, assets, shader) : shape3DCommand(state, pos, *entry, op);
            if (lighting) {
                bool normals = vertexNormals;
                if (model) {
                    auto name = r.string(r.required(*entry, "model"));
                    normals = assets->model(name)->hasVertexNormals;
                }
                draw = litCommand(*lighting, *scene->lighting, scene->material, scene->camera, model, normals, std::move(draw));
            }
            result.emplace_back(std::move(draw));
            continue;
        }
        if (op == "shader") {
            if (scene && scene->lighting) r.fail("custom shader and lighting scopes must not overlap");
            if (depth >= 64) r.fail("shader nesting must not exceed 64 levels");
            auto shader = shaderState(state, pos, *entry, assets);
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, parent, activeCamera,
                                         activeTexture, activeBlend, shader, depth + 1, scene);
            result.emplace_back(shaderCommand(std::move(shader), activeShader, std::move(batch)));
        } else if (op == "blend") {
            if (depth >= 64) r.fail("blend nesting must not exceed 64 levels");
            r.fields(*entry, {"op", "mode", "commands"});
            auto mode = blendMode(r, r.required(*entry, "mode"));
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, parent, activeCamera,
                                         activeTexture, mode, activeShader, depth + 1, scene);
            result.emplace_back(blendCommand(mode, activeBlend, std::move(batch)));
        } else if (op == "lighting" || op == "material") {
            if (!scene) r.fail(op + " scope requires a camera3D scope");
            if (depth >= 64) r.fail(op + " nesting must not exceed 64 levels");
            auto child = *scene;
            if (op == "lighting") {
                if (activeShader.explicitScope) r.fail("custom shader and lighting scopes must not overlap");
                child.lighting = lightingSpec(state, pos, *entry);
            } else {
                if (!child.lighting) r.fail("material scope requires a lighting scope");
                child.material = materialSpec(state, pos, *entry);
            }
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, parent, activeCamera,
                                         activeTexture, activeBlend, activeShader, depth + 1, std::move(child));
            result.emplace_back([batch = std::move(batch)] { for (const auto & command : batch) command(); });
        } else if (op == "camera3D") {
            if (depth >= 64) r.fail("camera nesting must not exceed 64 levels");
            r.fields(*entry, {"op", "camera", "commands", "clearDepth"});
            auto camera = camera3DSpec(r, r.required(*entry, "camera"));
            bool clearDepth = r.defaultBool(*entry, "clearDepth", true);
            if (assets) {
                auto * target = activeTexture ? assets->renderTexture(*activeTexture) : nullptr;
                double width = target ? target->texture.width : GetScreenWidth();
                double height = target ? target->texture.height : GetScreenHeight();
                validateProjection3D(r, camera, width/height);
            }
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, parent, activeCamera,
                                         activeTexture, activeBlend, activeShader, depth + 1, Scene3D{camera, std::nullopt, {}});
            result.emplace_back(camera3DCommand(r, camera, activeCamera, clearDepth, assets != nullptr, std::move(batch)));
        } else if (op == "camera2D") {
            if (depth >= 64) r.fail("camera nesting must not exceed 64 levels");
            r.fields(*entry, {"op", "camera", "commands"});
            auto camera = cameraSpec(r, r.required(*entry, "camera"));
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, parent, camera,
                                         activeTexture, activeBlend, activeShader, depth + 1, std::nullopt);
            result.emplace_back(cameraCommand(camera, activeCamera, std::move(batch)));
        } else if (op == "clip") {
            if (depth >= 64) r.fail("clip nesting must not exceed 64 levels");
            auto bounds = clipBounds(r, *entry, parent);
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, bounds, activeCamera,
                                         activeTexture, activeBlend, activeShader, depth + 1, scene);
            result.emplace_back(clipCommand(bounds, parent, std::move(batch)));
        } else if (op == "paint") {
            if (depth >= 64) r.fail("paint nesting must not exceed 64 levels");
            if (activeTexture) r.fail("paint must not nest inside another paint");
            r.fields(*entry, {"op", "texture", "commands", "clear"});
            auto name = r.string(r.required(*entry, "texture"));
            if (name.empty()) r.fail("texture name must not be empty");
            bool clear = r.defaultBool(*entry, "clear", true);
            RenderTexture2D target{};
            if (assets) {
                if (auto * found = assets->renderTexture(name)) target = *found;
                else if (assets->texture(name)) r.fail("texture '" + name + "' is not a render texture");
                else r.fail("unknown render texture '" + name + "'");
            }
            // Paint children start a fresh texture coordinate system without
            // inherited clip bounds, cameras, blend modes or shaders.
            auto batch = compileCommands(state, pos, r.required(*entry, "commands"), assets, std::nullopt,
                                         std::nullopt, &name, BLEND_ALPHA, {}, depth + 1, std::nullopt);
            result.emplace_back(paintCommand(target, parent, activeCamera, activeBlend, activeShader, clear, std::move(batch)));
        } else if (op == "clear") {
            r.fields(*entry, {"op", "color"});
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] {
                // ClearBackground clears immediately; preserve list order even
                // when earlier geometry is still queued inside a clip scope.
                rlDrawRenderBatchActive();
                ClearBackground(color);
            });
        } else if (op == "texture") {
            result.emplace_back(textureCommand(state, pos, *entry, assets, activeTexture));
        } else if (op == "textureNPatch") {
            result.emplace_back(texturePatchCommand(state, pos, *entry, assets, activeTexture));
        } else if (op == "text" || op == "textCodepoint" || op == "textCodepoints") {
            result.emplace_back(textCommand(state, pos, *entry, op, assets));
        } else if (op == "lineBezier" || op == "splineLinear" || op == "splineBasis" || op == "splineCatmullRom" ||
                   op == "splineBezierQuadratic" || op == "splineBezierCubic") {
            result.emplace_back(curveCommand(state, pos, *entry, op));
        } else if (op == "triangle" || op == "triangleLines" || op == "ellipse" || op == "ellipseLines" ||
                   op == "rectangleRounded" || op == "rectangleRoundedLines" || op == "lineEx" ||
                   op == "rectangleGradientV" || op == "rectangleGradientH" || op == "rectangleGradientEx" ||
                   op == "circleGradient" || op == "circleSector" || op == "circleSectorLines" ||
                   op == "ring" || op == "ringLines" || op == "poly" || op == "polyLines" || op == "polyLinesEx" ||
                   op == "lineDashed" || op == "rectanglePro" || op == "rectangleLinesEx" || op == "rectangleRoundedLinesEx" ||
                   op == "triangleFan" || op == "triangleStrip") {
            result.emplace_back(shapeCommand(state, pos, *entry, op));
        } else if (op == "rectangle" || op == "rectangleLines") {
            r.fields(*entry, {"op", "x", "y", "width", "height", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            int w = r.integerAttr(*entry, "width", 0), h = r.integerAttr(*entry, "height", 0);
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] {
                if (op == "rectangle") DrawRectangle(x, y, w, h, color);
                else DrawRectangleLines(x, y, w, h, color);
            });
        } else if (op == "circle" || op == "circleLines") {
            r.fields(*entry, {"op", "x", "y", "radius", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            float radius = r.number(r.required(*entry, "radius"), "radius", 0);
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] {
                if (op == "circle") DrawCircle(x, y, radius, color);
                else DrawCircleLines(x, y, radius, color);
            });
        } else if (op == "line") {
            r.fields(*entry, {"op", "x1", "y1", "x2", "y2", "color"});
            int x1 = r.integerAttr(*entry, "x1"), y1 = r.integerAttr(*entry, "y1");
            int x2 = r.integerAttr(*entry, "x2"), y2 = r.integerAttr(*entry, "y2");
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { DrawLine(x1, y1, x2, y2, color); });
        } else if (op == "pixel") {
            r.fields(*entry, {"op", "x", "y", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { DrawPixel(x, y, color); });
        } else if (op == "fps") {
            r.fields(*entry, {"op", "x", "y"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            result.emplace_back([=] { DrawFPS(x, y); });
        } else {
            r.fail("unknown drawing operation '" + op + "'");
        }
    }
    return result;
}

} // namespace

std::vector<Command> commands(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    return compileCommands(state, pos, value, assets, std::nullopt, std::nullopt, nullptr, BLEND_ALPHA, {}, 0, std::nullopt);
}

} // namespace nixray
