#include "shapes.hh"
#include "reader.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numbers>
#include <utility>

namespace nixray {

namespace {

constexpr int maxSegments = 4096;

Vector2 drawingPoint(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y"});
    return {static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y"))};
}

void addTriangle(std::vector<Vector2> & vertices, Vector2 a, Vector2 b, Vector2 c)
{
    double area = (static_cast<double>(b.x) - a.x)*(static_cast<double>(c.y) - a.y) -
                  (static_cast<double>(b.y) - a.y)*(static_cast<double>(c.x) - a.x);
    if (area == 0) return;
    if (area > 0) std::swap(b, c);
    vertices.insert(vertices.end(), {a, b, c});
}

void outwardBounds(const Reader & r, Rectangle rec, float thickness)
{
    double maximum = std::numeric_limits<float>::max();
    double w = rec.width + 2.0*thickness, h = rec.height + 2.0*thickness;
    if (w > maximum || h > maximum ||
        std::abs(static_cast<double>(rec.x) - thickness) > maximum ||
        std::abs(static_cast<double>(rec.y) - thickness) > maximum ||
        std::abs(static_cast<double>(rec.x) + rec.width + thickness) > maximum ||
        std::abs(static_cast<double>(rec.y) + rec.height + thickness) > maximum)
        r.fail("rounded rectangle outline bounds must remain finite");
}

int cornerSegments(float radius, bool outline)
{
    if (radius <= 0.5f) return 4;
    // Use doubles and an explicit bound rather than raylib's automatic path:
    // very small/large radii can otherwise convert NaN/infinity to an integer.
    double angle = 2 * std::acos(1 - 0.5 / static_cast<double>(radius));
    double count = std::ceil(2 * std::numbers::pi / angle / (outline ? 2 : 4));
    return static_cast<int>(std::clamp(count, 4.0, static_cast<double>(maxSegments)));
}

struct Arc {
    float start, end;
    int segments;
};

Arc arcSpec(const Reader & r, Value & value, float radius)
{
    // Check cross-field constraints before float rounding can conceal a violation.
    double start = r.numberDouble(r.required(value, "startAngle"), "startAngle");
    double end = r.numberDouble(r.required(value, "endAngle"), "endAngle");
    if (end < start) std::swap(start, end);
    double sweep = end - start;
    if (sweep > 360.0) r.fail("arc angle span must not exceed 360 degrees");
    start = std::fmod(start, 360.0);
    if (start < 0) start += 360.0;
    Arc arc{static_cast<float>(start), static_cast<float>(start + sweep), 0};
    if (auto * count = r.optional(value, "segments")) arc.segments = r.integer(*count, "segments", 0, maxSegments);
    // Never enter raylib's unsafe automatic path, even with a small explicit count.
    int minimum = std::max(1, static_cast<int>(std::ceil((arc.end - arc.start) / 90.0f)));
    if (!arc.segments) {
        double count = std::ceil(cornerSegments(radius, false) * 4.0 * sweep / 360.0);
        arc.segments = static_cast<int>(std::clamp(count, static_cast<double>(minimum), static_cast<double>(maxSegments)));
    } else arc.segments = std::max(arc.segments, minimum);
    return arc;
}

} // namespace

Command shapeCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    if (op == "triangleFan" || op == "triangleStrip") {
        r.fields(value, {"op", "points", "color"});
        auto & points = r.required(value, "points");
        state.forceList(points, pos, context);
        if (points.listSize() < 3 || points.listSize() > maxSegments)
            r.fail("'points' must contain between 3 and 4096 points");
        std::vector<Vector2> controls, triangles;
        controls.reserve(points.listSize());
        triangles.reserve((points.listSize() - 2)*3);
        for (auto * p : points.listView()) controls.push_back(drawingPoint(r, *p));
        for (size_t i = 2; i < controls.size(); ++i)
            addTriangle(triangles, controls[op == "triangleFan" ? 0 : i - 2], controls[i - 1], controls[i]);
        auto color = r.color(r.required(value, "color"));
        return [triangles = std::move(triangles), color] {
            for (size_t i = 0; i < triangles.size(); i += 3) DrawTriangle(triangles[i], triangles[i + 1], triangles[i + 2], color);
        };
    }
    if (op == "lineDashed") {
        r.fields(value, {"op", "x1", "y1", "x2", "y2", "dashSize", "spaceSize", "color"});
        Vector2 a{static_cast<float>(r.integerAttr(value, "x1")), static_cast<float>(r.integerAttr(value, "y1"))};
        Vector2 b{static_cast<float>(r.integerAttr(value, "x2")), static_cast<float>(r.integerAttr(value, "y2"))};
        int dash = r.integerAttr(value, "dashSize", 1), space = r.integerAttr(value, "spaceSize", 0);
        auto color = r.color(r.required(value, "color"));
        double dx = static_cast<double>(b.x) - a.x, dy = static_cast<double>(b.y) - a.y;
        double length = std::hypot(dx, dy), period = static_cast<double>(dash) + space;
        if (length == 0) return [] {};
        if (space == 0 || length < period) return [=] { DrawLineV(a, b, color); };
        double count = std::ceil(length/period);
        if (count > 65536) r.fail("dashed line must not exceed 65536 dashes");
        std::vector<std::array<Vector2, 2>> dashes;
        dashes.reserve(static_cast<size_t>(count));
        auto sample = [&](double distance) {
            double t = distance/length;
            return Vector2{static_cast<float>(a.x + t*dx), static_cast<float>(a.y + t*dy)};
        };
        // Do not call native DrawLineDashed's float-progress loop: at large
        // coordinates it can stop advancing, and dash + space can overflow int.
        for (size_t i = 0; i < static_cast<size_t>(count); ++i) {
            double start = i*period;
            auto from = sample(start), to = sample(std::min(length, start + dash));
            if (from.x != to.x || from.y != to.y) dashes.push_back({from, to});
        }
        return [dashes = std::move(dashes), color] { for (const auto & dash : dashes) DrawLineV(dash[0], dash[1], color); };
    }
    if (op == "rectanglePro" || op == "rectangleLinesEx") {
        bool outline = op == "rectangleLinesEx";
        r.fields(value, outline ? std::initializer_list<std::string_view>{"op", "x", "y", "width", "height", "thickness", "color"}
                                : std::initializer_list<std::string_view>{"op", "x", "y", "width", "height", "rotation", "origin", "color"});
        Rectangle rec{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y")),
                      static_cast<float>(r.integerAttr(value, "width", 0)), static_cast<float>(r.integerAttr(value, "height", 0))};
        auto color = r.color(r.required(value, "color"));
        if (outline) {
            float thickness = r.number(r.required(value, "thickness"), "thickness", 0);
            return [=] {
                if (rec.width == 0 || rec.height == 0 || thickness == 0) return;
                // Native borders can overlap (or invert) once they consume the
                // interior. Fill once instead, preserving translucent coverage.
                if (thickness >= std::min(rec.width, rec.height)/2) DrawRectangleRec(rec, color);
                else DrawRectangleLinesEx(rec, thickness, color);
            };
        }
        Vector2 origin{};
        if (auto * v = r.optional(value, "origin")) {
            r.fields(*v, {"x", "y"});
            origin = {r.number(r.required(*v, "x"), "origin.x"), r.number(r.required(*v, "y"), "origin.y")};
        }
        double angle = 0;
        if (auto * v = r.optional(value, "rotation")) angle = r.numberDouble(*v, "rotation");
        float rotation = static_cast<float>(std::fmod(angle, 360.0));
        double reachX = std::max(std::abs(static_cast<double>(origin.x)), std::abs(static_cast<double>(rec.width) - origin.x));
        double reachY = std::max(std::abs(static_cast<double>(origin.y)), std::abs(static_cast<double>(rec.height) - origin.y));
        if (std::hypot(reachX, reachY) > std::numeric_limits<float>::max()) r.fail("rotated rectangle bounds must remain finite");
        float sine = std::sin(rotation*DEG2RAD), cosine = std::cos(rotation*DEG2RAD);
        for (int corner = 0; corner < 4; ++corner) {
            float dx = -origin.x + (corner & 1 ? rec.width : 0), dy = -origin.y + (corner & 2 ? rec.height : 0);
            float x = rotation == 0 ? rec.x - origin.x + (corner & 1 ? rec.width : 0) : rec.x + dx*cosine - dy*sine;
            float y = rotation == 0 ? rec.y - origin.y + (corner & 2 ? rec.height : 0) : rec.y + dx*sine + dy*cosine;
            if (!std::isfinite(x) || !std::isfinite(y)) r.fail("rotated rectangle bounds must remain finite");
        }
        return [=] { if (rec.width > 0 && rec.height > 0) DrawRectanglePro(rec, origin, rotation, color); };
    }
    if (op == "poly" || op == "polyLines" || op == "polyLinesEx") {
        bool thick = op == "polyLinesEx";
        if (thick) r.fields(value, {"op", "x", "y", "sides", "radius", "rotation", "thickness", "color"});
        else r.fields(value, {"op", "x", "y", "sides", "radius", "rotation", "color"});
        Vector2 center{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y"))};
        int sides = r.integer(r.required(value, "sides"), "sides", 3, maxSegments);
        float radius = r.number(r.required(value, "radius"), "radius", 0);
        double angle = 0;
        if (auto * rotation = r.optional(value, "rotation")) angle = r.numberDouble(*rotation, "rotation");
        float rotation = static_cast<float>(std::fmod(angle, 360.0));
        float thickness = thick ? r.number(r.required(value, "thickness"), "thickness", 0) : 0;
        auto color = r.color(r.required(value, "color"));
        return [=] {
            if (radius == 0 || (thick && thickness == 0)) return;
            // Do not let a thick native contour invert its inner polygon.
            if (op == "poly" || (thick && thickness >= radius)) DrawPoly(center, sides, radius, rotation, color);
            else if (thick) DrawPolyLinesEx(center, sides, radius, rotation, thickness, color);
            else DrawPolyLines(center, sides, radius, rotation, color);
        };
    }
    if (op == "lineEx") {
        r.fields(value, {"op", "x1", "y1", "x2", "y2", "thickness", "color"});
        Vector2 start{static_cast<float>(r.integerAttr(value, "x1")), static_cast<float>(r.integerAttr(value, "y1"))};
        Vector2 end{static_cast<float>(r.integerAttr(value, "x2")), static_cast<float>(r.integerAttr(value, "y2"))};
        float thickness = r.number(r.required(value, "thickness"), "thickness", 0);
        auto color = r.color(r.required(value, "color"));
        return [=] { DrawLineEx(start, end, thickness, color); };
    }
    if (op == "rectangleGradientV" || op == "rectangleGradientH" || op == "rectangleGradientEx") {
        if (op == "rectangleGradientV") r.fields(value, {"op", "x", "y", "width", "height", "top", "bottom"});
        else if (op == "rectangleGradientH") r.fields(value, {"op", "x", "y", "width", "height", "left", "right"});
        else r.fields(value, {"op", "x", "y", "width", "height", "topLeft", "bottomLeft", "bottomRight", "topRight"});
        Rectangle rec{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y")),
                      static_cast<float>(r.integerAttr(value, "width", 0)), static_cast<float>(r.integerAttr(value, "height", 0))};
        Color topLeft, bottomLeft, bottomRight, topRight;
        if (op == "rectangleGradientV") {
            topLeft = topRight = r.color(r.required(value, "top"));
            bottomLeft = bottomRight = r.color(r.required(value, "bottom"));
        } else if (op == "rectangleGradientH") {
            topLeft = bottomLeft = r.color(r.required(value, "left"));
            topRight = bottomRight = r.color(r.required(value, "right"));
        } else {
            topLeft = r.color(r.required(value, "topLeft"));
            bottomLeft = r.color(r.required(value, "bottomLeft"));
            bottomRight = r.color(r.required(value, "bottomRight"));
            topRight = r.color(r.required(value, "topRight"));
        }
        return [=] {
            if (rec.width == 0 || rec.height == 0) return;
            DrawRectangleGradientEx(rec, topLeft, bottomLeft, bottomRight, topRight);
        };
    }
    if (op == "circleGradient") {
        r.fields(value, {"op", "x", "y", "radius", "inner", "outer"});
        int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
        float radius = r.number(r.required(value, "radius"), "radius", 0);
        auto inner = r.color(r.required(value, "inner")), outer = r.color(r.required(value, "outer"));
        return [=] { if (radius > 0) DrawCircleGradient(x, y, radius, inner, outer); };
    }
    if (op == "circleSector" || op == "circleSectorLines" || op == "ring" || op == "ringLines") {
        bool ring = op == "ring" || op == "ringLines";
        if (ring) r.fields(value, {"op", "x", "y", "innerRadius", "outerRadius", "startAngle", "endAngle", "segments", "color"});
        else r.fields(value, {"op", "x", "y", "radius", "startAngle", "endAngle", "segments", "color"});
        Vector2 center{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y"))};
        double inner = ring ? r.numberDouble(r.required(value, "innerRadius"), "innerRadius", 0) : 0;
        double outer = r.numberDouble(r.required(value, ring ? "outerRadius" : "radius"), ring ? "outerRadius" : "radius", 0);
        if (inner > outer) r.fail("innerRadius must not exceed outerRadius");
        float innerRadius = static_cast<float>(inner), outerRadius = static_cast<float>(outer);
        auto arc = arcSpec(r, value, outerRadius);
        auto color = r.color(r.required(value, "color"));
        return [=] {
            if (outerRadius == 0 || innerRadius == outerRadius || arc.start == arc.end) return;
            if (op == "ring") DrawRing(center, innerRadius, outerRadius, arc.start, arc.end, arc.segments, color);
            else if (op == "ringLines") DrawRingLines(center, innerRadius, outerRadius, arc.start, arc.end, arc.segments, color);
            else if (op == "circleSectorLines") DrawCircleSectorLines(center, outerRadius, arc.start, arc.end, arc.segments, color);
            else DrawCircleSector(center, outerRadius, arc.start, arc.end, arc.segments, color);
        };
    }
    if (op == "triangle" || op == "triangleLines") {
        r.fields(value, {"op", "x1", "y1", "x2", "y2", "x3", "y3", "color"});
        auto vertex = [&](const char * x, const char * y) {
            return Vector2{static_cast<float>(r.integerAttr(value, x)), static_cast<float>(r.integerAttr(value, y))};
        };
        auto a = vertex("x1", "y1"), b = vertex("x2", "y2"), c = vertex("x3", "y3");
        auto color = r.color(r.required(value, "color"));
        // Compute using the actual float vertices, without signed integer overflow.
        double area = (static_cast<double>(b.x) - a.x) * (static_cast<double>(c.y) - a.y) -
                      (static_cast<double>(b.y) - a.y) * (static_cast<double>(c.x) - a.x);
        if (area == 0) return [] {};
        // Raylib's filled triangles require counter-clockwise screen vertices.
        if (area > 0) std::swap(b, c);
        bool outline = op == "triangleLines";
        return [=] {
            if (outline) DrawTriangleLines(a, b, c, color);
            else DrawTriangle(a, b, c, color);
        };
    }
    if (op == "ellipse" || op == "ellipseLines") {
        r.fields(value, {"op", "x", "y", "radiusX", "radiusY", "color"});
        int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
        float radiusX = r.number(r.required(value, "radiusX"), "radiusX", 0);
        float radiusY = r.number(r.required(value, "radiusY"), "radiusY", 0);
        auto color = r.color(r.required(value, "color"));
        bool outline = op == "ellipseLines";
        return [=] {
            if (radiusX == 0 || radiusY == 0) return;
            if (outline) DrawEllipseLines(x, y, radiusX, radiusY, color);
            else DrawEllipse(x, y, radiusX, radiusY, color);
        };
    }
    if (op == "rectangleRounded" || op == "rectangleRoundedLines" || op == "rectangleRoundedLinesEx") {
        bool thick = op == "rectangleRoundedLinesEx";
        r.fields(value, thick ? std::initializer_list<std::string_view>{"op", "x", "y", "width", "height", "roundness", "segments", "thickness", "color"}
                              : std::initializer_list<std::string_view>{"op", "x", "y", "width", "height", "roundness", "segments", "color"});
        Rectangle rectangle{static_cast<float>(r.integerAttr(value, "x")),
                            static_cast<float>(r.integerAttr(value, "y")),
                            static_cast<float>(r.integerAttr(value, "width", 0)),
                            static_cast<float>(r.integerAttr(value, "height", 0))};
        float roundness = r.number(r.required(value, "roundness"), "roundness", 0, 1);
        int segments = 0;
        if (auto * count = r.optional(value, "segments")) segments = r.integer(*count, "segments", 0, maxSegments);
        if (segments > 0 && segments < 4) r.fail("'segments' must be 0 (automatic) or an integer in [4, 4096]");
        auto color = r.color(r.required(value, "color"));
        bool outline = op != "rectangleRounded";
        float thickness = thick ? r.number(r.required(value, "thickness"), "thickness", 0) : 0;
        if (thick) outwardBounds(r, rectangle, thickness);
        float radius = std::min(rectangle.width, rectangle.height) * roundness / 2;
        if (radius == 0) roundness = 0;
        if (!segments) segments = cornerSegments(radius + thickness, outline);
        return [=] {
            if (rectangle.width == 0 || rectangle.height == 0) return;
            if (thick) { if (thickness > 0) DrawRectangleRoundedLinesEx(rectangle, roundness, segments, thickness, color); }
            else if (outline) DrawRectangleRoundedLines(rectangle, roundness, segments, color);
            else DrawRectangleRounded(rectangle, roundness, segments, color);
        };
    }
    r.fail("unknown shape operation '" + op + "'");
}

} // namespace nixray
