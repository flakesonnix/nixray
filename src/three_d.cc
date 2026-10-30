#include "three_d.hh"
#include "reader.hh"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <raymath.h>
#include <rlgl.h>
#include <cmath>
#include <limits>
#include <utility>

namespace nixray {

namespace {

Vector3 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y", "z"});
    return {r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y"),
            r.number(r.required(value, "z"), "z")};
}

bool finiteMatrix(Matrix matrix)
{
    for (float value : MatrixToFloatV(matrix).v) if (!std::isfinite(value)) return false;
    return true;
}

void usableMatrix(const Reader & r, Matrix matrix)
{
    float determinant = MatrixDeterminant(matrix);
    if (!finiteMatrix(matrix) || !std::isfinite(determinant) || determinant == 0 || !finiteMatrix(MatrixInvert(matrix)))
        r.fail("3D camera transform must be finite and invertible");
}

void bounds(const Reader & r, Vector3 position, double x, double y, double z)
{
    double maximum = std::numeric_limits<float>::max();
    if (std::abs(static_cast<double>(position.x)) + x > maximum ||
        std::abs(static_cast<double>(position.y)) + y > maximum ||
        std::abs(static_cast<double>(position.z)) + z > maximum)
        r.fail("3D geometry bounds must fit finite native coordinates");
}

struct Mode3D {
    std::optional<Camera2D> parent;
    Mode3D(Camera3D camera, std::optional<Camera2D> parent) : parent(parent) { BeginMode3D(camera); }
    ~Mode3D()
    {
        EndMode3D();
        if (parent) BeginMode2D(*parent);
    }
    Mode3D(const Mode3D &) = delete;
    Mode3D & operator=(const Mode3D &) = delete;
};

} // namespace

void validateProjection3D(const Reader & r, Camera3D camera, double aspect)
{
    if (!std::isfinite(aspect) || aspect <= 0) r.fail("3D camera surface aspect must be positive and finite");
    // Match the linked raylib headers' default clip planes; this API never
    // changes rlgl's global near/far distances. No GL context is needed here.
    double top = camera.projection == CAMERA_PERSPECTIVE
        ? RL_CULL_DISTANCE_NEAR * std::tan(static_cast<double>(camera.fovy)*0.5*DEG2RAD)
        : camera.fovy/2.0;
    double right = top*aspect;
    auto projection = camera.projection == CAMERA_PERSPECTIVE
        ? MatrixFrustum(-right, right, -top, top, RL_CULL_DISTANCE_NEAR, RL_CULL_DISTANCE_FAR)
        : MatrixOrtho(-right, right, -top, top, RL_CULL_DISTANCE_NEAR, RL_CULL_DISTANCE_FAR);
    usableMatrix(r, projection);
    usableMatrix(r, MatrixMultiply(GetCameraMatrix(camera), projection));
}

Camera3D camera3DSpec(const Reader & r, Value & value)
{
    r.fields(value, {"position", "target", "up", "fovy", "projection"});
    Camera3D camera{{0, 0, 10}, {0, 0, 0}, {0, 1, 0}, 45, CAMERA_PERSPECTIVE};
    if (auto * position = r.optional(value, "position")) camera.position = point(r, *position);
    if (auto * target = r.optional(value, "target")) camera.target = point(r, *target);
    if (auto * up = r.optional(value, "up")) camera.up = point(r, *up);
    if (auto * projection = r.optional(value, "projection")) {
        auto name = r.string(*projection);
        if (name == "perspective") camera.projection = CAMERA_PERSPECTIVE;
        else if (name == "orthographic") camera.projection = CAMERA_ORTHOGRAPHIC;
        else r.fail("unknown 3D camera projection '" + name + "'");
    }
    if (auto * fovy = r.optional(value, "fovy")) camera.fovy = r.number(*fovy, "fovy", 0);
    if (camera.fovy <= 0 || (camera.projection == CAMERA_PERSPECTIVE && camera.fovy >= 180))
        r.fail("3D camera fovy must be positive, and below 180 degrees for perspective");
    usableMatrix(r, GetCameraMatrix(camera));
    validateProjection3D(r, camera, 1);
    return camera;
}

