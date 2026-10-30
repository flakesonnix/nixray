#include "three_d.hh"
#include "reader.hh"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <raymath.h>
#include <rlgl.h>
#include <algorithm>
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

bool zero(Vector3 v) { return v.x == 0 && v.y == 0 && v.z == 0; }

Vector3 nativeUnit(const Reader & r, Vector3 v)
{
    // Match raymath's float operations: finite endpoints do not imply usable
    // differences, squared lengths, perpendiculars or cross products.
    float length = Vector3Length(v);
    if (!std::isfinite(length) || length == 0) r.fail("3D endpoint basis must be finite and nondegenerate");
    auto result = Vector3Normalize(v);
    float unitLength = Vector3Length(result);
    if (!std::isfinite(unitLength) || std::abs(unitLength - 1) > 0.001f)
        r.fail("3D endpoint basis must be finite and nondegenerate");
    return result;
}

void endpointBasis(const Reader & r, Vector3 start, Vector3 end)
{
    auto direction = Vector3Subtract(end, start);
    if (zero(direction)) return; // Native cylinder no-op / capsule sphere case.
    nativeUnit(r, direction);
    auto b1 = nativeUnit(r, Vector3Perpendicular(direction));
    nativeUnit(r, Vector3CrossProduct(b1, direction));
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
           op == "plane" || op == "line3D" || op == "grid" || op == "circle3D" ||
           op == "triangle3D" || op == "triangleStrip3D" || op == "cylinder" || op == "cylinderWires" ||
           op == "cylinderEx" || op == "cylinderWiresEx" || op == "capsule" || op == "capsuleWires";
}

Command shape3DCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    if (op == "circle3D") {
        r.fields(value, {"op", "position", "radius", "rotationAxis", "rotation", "color"});
        auto position = point(r, r.required(value, "position"));
        float radius = r.number(r.required(value, "radius"), "radius", 0);
        Vector3 axis{0, 0, 1};
        if (auto * v = r.optional(value, "rotationAxis")) axis = point(r, *v);
        double length = std::hypot(static_cast<double>(axis.x), static_cast<double>(axis.y), static_cast<double>(axis.z));
        if (length == 0) r.fail("circle3D rotation axis must be nonzero");
        axis = {static_cast<float>(axis.x/length), static_cast<float>(axis.y/length), static_cast<float>(axis.z/length)};
        double angle = 0;
        if (auto * v = r.optional(value, "rotation")) angle = r.numberDouble(*v, "rotation");
        float rotation = static_cast<float>(std::fmod(angle, 360.0));
        auto color = r.color(r.required(value, "color"));
        // Bound intermediate rotated x/y sums too, not only the final circle.
        bounds(r, position, 2.0*radius, 2.0*radius, 2.0*radius);
        return [=] { if (radius > 0) DrawCircle3D(position, radius, axis, rotation, color); };
    }
    if (op == "triangle3D" || op == "triangleStrip3D") {
        std::vector<Vector3> points;
        if (op == "triangle3D") {
            r.fields(value, {"op", "v1", "v2", "v3", "color"});
            for (auto field : {"v1", "v2", "v3"}) points.push_back(point(r, r.required(value, field)));
        } else {
            r.fields(value, {"op", "points", "color"});
            auto & list = r.required(value, "points");
            state.forceList(list, pos, context);
            if (list.listSize() < 3 || list.listSize() > 4096) r.fail("triangleStrip3D requires 3..4096 points");
            points.reserve(list.listSize());
            for (auto * v : list.listView()) points.push_back(point(r, *v));
        }
        auto color = r.color(r.required(value, "color"));
        return [op, points = std::move(points), color] {
            if (op == "triangle3D") DrawTriangle3D(points[0], points[1], points[2], color);
            else DrawTriangleStrip3D(points.data(), points.size(), color);
        };
    }
    if (op == "cylinder" || op == "cylinderWires") {
        r.fields(value, {"op", "position", "radiusTop", "radiusBottom", "height", "slices", "color"});
        auto position = point(r, r.required(value, "position"));
        float top = r.number(r.required(value, "radiusTop"), "radiusTop", 0);
        float bottom = r.number(r.required(value, "radiusBottom"), "radiusBottom", 0);
        float height = r.number(r.required(value, "height"), "height", 0);
        int slices = 16;
        if (auto * count = r.optional(value, "slices")) slices = r.integer(*count, "slices", 3, 256);
        auto color = r.color(r.required(value, "color"));
        double radius = std::max(top, bottom);
        bounds(r, position, radius, height, radius);
        return [=] {
            if (height == 0 || (top == 0 && bottom == 0)) return;
            if (op == "cylinder") DrawCylinder(position, top, bottom, height, slices, color);
            else DrawCylinderWires(position, top, bottom, height, slices, color);
        };
    }
    if (op == "cylinderEx" || op == "cylinderWiresEx" || op == "capsule" || op == "capsuleWires") {
        bool capsule = op == "capsule" || op == "capsuleWires";
        if (capsule) r.fields(value, {"op", "start", "end", "radius", "slices", "rings", "color"});
        else r.fields(value, {"op", "start", "end", "startRadius", "endRadius", "slices", "color"});
        auto start = point(r, r.required(value, "start")), end = point(r, r.required(value, "end"));
        float startRadius = r.number(r.required(value, capsule ? "radius" : "startRadius"), capsule ? "radius" : "startRadius", 0);
        float endRadius = capsule ? startRadius : r.number(r.required(value, "endRadius"), "endRadius", 0);
        int slices = 16, rings = 8;
        if (auto * count = r.optional(value, "slices")) slices = r.integer(*count, "slices", 3, 256);
        if (capsule) {
            if (auto * count = r.optional(value, "rings")) rings = r.integer(*count, "rings", 1, 128);
        }
        auto color = r.color(r.required(value, "color"));
        endpointBasis(r, start, end);
        // Native vertices accumulate two basis terms for cylinders and three
        // for caps. Conservative bounds cover the intermediate sums as well.
        double radius = (capsule ? 3.0 : 2.0)*std::max(startRadius, endRadius);
        bounds(r, start, radius, radius, radius);
        bounds(r, end, radius, radius, radius);
        return [=] {
            if (startRadius == 0 && endRadius == 0) return;
            if (op == "capsule") DrawCapsule(start, end, startRadius, slices, rings, color);
            else if (op == "capsuleWires") DrawCapsuleWires(start, end, startRadius, slices, rings, color);
            else if (op == "cylinderEx") DrawCylinderEx(start, end, startRadius, endRadius, slices, color);
            else DrawCylinderWiresEx(start, end, startRadius, endRadius, slices, color);
        };
    }
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
