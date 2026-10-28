#include "shader.hh"
#include "assets.hh"
#include "reader.hh"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <rlgl.h>
#include <algorithm>
#include <string_view>
#include <utility>

namespace nixray {

namespace {

void uniformName(const Reader & r, const std::string & name)
{
    auto letter = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; };
    if (name.empty() || !letter(name.front()) ||
        !std::all_of(name.begin(), name.end(), [&](char c) { return letter(c) || (c >= '0' && c <= '9'); }))
        r.fail("uniform names must be GLSL identifiers");
    if (name.starts_with("gl_")) r.fail("uniform names must not use the reserved gl_ prefix");
    for (std::string_view managed : {"mvp", "matView", "matProjection", "matModel", "matNormal", "boneMatrices",
                                     "colDiffuse", "texture0", "texture1", "texture2"})
        if (name == managed) r.fail("uniform '" + name + "' is managed by raylib");
}

int uniformType(const Reader & r, Value & value)
{
    auto type = r.string(value);
    if (type == "float") return SHADER_UNIFORM_FLOAT;
    if (type == "int") return SHADER_UNIFORM_INT;
    if (type == "vec2") return SHADER_UNIFORM_VEC2;
    if (type == "vec3") return SHADER_UNIFORM_VEC3;
    if (type == "vec4") return SHADER_UNIFORM_VEC4;
    r.fail("unknown uniform type '" + type + "'; expected float, int, vec2, vec3 or vec4");
}

UniformValue uniformValue(EvalState & state, PosIdx pos, const Reader & r, Value & value, int type)
{
    UniformValue result;
    result.type = type;
    if (type == SHADER_UNIFORM_INT) result.integer = r.integer(value, "uniform int");
    else if (type == SHADER_UNIFORM_FLOAT) result.floats[0] = r.number(value, "uniform float");
    else {
        state.forceList(value, pos, context);
        unsigned size = type == SHADER_UNIFORM_VEC2 ? 2 : type == SHADER_UNIFORM_VEC3 ? 3 : 4;
        if (value.listSize() != size) r.fail("uniform vector must contain exactly " + std::to_string(size) + " numbers");
        for (unsigned i = 0; i < size; ++i)
            result.floats[i] = r.number(*value.listView()[i], "uniform vector component");
    }
    return result;
}

// Without assets, validation can check value shape/range but not the schema.
UniformValue untypedUniformValue(EvalState & state, PosIdx pos, const Reader & r, Value & value)
{
    state.forceValue(value, pos);
    int type = SHADER_UNIFORM_FLOAT;
    if (value.type() == nList) {
        if (value.listSize() < 2 || value.listSize() > 4)
            r.fail("uniform vectors must contain between 2 and 4 numbers");
        type = value.listSize() == 2 ? SHADER_UNIFORM_VEC2 :
               value.listSize() == 3 ? SHADER_UNIFORM_VEC3 : SHADER_UNIFORM_VEC4;
    }
    return uniformValue(state, pos, r, value, type);
}

void reflectUniforms(ShaderAsset & asset, const Reader & r)
{
    // Use the current GLFW context's entry points, not symbols from a different
    // GL loader/driver. These are core GL 2.0 functions on the desktop backend.
    using GetProgram = void (*)(unsigned, unsigned, int *);
    using GetUniform = void (*)(unsigned, unsigned, int, int *, int *, unsigned *, char *);
    auto getProgram = reinterpret_cast<GetProgram>(glfwGetProcAddress("glGetProgramiv"));
    auto getUniform = reinterpret_cast<GetUniform>(glfwGetProcAddress("glGetActiveUniform"));
    if (!getProgram || !getUniform) r.fail("shader uniform reflection is unavailable in this OpenGL context");
    constexpr unsigned activeUniforms = 0x8b86, uniformNameLength = 0x8b87;
    int count = 0, maxLength = 0;
    getProgram(asset.program.id, activeUniforms, &count);
    getProgram(asset.program.id, uniformNameLength, &maxLength);
    std::vector<char> buffer(std::max(maxLength, 1));
    struct UniformInfo { unsigned type; int size; };
    std::map<std::string, UniformInfo> active;
    for (int i = 0; i < count; ++i) {
        int length = 0, size = 0;
        unsigned type = 0;
        getUniform(asset.program.id, i, static_cast<int>(buffer.size()), &length, &size, &type, buffer.data());
        active.emplace(std::string(buffer.data(), length), UniformInfo{type, size});
    }
    constexpr unsigned glFloat = 0x1406, glInt = 0x1404;
    constexpr unsigned glVec2 = 0x8b50, glVec3 = 0x8b51, glVec4 = 0x8b52;
    for (const auto & [name, value] : asset.defaults) {
        auto found = active.find(name);
        if (found == active.end()) r.fail("shader uniform '" + name + "' is missing, optimized out or an array");
        unsigned expected = value.type == SHADER_UNIFORM_FLOAT ? glFloat : value.type == SHADER_UNIFORM_INT ? glInt :
                            value.type == SHADER_UNIFORM_VEC2 ? glVec2 : value.type == SHADER_UNIFORM_VEC3 ? glVec3 : glVec4;
        if (found->second.size != 1 || found->second.type != expected)
            r.fail("shader uniform '" + name + "' has an incompatible GLSL type or is an array");
        int location = GetShaderLocation(asset.program, name.c_str());
        if (location < 0) r.fail("could not resolve shader uniform '" + name + "'");
        asset.locations.emplace(name, location);
    }
}

void applyShader(const ShaderState & shader)
{
    // Uniforms are program-global. Even changing values on the same program
    // must flush queued geometry before overwriting them.
    rlDrawRenderBatchActive();
    if (!shader.asset) {
        EndShaderMode();
        return;
    }
    BeginShaderMode(shader.asset->program);
    for (const auto & [name, value] : shader.uniforms) {
        const void * data = value.type == SHADER_UNIFORM_INT
            ? static_cast<const void *>(&value.integer) : static_cast<const void *>(value.floats.data());
        SetShaderValue(shader.asset->program, shader.asset->locations.at(name), data, value.type);
    }
}

} // namespace

