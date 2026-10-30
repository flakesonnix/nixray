#pragma once

#include "commands.hh"
#include <raylib.h>
#include <array>
#include <map>
#include <memory>
#include <string>

namespace nixray {

class Reader;

struct UniformValue {
    int type = SHADER_UNIFORM_FLOAT;
    std::array<float, 4> floats{};
    int integer = 0;
};
using UniformValues = std::map<std::string, UniformValue>;

struct ShaderSpec {
    std::string fragment;
    UniformValues defaults;
};

struct ShaderAsset {
    Shader program{};
    UniformValues defaults;
    std::map<std::string, int> locations;

    ShaderAsset() = default;
    ~ShaderAsset();
    ShaderAsset(const ShaderAsset &) = delete;
    ShaderAsset & operator=(const ShaderAsset &) = delete;
};

struct ShaderState {
    const ShaderAsset * asset = nullptr;
    UniformValues uniforms;
    bool explicitScope = false;
};

UniformValues uniformSpecs(nix::EvalState & state, nix::PosIdx pos, nix::Value * value);
std::unique_ptr<ShaderAsset> loadShaderAsset(const ShaderSpec & spec, const std::string & name, const Reader & reader);
ShaderState shaderState(nix::EvalState & state, nix::PosIdx pos, nix::Value & value, const Assets * assets);

class ShaderScope {
    const ShaderState & parent;

public:
    ShaderScope(const ShaderState & shader, const ShaderState & parent);
    ~ShaderScope();
    ShaderScope(const ShaderScope &) = delete;
    ShaderScope & operator=(const ShaderScope &) = delete;
};

Command shaderCommand(ShaderState shader, ShaderState parent, std::vector<Command> batch);

} // namespace nixray
