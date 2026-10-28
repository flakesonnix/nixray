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

struct AssetSpecs {
    std::map<std::string, std::string> textures;
    std::map<std::string, FontSpec> fonts;
};

AssetSpecs assetSpecs(nix::EvalState & state, nix::PosIdx pos, nix::Value * value);

// Own GPU resources, never evaluator Values. The window must outlive this object.
class Assets {
    struct TextureDeleter { void operator()(Texture2D * texture) const; };
    struct FontDeleter { void operator()(Font * font) const; };
    std::map<std::string, std::unique_ptr<Texture2D, TextureDeleter>> textures;
    std::map<std::string, std::unique_ptr<Font, FontDeleter>> fonts;

public:
    Assets(const AssetSpecs & specs, const Reader & reader);
    Assets(const Assets &) = delete;
    Assets & operator=(const Assets &) = delete;

    const Texture2D * texture(const std::string & name) const;
    const Font * font(const std::string & name) const;
};

} // namespace nixray
