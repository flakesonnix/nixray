#include "camera.hh"
#include "reader.hh"

#include <raymath.h>
#include <cmath>
#include <utility>

namespace nixray {

namespace {

Vector2 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y"});
    return {r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y")};
}

bool finiteMatrix(Matrix matrix)
{
    for (float value : MatrixToFloatV(matrix).v) if (!std::isfinite(value)) return false;
    return true;
}

struct CameraScope {
    std::optional<Camera2D> parent;

    CameraScope(Camera2D camera, std::optional<Camera2D> parent) : parent(parent) { BeginMode2D(camera); }
    ~CameraScope()
    {
        if (parent) BeginMode2D(*parent);
        else EndMode2D();
    }
    CameraScope(const CameraScope &) = delete;
    CameraScope & operator=(const CameraScope &) = delete;
};

void convertPoint(EvalState & state, PosIdx pos, Value ** args, Value & out, bool inverse)
{
    Reader r(state, pos);
    auto camera = cameraSpec(r, *args[0]);
    auto input = point(r, *args[1]);
    auto converted = inverse ? GetScreenToWorld2D(input, camera) : GetWorldToScreen2D(input, camera);
    if (!std::isfinite(converted.x) || !std::isfinite(converted.y))
        r.fail("converted point must have finite coordinates");
    auto result = state.buildBindings(2);
    result.alloc("x").mkFloat(converted.x);
    result.alloc("y").mkFloat(converted.y);
    out.mkAttrs(result);
}

} // namespace

Camera2D cameraSpec(const Reader & r, Value & value)
{
    r.fields(value, {"target", "offset", "zoom", "rotation"});
    Camera2D camera{};
    camera.zoom = 1;
    if (auto * target = r.optional(value, "target")) camera.target = point(r, *target);
    if (auto * offset = r.optional(value, "offset")) camera.offset = point(r, *offset);
    if (auto * zoom = r.optional(value, "zoom")) camera.zoom = r.number(*zoom, "zoom", 0);
    if (camera.zoom == 0) r.fail("'zoom' must be positive");
    if (auto * rotation = r.optional(value, "rotation")) camera.rotation = r.number(*rotation, "rotation");
    camera.rotation = std::fmod(camera.rotation, 360.0f);

    // Finite fields alone do not guarantee a usable native transform: products
    // can overflow, or a tiny zoom can make raylib's float inverse singular.
    auto matrix = GetCameraMatrix2D(camera);
    float determinant = matrix.m0 * matrix.m5 - matrix.m1 * matrix.m4;
    if (!finiteMatrix(matrix) || !std::isfinite(determinant) || determinant <= 0)
        r.fail("camera transform must be finite and invertible");
    auto inverse = MatrixInvert(matrix);
    if (!finiteMatrix(inverse) || inverse.m15 == 0)
        r.fail("camera transform must be finite and invertible");
    return camera;
}

Command cameraCommand(Camera2D camera, std::optional<Camera2D> parent, std::vector<Command> batch)
{
    return [camera, parent, batch = std::move(batch)] {
        // Begin/EndMode2D flush pending geometry before changing the matrix.
        CameraScope scope(camera, parent);
        for (const auto & command : batch) command();
    };
}

void worldToScreen2D(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    convertPoint(state, pos, args, out, false);
}

void screenToWorld2D(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    convertPoint(state, pos, args, out, true);
}

} // namespace nixray
