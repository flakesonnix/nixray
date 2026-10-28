#pragma once

#include <nix/expr/eval.hh>
#include <raylib.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace nixray {

class Reader;

struct FontSpec {
    std::string path;
    int size = 32;
    std::vector<int> codepoints;
    bool customized = false;
};

struct TextureSize { int width, height; };

struct AssetSpecs {
    std::map<std::string, std::string> textures;
    std::map<std::string, FontSpec> fonts;
    std::map<std::string, TextureSize> renderTextures;
};

AssetSpecs assetSpecs(nix::EvalState & state, nix::PosIdx pos, nix::Value * value);

// Own GPU resources, never evaluator Values. The window must outlive this object.
class Assets {
    struct TextureDeleter { void operator()(Texture2D * texture) const; };
    struct FontDeleter { void operator()(Font * font) const; };
    struct RenderTextureDeleter { void operator()(RenderTexture2D * target) const; };
    std::map<std::string, std::unique_ptr<Texture2D, TextureDeleter>> textures;
    std::map<std::string, std::unique_ptr<Font, FontDeleter>> fonts;
    std::map<std::string, std::unique_ptr<RenderTexture2D, RenderTextureDeleter>> renderTextures;

public:
    Assets(const AssetSpecs & specs, const Reader & reader);
    Assets(const Assets &) = delete;
    Assets & operator=(const Assets &) = delete;

    const Texture2D * texture(const std::string & name) const;
    const Font * font(const std::string & name) const;
    const RenderTexture2D * renderTexture(const std::string & name) const;
};

} // namespace nixray