Command camera3DCommand(const Reader & r, Camera3D camera, std::optional<Camera2D> parent,
                        bool clearDepth, bool loaded, std::vector<Command> batch)
{
    using Clear = void (*)(unsigned);
    Clear clear = nullptr;
    if (loaded && clearDepth) {
        clear = reinterpret_cast<Clear>(glfwGetProcAddress("glClear"));
        if (!clear) r.fail("3D depth clearing is unavailable in this OpenGL context");
    }
    return [=, batch = std::move(batch)] {
        // BeginMode3D uses the active FBO's aspect and flushes queued 2D work.
        Mode3D scope(camera, parent);
        if (clearDepth) clear(0x00000100); // GL_DEPTH_BUFFER_BIT; preserve color and obey scissoring.
        for (const auto & command : batch) command();
    };
}

bool isShape3D(const std::string & op)
{
    return op == "cube" || op == "cubeWires" || op == "sphere" || op == "sphereWires" ||
           op == "plane" || op == "line3D" || op == "grid";
}

Command shape3DCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    if (op == "grid") {
        r.fields(value, {"op", "slices", "spacing"});
        int slices = r.integer(r.required(value, "slices"), "slices", 0, 4096);
        float spacing = r.number(r.required(value, "spacing"), "spacing", 0);
        bounds(r, {}, (slices/2)*static_cast<double>(spacing), 0, (slices/2)*static_cast<double>(spacing));
        return [=] { if (slices >= 2 && spacing > 0) DrawGrid(slices, spacing); };
    }
    if (op == "line3D") {
        r.fields(value, {"op", "start", "end", "color"});
        auto start = point(r, r.required(value, "start")), end = point(r, r.required(value, "end"));
        auto color = r.color(r.required(value, "color"));
        return [=] { if (start.x != end.x || start.y != end.y || start.z != end.z) DrawLine3D(start, end, color); };
    }
    if (op == "sphere" || op == "sphereWires") {
        r.fields(value, {"op", "position", "radius", "rings", "slices", "color"});
        auto position = point(r, r.required(value, "position"));
        float radius = r.number(r.required(value, "radius"), "radius", 0);
        int rings = 16, slices = 16;
        if (auto * count = r.optional(value, "rings")) rings = r.integer(*count, "rings", 2, 128);
        if (auto * count = r.optional(value, "slices")) slices = r.integer(*count, "slices", 3, 256);
        auto color = r.color(r.required(value, "color"));
        bounds(r, position, radius, radius, radius);
        return [=] {
            if (radius == 0) return;
            if (op == "sphere") DrawSphereEx(position, radius, rings, slices, color);
            else DrawSphereWires(position, radius, rings, slices, color);
        };
    }
    bool plane = op == "plane";
    if (plane) r.fields(value, {"op", "position", "width", "length", "color"});
    else r.fields(value, {"op", "position", "width", "height", "length", "color"});
    auto position = point(r, r.required(value, "position"));
    float width = r.number(r.required(value, "width"), "width", 0);
    float height = plane ? 1 : r.number(r.required(value, "height"), "height", 0);
    float length = r.number(r.required(value, "length"), "length", 0);
    auto color = r.color(r.required(value, "color"));
    bounds(r, position, width/2.0, plane ? 0 : height/2.0, length/2.0);
    return [=] {
        if (width == 0 || height == 0 || length == 0) return;
        if (plane) DrawPlane(position, {width, length}, color);
        else if (op == "cube") DrawCube(position, width, height, length, color);
        else DrawCubeWires(position, width, height, length, color);
    };
}

} // namespace nixray
