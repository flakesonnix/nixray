#include <nix/expr/eval.hh>
#include <nix/expr/eval-settings.hh>
#include <nix/expr/primops.hh>
#include <nix/util/signals.hh>
#include <raylib.h>

#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <limits>
#include <string>
#include <vector>

namespace {

using namespace nix;
constexpr auto context = "while evaluating a nixray argument";

class Reader {
    EvalState & state;
    PosIdx pos;

public:
    Reader(EvalState & state, PosIdx pos) : state(state), pos(pos) {}

    [[noreturn]] void fail(const std::string & message) const
    {
        state.error<EvalError>("nixray: %s", message).atPos(pos).debugThrow();
    }

    Value * optional(Value & value, const char * name) const
    {
        state.forceAttrs(value, pos, context);
        const auto * attr = value.attrs()->get(state.symbols.create(name));
        return attr ? attr->value : nullptr;
    }

    Value & required(Value & value, const char * name) const
    {
        if (auto * found = optional(value, name)) return *found;
        fail(std::string("missing attribute '") + name + "'");
    }

    void fields(Value & value, std::initializer_list<std::string_view> allowed) const
    {
        state.forceAttrs(value, pos, context);
        for (const auto & attr : *value.attrs()) {
            const std::string_view name = state.symbols[attr.name];
            bool known = false;
            for (auto field : allowed) known |= name == field;
            if (!known) fail("unknown attribute '" + std::string(name) + "'");
        }
    }

    int integer(Value & value, const char * name, int minimum = std::numeric_limits<int>::min(),
                int maximum = std::numeric_limits<int>::max()) const
    {
        auto n = state.forceInt(value, pos, context).value;
        if (n < minimum || n > maximum)
            fail(std::string("'") + name + "' must be an integer in [" +
                 std::to_string(minimum) + ", " + std::to_string(maximum) + "]");
        return static_cast<int>(n);
    }

    int integerAttr(Value & value, const char * name, int minimum = std::numeric_limits<int>::min()) const
    {
        return integer(required(value, name), name, minimum);
    }

    int defaultInt(Value & value, const char * name, int fallback, int minimum = 0) const
    {
        auto * found = optional(value, name);
        return found ? integer(*found, name, minimum) : fallback;
    }

    float number(Value & value, const char * name, float minimum = -std::numeric_limits<float>::max()) const
    {
        double n = state.forceFloat(value, pos, context);
        if (!std::isfinite(n) || n < minimum || n > std::numeric_limits<float>::max())
            fail(std::string("'") + name + "' must be a finite number in range");
        return static_cast<float>(n);
    }

    bool defaultBool(Value & value, const char * name, bool fallback) const
    {
        auto * found = optional(value, name);
        return found ? state.forceBool(*found, pos, context) : fallback;
    }

    std::string string(Value & value) const
    {
        auto text = state.forceStringNoCtx(value, pos, context);
        if (text.find('\0') != std::string_view::npos) fail("strings must not contain NUL bytes");
        return std::string(text);
    }

    Color color(Value & value) const
    {
        state.forceList(value, pos, context);
        if (value.listSize() != 4) fail("color must be [ red green blue alpha ]");
        auto channels = value.listView();
        return {
            static_cast<unsigned char>(integer(*channels[0], "red", 0, 255)),
            static_cast<unsigned char>(integer(*channels[1], "green", 0, 255)),
            static_cast<unsigned char>(integer(*channels[2], "blue", 0, 255)),
            static_cast<unsigned char>(integer(*channels[3], "alpha", 0, 255)),
        };
    }
};

// Parse every command before BeginDrawing: evaluation errors cannot leave an
// unfinished drawing batch, and command execution never re-enters the evaluator.
using Command = std::function<void()>;

std::vector<Command> commands(EvalState & state, PosIdx pos, Value & value)
{
    Reader r(state, pos);
    state.forceList(value, pos, context);
    std::vector<Command> result;
    result.reserve(value.listSize());
    auto values = value.listView();
    for (auto * entry : values) {
        auto op = r.string(r.required(*entry, "op"));
        if (op == "clear") {
            r.fields(*entry, {"op", "color"});
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { ClearBackground(color); });
        } else if (op == "text") {
            r.fields(*entry, {"op", "text", "x", "y", "size", "color"});
            auto text = r.string(r.required(*entry, "text"));
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            int size = r.integerAttr(*entry, "size", 1);
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { DrawText(text.c_str(), x, y, size, color); });
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

RegisterPrimOp validateOp({
    .name = "__raylibValidate",
    .args = {"commands"},
    .doc = "Validate a list of nixray drawing commands without opening a window; return its length.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        out.mkInt(static_cast<int64_t>(commands(state, pos, *args[0]).size()));
    },
    .experimentalFeature = std::nullopt,
});

RegisterPrimOp versionOp({
    .name = "__raylibVersion",
    .args = {},
    .arity = 0,
    .doc = "The version of raylib linked into nixray.",
    .impl = [](EvalState & state, PosIdx, Value **, Value & out) {
        out.mkString(RAYLIB_VERSION, state.mem);
    },
    .experimentalFeature = std::nullopt,
});

} // namespace
