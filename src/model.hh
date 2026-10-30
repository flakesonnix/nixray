#pragma once

#include "commands.hh"
#include <raylib.h>
#include <string>
#include <memory>
#include <vector>
#include <cstdint>

namespace nixray {

class Reader;
class Assets;

struct ModelSpec {
    std::string path, animations;
};

struct ModelAsset {
    Model value{};
    ModelAnimation * animations = nullptr;
    int animationCount = 0;
    int64_t vertexCount = 0, triangleCount = 0;
    BoundingBox bounds{};
    std::vector<std::vector<BoundingBox>> poseBounds;

    ModelAsset() = default;
    ~ModelAsset();
    ModelAsset(const ModelAsset &) = delete;
    ModelAsset & operator=(const ModelAsset &) = delete;
};

std::unique_ptr<ModelAsset> loadModelAsset(const ModelSpec & spec, const std::string & name, const Reader & reader);
Command modelCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                      const std::string & op, const Assets * assets, const Shader * shader);
void modelSnapshot(nix::EvalState & state, const Assets & assets, nix::Value & out);

} // namespace nixray
