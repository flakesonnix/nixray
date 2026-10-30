#pragma once

#include "shader.hh"
#include <array>
#include <vector>

namespace nixray {

struct DirectionalLight {
    Vector3 direction;
    std::array<float, 3> color;
    float intensity;
};

struct LightingSpec {
    std::array<float, 3> ambient{0.15f, 0.15f, 0.15f};
    std::vector<DirectionalLight> lights;
};

struct MaterialSpec {
    Color diffuse = WHITE;
    float specular = 0.5f, shininess = 32;
};

struct LightingShader {
    ShaderAsset resource;
    int ambient, count, directions, colors, camera, viewDirection, orthographic;
    int diffuse, specular, shininess, model, normals;
};

LightingSpec lightingSpec(nix::EvalState & state, nix::PosIdx pos, nix::Value & value);
MaterialSpec materialSpec(nix::EvalState & state, nix::PosIdx pos, nix::Value & value);
std::unique_ptr<LightingShader> loadLightingShader(const Reader & reader);
Command litCommand(const LightingShader & shader, LightingSpec lighting, MaterialSpec material,
                    Camera3D camera, bool model, bool normals, Command draw);

} // namespace nixray
