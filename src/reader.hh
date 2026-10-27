#pragma once

#include <nix/expr/eval.hh>
#include <raylib.h>

#include <cmath>
#include <initializer_list>
#include <limits>
#include <string>
#include <string_view>

namespace nixray {

using namespace nix;
inline constexpr auto context = "while evaluating a nixray argument";

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

} // namespace nixray
