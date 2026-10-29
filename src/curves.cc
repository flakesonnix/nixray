#include "curves.hh"
#include "reader.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <utility>

namespace nixray {

namespace {

constexpr size_t maxPoints = 4096, maxIntervals = 65536;

Vector2 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y"});
    return {static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y"))};
}

// Evaluate the usual spline weights relative to one control point. Double
// intermediates avoid cancellation and keep constant spans exactly constant.
Vector2 sample(const Vector2 * p, const std::string & op, double t)
{
    double u = 1 - t;
    std::array<double, 4> w{};
    if (op == "splineBasis") w = {u*u*u/6, (3*t*t*t - 6*t*t + 4)/6, (-3*t*t*t + 3*t*t + 3*t + 1)/6, t*t*t/6};
    else if (op == "splineCatmullRom") w = {(-t*t*t + 2*t*t - t)/2, (3*t*t*t - 5*t*t + 2)/2,
                                           (-3*t*t*t + 4*t*t + t)/2, (t*t*t - t*t)/2};
    else if (op == "splineBezierQuadratic") w = {u*u, 2*u*t, t*t, 0};
    else w = {u*u*u, 3*u*u*t, 3*u*t*t, t*t*t};
    double x = p[0].x, y = p[0].y;
    size_t count = op == "splineBezierQuadratic" ? 3 : 4;
    for (size_t i = 1; i < count; ++i) {
        x += w[i] * (static_cast<double>(p[i].x) - p[0].x);
        y += w[i] * (static_cast<double>(p[i].y) - p[0].y);
    }
    return {static_cast<float>(x), static_cast<float>(y)};
}

void appendPoint(std::vector<Vector2> & path, Vector2 p)
{
    if (!path.empty() && p.x == path.back().x && p.y == path.back().y) return;
    while (path.size() >= 2) {
        auto a = path[path.size() - 2], b = path.back();
        double dx = static_cast<double>(b.x) - a.x, dy = static_cast<double>(b.y) - a.y;
        double ex = static_cast<double>(p.x) - b.x, ey = static_cast<double>(p.y) - b.y;
        if (dx*ey != dy*ex || dx*ex + dy*ey < 0) break;
        // Collinear subdivisions do not change the stroke. Merging them avoids
        // rasterization cracks from thousands of subpixel-width triangles.
        path.pop_back();
    }
    path.push_back(p);
}

Command stroke(const Reader & r, const std::vector<Vector2> & path, float thickness, Color color)
{
    if (path.size() < 2 || thickness == 0) return [] {};
    // Share cross-sections between intervals: ordinary joins do not repeatedly
    // alpha-blend independent segment rectangles. Bound miter reach to one full
    // thickness, avoiding unbounded spikes at near reversals.
    struct Normal { double x, y; };
    std::vector<Normal> normals;
    normals.reserve(path.size() - 1);
    for (size_t i = 1; i < path.size(); ++i) {
        double dx = static_cast<double>(path[i].x) - path[i - 1].x;
        double dy = static_cast<double>(path[i].y) - path[i - 1].y;
        double length = std::hypot(dx, dy);
        normals.push_back({-dy/length, dx/length});
    }
    auto vertex = [&](double x, double y) {
        if (!std::isfinite(x) || !std::isfinite(y) || std::abs(x) > std::numeric_limits<float>::max() ||
            std::abs(y) > std::numeric_limits<float>::max()) r.fail("curve stroke coordinates must remain finite");
        return Vector2{static_cast<float>(x), static_cast<float>(y)};
    };
    auto section = [&](size_t i, bool outgoing) {
        auto n = normals[i == 0 ? 0 : i - 1];
        double reach = thickness/2.0;
        if (i > 0 && i + 1 < path.size()) {
            double nx = n.x + normals[i].x, ny = n.y + normals[i].y;
            double length = std::hypot(nx, ny);
            if (length > 0) {
                n = {nx/length, ny/length};
                reach *= std::min(2.0, 2.0/length);
            } else if (outgoing) n = normals[i]; // Exact retraces meet as separate butt caps.
        }
        return std::array<Vector2, 2>{vertex(path[i].x + n.x*reach, path[i].y + n.y*reach),
                                      vertex(path[i].x - n.x*reach, path[i].y - n.y*reach)};
    };
    std::vector<Vector2> triangles;
    triangles.reserve((path.size() - 1)*6);
    auto triangle = [&](Vector2 a, Vector2 b, Vector2 c) {
        double area = (static_cast<double>(b.x) - a.x)*(static_cast<double>(c.y) - a.y) -
                      (static_cast<double>(b.y) - a.y)*(static_cast<double>(c.x) - a.x);
        if (area == 0) return;
        if (area > 0) std::swap(b, c);
        triangles.insert(triangles.end(), {a, b, c});
    };
    for (size_t i = 1; i < path.size(); ++i) {
        auto previous = section(i - 1, true), current = section(i, false);
        triangle(previous[0], previous[1], current[0]);
        triangle(current[0], previous[1], current[1]);
    }
    return [triangles = std::move(triangles), color] {
        for (size_t i = 0; i < triangles.size(); i += 3)
            DrawTriangle(triangles[i], triangles[i + 1], triangles[i + 2], color);
    };
}

} // namespace

Command curveCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    bool connector = op == "lineBezier", linear = op == "splineLinear";
    if (connector) r.fields(value, {"op", "x1", "y1", "x2", "y2", "thickness", "segments", "color"});
    else if (linear) r.fields(value, {"op", "points", "thickness", "color"});
    else r.fields(value, {"op", "points", "thickness", "segments", "color"});
    float thickness = r.number(r.required(value, "thickness"), "thickness", 0);
    auto color = r.color(r.required(value, "color"));
    int segments = 24;
    if (!linear) {
        if (auto * count = r.optional(value, "segments")) segments = r.integer(*count, "segments", 1, 4096);
    }
    std::vector<Vector2> controls;
    if (connector) {
        controls = {{static_cast<float>(r.integerAttr(value, "x1")), static_cast<float>(r.integerAttr(value, "y1"))},
                    {static_cast<float>(r.integerAttr(value, "x2")), static_cast<float>(r.integerAttr(value, "y2"))}};
    } else {
        auto & points = r.required(value, "points");
        state.forceList(points, pos, context);
        size_t count = points.listSize();
        size_t minimum = linear ? 2 : op == "splineBezierQuadratic" ? 3 : 4;
        if (count < minimum || count > maxPoints)
            r.fail("'points' must contain between " + std::to_string(minimum) + " and 4096 points");
        if (op == "splineBezierQuadratic" && count % 2 != 1)
            r.fail("quadratic Bezier points must contain complete spans (2n + 1 points)");
        if (op == "splineBezierCubic" && (count - 1) % 3 != 0)
            r.fail("cubic Bezier points must contain complete spans (3n + 1 points)");
        controls.reserve(count);
        for (auto * entry : points.listView()) controls.push_back(point(r, *entry));
    }
    if (linear) {
        std::vector<Vector2> path;
        for (auto p : controls) appendPoint(path, p);
        return stroke(r, path, thickness, color);
    }
    size_t step = op == "splineBezierQuadratic" ? 2 : op == "splineBezierCubic" ? 3 : 1;
    size_t spans = connector ? 1 : (op == "splineBasis" || op == "splineCatmullRom") ? controls.size() - 3 : (controls.size() - 1)/step;
    size_t intervals = spans * static_cast<size_t>(segments);
    if (intervals > maxIntervals) r.fail("curve sampling must not exceed 65536 intervals per command");
    std::vector<Vector2> path;
    path.reserve(intervals + 1);
    for (size_t span = 0; span < spans; ++span) {
        for (int j = span == 0 ? 0 : 1; j <= segments; ++j) {
            double t = static_cast<double>(j)/segments;
            Vector2 p;
            if (connector) {
                // Match raylib's eased connector: linear x, cubic ease-in/out y.
                double u = 1 - t, eased = t < 0.5 ? 4*t*t*t : 1 - 4*u*u*u;
                p = {static_cast<float>(controls[0].x + t*(static_cast<double>(controls[1].x) - controls[0].x)),
                     static_cast<float>(controls[0].y + eased*(static_cast<double>(controls[1].y) - controls[0].y))};
            } else p = sample(controls.data() + span*step, op, t);
            // Repeated controls and float-rounded samples are valid, not 0/0 normals.
            appendPoint(path, p);
        }
    }
    return stroke(r, path, thickness, color);
}

} // namespace nixray
