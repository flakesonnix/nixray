#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <rlgl.h>
#include <set>

namespace nixray {

std::vector<Command> textureActions(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    state.forceList(value, pos, context);
    if (value.listSize() > 256) r.fail("texture actions must contain at most 256 entries");
    std::vector<Command> result;
    std::vector<Texture2D> refresh;
    std::set<unsigned> dirty;
    int64_t pixels = 0;
    for (auto * entry : value.listView()) {
        auto op = r.string(r.required(*entry, "op"));
        bool full = op == "updateTexture";
        if (!full && op != "updateTextureRec") r.fail("unknown texture action '" + op + "'");
        r.fields(*entry, full ? std::initializer_list<std::string_view>{"op", "texture", "image"}
                             : std::initializer_list<std::string_view>{"op", "texture", "image", "x", "y"});
        auto name = r.string(r.required(*entry, "texture"));
        if (name.empty()) r.fail("texture name must not be empty");
        auto image = imageValue(state, pos, r.required(*entry, "image"));
        int x = full ? 0 : r.integerAttr(*entry, "x", 0), y = full ? 0 : r.integerAttr(*entry, "y", 0);
        pixels += static_cast<int64_t>(image->value.width)*image->value.height;
        if (pixels > 16777216) r.fail("texture actions must upload at most 16777216 pixels per frame");
        Texture2D texture{};
        if (assets) {
            auto * found = assets->texture(name);
            if (!found) {
                if (assets->renderTexture(name)) r.fail("texture updates cannot target a render texture; use paint");
                r.fail("unknown texture '" + name + "'");
            }
            texture = *found;
            if (full && (image->value.width != texture.width || image->value.height != texture.height))
                r.fail("full texture update must match texture dimensions");
            if (static_cast<int64_t>(x) + image->value.width > texture.width || static_cast<int64_t>(y) + image->value.height > texture.height)
                r.fail("texture update rectangle exceeds texture bounds");
            if (texture.format < PIXELFORMAT_UNCOMPRESSED_GRAYSCALE || texture.format > PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
                r.fail("texture updates require uncompressed byte or packed 16-bit texture colors");
            if (texture.format != image->value.format) {
                auto converted = std::make_shared<ImageData>();
                converted->value = ImageCopy(image->value);
                if (!IsImageValid(converted->value)) r.fail("could not copy texture update image");
                ImageFormat(&converted->value, texture.format);
                if (!IsImageValid(converted->value) || converted->value.format != texture.format)
                    r.fail("could not convert texture update image");
                image = std::move(converted);
            }
            if (texture.mipmaps > 1 && dirty.insert(texture.id).second) refresh.push_back(texture);
        }
        result.emplace_back([texture, image = std::move(image), x, y, full] {
            rlDrawRenderBatchActive();
            if (full) UpdateTexture(texture, image->value.data);
            else UpdateTextureRec(texture, {static_cast<float>(x), static_cast<float>(y),
                                  static_cast<float>(image->value.width), static_cast<float>(image->value.height)}, image->value.data);
        });
    }
    // No drawing occurs between uploads. Rebuild each dirty mip chain once,
    // after all patches, instead of once per tiny update to a large texture.
    for (auto texture : refresh) result.emplace_back([texture] { refreshTextureMipmaps(texture); });
    return result;
}

} // namespace nixray