UniformValues uniformSpecs(EvalState & state, PosIdx pos, Value * value)
{
    if (!value) return {};
    Reader r(state, pos);
    state.forceAttrs(*value, pos, context);
    UniformValues result;
    for (const auto & attr : *value->attrs()) {
        std::string name(state.symbols[attr.name]);
        uniformName(r, name);
        r.fields(*attr.value, {"type", "value"});
        int type = uniformType(r, r.required(*attr.value, "type"));
        result.emplace(std::move(name), uniformValue(state, pos, r, r.required(*attr.value, "value"), type));
    }
    return result;
}

ShaderAsset::~ShaderAsset()
{
    // A failed shader load may return the shared default program but newly
    // allocated locations. Never unload the shared program or leak those locs.
    if (program.id == rlGetShaderIdDefault()) {
        if (program.locs && program.locs != rlGetShaderLocsDefault()) MemFree(program.locs);
    } else if (program.id || program.locs) UnloadShader(program);
}

std::unique_ptr<ShaderAsset> loadShaderAsset(const ShaderSpec & spec, const std::string & name, const Reader & r)
{
    auto result = std::make_unique<ShaderAsset>();
    if (!FileExists(spec.fragment.c_str())) r.fail("could not load shader '" + name + "' from '" + spec.fragment + "'");
    result->program = LoadShader(nullptr, spec.fragment.c_str());
    if (!IsShaderValid(result->program) || result->program.id == rlGetShaderIdDefault())
        r.fail("could not load shader '" + name + "' from '" + spec.fragment + "'");
    result->defaults = spec.defaults;
    reflectUniforms(*result, r);
    return result;
}

ShaderState shaderState(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    r.fields(value, {"op", "shader", "uniforms", "commands"});
    auto name = r.string(r.required(value, "shader"));
    if (name.empty()) r.fail("shader name must not be empty");
    ShaderState result;
    if (assets) {
        result.asset = assets->shader(name);
        if (!result.asset) r.fail("unknown shader '" + name + "'");
        result.uniforms = result.asset->defaults;
    }
    if (auto * uniforms = r.optional(value, "uniforms")) {
        state.forceAttrs(*uniforms, pos, context);
        for (const auto & attr : *uniforms->attrs()) {
            std::string uniform(state.symbols[attr.name]);
            uniformName(r, uniform);
            if (assets) {
                auto found = result.uniforms.find(uniform);
                if (found == result.uniforms.end()) r.fail("unknown uniform '" + uniform + "' for shader '" + name + "'");
                found->second = uniformValue(state, pos, r, *attr.value, found->second.type);
            } else result.uniforms.emplace(std::move(uniform), untypedUniformValue(state, pos, r, *attr.value));
        }
    }
    return result;
}

ShaderScope::ShaderScope(const ShaderState & shader, const ShaderState & parent) : parent(parent)
{
    applyShader(shader);
}

ShaderScope::~ShaderScope()
{
    applyShader(parent);
}

Command shaderCommand(ShaderState shader, ShaderState parent, std::vector<Command> batch)
{
    return [shader = std::move(shader), parent = std::move(parent), batch = std::move(batch)] {
        ShaderScope scope(shader, parent);
        for (const auto & command : batch) command();
    };
}

} // namespace nixray
