#include "image.hh"
#include "reader.hh"
#include "log.hh"

#include <nix/expr/eval-gc.hh>
#include <nix/expr/eval-settings.hh>
#include <nix/util/signals.hh>
#include <nix/util/serialise.hh>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <ostream>
#include <utility>
#include <unistd.h>

namespace nixray {

namespace {

constexpr int maxSide = 16384;
constexpr int64_t maxPixels = 4194304, maxWork = 67108864, maxFileBytes = 67108864;

class ImageValue final : public nix::ExternalValueBase, public gc_cleanup {
public:
    std::shared_ptr<const ImageData> image;
    explicit ImageValue(std::shared_ptr<const ImageData> image) : image(std::move(image)) {}
    std::string showType() const override { return "nixray image"; }
    std::string typeOf() const override { return "nixray-image"; }
    std::ostream & print(std::ostream & stream) const override
    {
        return stream << "<nixray image " << image->value.width << "x" << image->value.height << ">";
    }
};

void size(const Reader & r, int width, int height)
{
    if (width < 1 || height < 1 || width > maxSide || height > maxSide || static_cast<int64_t>(width)*height > maxPixels)
        r.fail("images require dimensions in 1..16384 and at most 4194304 pixels");
}

void normalize(const Reader & r, Image & image)
{
    if (!IsImageValid(image)) r.fail("could not create or decode image");
    size(r, image.width, image.height);
    // Float/compressed formats need separate conversion and finite-data rules.
    if (image.format < PIXELFORMAT_UNCOMPRESSED_GRAYSCALE || image.format > PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
        r.fail("images require uncompressed byte or packed 16-bit colors");
    image.mipmaps = 1;
    ImageFormat(&image, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
    if (!IsImageValid(image) || image.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
        r.fail("could not convert image to RGBA8");
}

int dimension(const Reader & r, Value & v, const char * field)
{
    return r.integer(r.required(v, field), field, 1, maxSide);
}

void publish(EvalState & state, Value & out, std::shared_ptr<const ImageData> image)
{
    // Native pixel allocations are outside Boehm's heap accounting. Periodically
    // collect unreachable external wrappers too, rather than waiting for enough
    // tiny evaluator objects to accumulate while their large buffers stay alive.
    static thread_local size_t bytesSinceGC = 0;
    bytesSinceGC += static_cast<size_t>(image->value.width)*image->value.height*4;
    if (bytesSinceGC >= maxFileBytes) { bytesSinceGC = 0; state.fullGC(); }
    out.mkExternal(new ImageValue(std::move(image)));
}

void canvas(const Reader & r, Image & image, int width, int height, int x, int y, Color fill)
{
    // Native ImageResizeCanvas can memcpy a negative width for disjoint offsets,
    // and ignores offsets when the size is unchanged. Clip safely in int64.
    ImageData result;
    result.value = GenImageColor(width, height, fill);
    normalize(r, result.value);
    int64_t left = std::max<int64_t>(0, x), top = std::max<int64_t>(0, y);
    int64_t right = std::min<int64_t>(width, static_cast<int64_t>(x) + image.width);
    int64_t bottom = std::min<int64_t>(height, static_cast<int64_t>(y) + image.height);
    if (left < right && top < bottom) for (int64_t row = top; row < bottom; ++row) {
        auto * dst = static_cast<Color *>(result.value.data) + row*width + left;
        auto * src = static_cast<const Color *>(image.data) + (row - y)*image.width + (left - x);
        std::memcpy(dst, src, static_cast<size_t>(right - left)*sizeof(Color));
    }
    std::swap(image, result.value);
}

// Publish with link(2), not a truncating fopen or a replacing rename. Encoding
// and writing the private temporary finish before the destination becomes visible.
struct ExportFile {
    std::string temporary;
    int fd = -1;
    ~ExportFile()
    {
        if (fd >= 0) ::close(fd);
        if (!temporary.empty()) ::unlink(temporary.c_str());
    }
};

} // namespace

ImageData::~ImageData()
{
    if (value.data) UnloadImage(value);
}

std::shared_ptr<const ImageData> imageValue(EvalState & state, PosIdx pos, Value & value)
{
    state.forceValue(value, pos);
    auto * image = value.type() == nExternal ? dynamic_cast<ImageValue *>(value.external()) : nullptr;
    if (!image) Reader(state, pos).fail("expected a nixray image value");
    return image->image;
}

void loadImage(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    state.forceValue(*args[0], pos);
    if (args[0]->type() == nString) {
        auto text = state.forceString(*args[0], pos, context);
        if (text.empty() || text.front() != '/' || text.find('\0') != std::string_view::npos)
            r.fail("image paths must be Nix paths or absolute strings without NUL bytes");
    } else if (args[0]->type() != nPath) r.fail("image paths must be Nix paths or absolute strings");
    auto path = state.realisePath(pos, *args[0]);
    // Read through Nix's accessor, never a physical-path escape around pure or
    // restricted evaluation. Native decoding only sees these permitted bytes.
    if (path.lstat().type != nix::SourceAccessor::tRegular) r.fail("image input must be a regular file");
    std::string bytes;
    nix::LambdaSink sink([&](std::string_view chunk) {
        if (chunk.size() > maxFileBytes - bytes.size()) r.fail("encoded images must not exceed 64 MiB");
        bytes.append(chunk);
    });
    path.readFile(sink, [&](uint64_t count) {
        if (count > maxFileBytes) r.fail("encoded images must not exceed 64 MiB");
    });
    std::string name(path.baseName());
    auto * extension = GetFileExtension(name.c_str());
    if (!extension || !*extension) r.fail("image path must have a supported file extension");
    configureLogging();
    auto image = std::make_shared<ImageData>();
    image->value = LoadImageFromMemory(extension, reinterpret_cast<const unsigned char *>(bytes.data()), bytes.size());
    normalize(r, image->value);
    publish(state, out, std::move(image));
}

void genImage(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto & v = *args[0];
    std::string kind = "solid";
    if (auto * k = r.optional(v, "kind")) kind = r.string(*k);
    int width = dimension(r, v, "width"), height = dimension(r, v, "height");
    size(r, width, height);
    configureLogging();
    auto image = std::make_shared<ImageData>();
    if (kind == "solid") {
        r.fields(v, {"kind", "width", "height", "color"});
        image->value = GenImageColor(width, height, r.color(r.required(v, "color")));
    } else if (kind == "checked") {
        r.fields(v, {"kind", "width", "height", "checksX", "checksY", "color1", "color2"});
        int x = dimension(r, v, "checksX"), y = dimension(r, v, "checksY");
        auto a = r.color(r.required(v, "color1")), b = r.color(r.required(v, "color2"));
        image->value = GenImageChecked(width, height, x, y, a, b);
    } else if (kind == "gradientLinear") {
        r.fields(v, {"kind", "width", "height", "direction", "start", "end"});
        if (width < 2 || height < 2) r.fail("linear gradients require width and height at least 2");
        int direction = r.defaultInt(v, "direction", 0);
        if (direction > 360) r.fail("gradient direction must be in 0..360 degrees");
        auto a = r.color(r.required(v, "start")), b = r.color(r.required(v, "end"));
        image->value = GenImageGradientLinear(width, height, direction, a, b);
    } else if (kind == "gradientRadial" || kind == "gradientSquare") {
        r.fields(v, {"kind", "width", "height", "density", "inner", "outer"});
        float density = 0;
        if (auto * d = r.optional(v, "density")) density = r.number(*d, "density", 0, 1);
        if (density == 1) r.fail("gradient density must remain below 1 after float conversion");
        auto a = r.color(r.required(v, "inner")), b = r.color(r.required(v, "outer"));
        image->value = kind == "gradientRadial" ? GenImageGradientRadial(width, height, density, a, b)
                                                : GenImageGradientSquare(width, height, density, a, b);
    } else r.fail("unknown image generator '" + kind + "'");
    normalize(r, image->value);
    publish(state, out, std::move(image));
}

void imageTransform(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto source = imageValue(state, pos, *args[0]);
    state.forceList(*args[1], pos, context);
    if (args[1]->listSize() > 256) r.fail("image transforms must contain at most 256 operations");
    if (!args[1]->listSize()) { out.mkExternal(new ImageValue(std::move(source))); return; }
    configureLogging();
    auto result = std::make_shared<ImageData>();
    result->value = ImageCopy(source->value);
    normalize(r, result->value);
    auto & image = result->value;
    int64_t work = static_cast<int64_t>(image.width)*image.height;
    auto charge = [&](int width, int height) {
        size(r, width, height);
        // A conservative pixel-work budget, not a native CPU-time guarantee.
        work += 4*(static_cast<int64_t>(image.width)*image.height + static_cast<int64_t>(width)*height);
        if (work > maxWork) r.fail("image transform exceeds the 67108864 pixel-work budget");
    };
    for (auto * entry : args[1]->listView()) {
        nix::checkInterrupt();
        auto op = r.string(r.required(*entry, "op"));
        if (op == "crop" || op == "drawRectangle") {
            r.fields(*entry, op == "crop" ? std::initializer_list<std::string_view>{"op", "x", "y", "width", "height"}
                                         : std::initializer_list<std::string_view>{"op", "x", "y", "width", "height", "color"});
            int x = r.integerAttr(*entry, "x", 0), y = r.integerAttr(*entry, "y", 0);
            int w = r.integerAttr(*entry, "width", op == "crop" ? 1 : 0), h = r.integerAttr(*entry, "height", op == "crop" ? 1 : 0);
            if (static_cast<int64_t>(x) + w > image.width || static_cast<int64_t>(y) + h > image.height)
                r.fail("image rectangle exceeds image bounds");
            charge(op == "crop" ? w : image.width, op == "crop" ? h : image.height);
            if (op == "crop") ImageCrop(&image, {static_cast<float>(x), static_cast<float>(y), static_cast<float>(w), static_cast<float>(h)});
            else ImageDrawRectangle(&image, x, y, w, h, r.color(r.required(*entry, "color")));
        } else if (op == "resize" || op == "resizeNN" || op == "resizeCanvas") {
            r.fields(*entry, op == "resizeCanvas" ? std::initializer_list<std::string_view>{"op", "width", "height", "offsetX", "offsetY", "fill"}
                                                 : std::initializer_list<std::string_view>{"op", "width", "height"});
            int w = dimension(r, *entry, "width"), h = dimension(r, *entry, "height");
            charge(w, h);
            if (op == "resizeCanvas") {
                int x = r.integerAttr(*entry, "offsetX"), y = r.integerAttr(*entry, "offsetY");
                auto fill = r.color(r.required(*entry, "fill"));
                canvas(r, image, w, h, x, y, fill);
            } else if (op == "resizeNN") ImageResizeNN(&image, w, h);
            else ImageResize(&image, w, h);
        } else if (op == "rotate" || op == "rotateCW" || op == "rotateCCW") {
            r.fields(*entry, op == "rotate" ? std::initializer_list<std::string_view>{"op", "degrees"} : std::initializer_list<std::string_view>{"op"});
            int degrees = op == "rotate" ? r.integer(r.required(*entry, "degrees"), "degrees", -359, 359) : op == "rotateCW" ? 90 : -90;
            int turns = ((degrees % 360) + 360) % 360 / 90;
            int w = image.width, h = image.height;
            if (degrees % 90 == 0) {
                if (turns % 2) std::swap(w, h);
            } else {
                float rad = degrees*PI/180.0f;
                w = static_cast<int>(std::abs(image.width*std::cos(rad)) + std::abs(image.height*std::sin(rad)));
                h = static_cast<int>(std::abs(image.height*std::cos(rad)) + std::abs(image.width*std::sin(rad)));
            }
            charge(w, h);
            if (degrees % 90) ImageRotate(&image, degrees);
            else for (int i = 0; i < turns; ++i) ImageRotateCW(&image);
        } else if (op == "drawPixel") {
            r.fields(*entry, {"op", "x", "y", "color"});
            int x = r.integer(r.required(*entry, "x"), "x", 0, image.width - 1);
            int y = r.integer(r.required(*entry, "y"), "y", 0, image.height - 1);
            auto color = r.color(r.required(*entry, "color"));
            charge(image.width, image.height);
            ImageDrawPixel(&image, x, y, color);
        } else if (op == "colorTint" || op == "alphaClear") {
            r.fields(*entry, op == "alphaClear" ? std::initializer_list<std::string_view>{"op", "color", "threshold"}
                                               : std::initializer_list<std::string_view>{"op", "color"});
            auto color = r.color(r.required(*entry, "color"));
            charge(image.width, image.height);
            if (op == "colorTint") ImageColorTint(&image, color);
            else ImageAlphaClear(&image, color, r.number(r.required(*entry, "threshold"), "threshold", 0, 1));
        } else if (op == "alphaCrop") {
            r.fields(*entry, {"op", "threshold"});
            float threshold = r.number(r.required(*entry, "threshold"), "threshold", 0, 1);
            charge(image.width, image.height);
            ImageAlphaCrop(&image, threshold);
        } else if (op == "alphaMask") {
            r.fields(*entry, {"op", "image"});
            auto mask = imageValue(state, pos, r.required(*entry, "image"));
            if (mask->value.width != image.width || mask->value.height != image.height) r.fail("alpha mask must match image dimensions");
            charge(image.width, image.height);
            ImageAlphaMask(&image, mask->value);
        } else if (op == "colorReplace") {
            r.fields(*entry, {"op", "color", "replace"});
            auto color = r.color(r.required(*entry, "color")), replace = r.color(r.required(*entry, "replace"));
            charge(image.width, image.height);
            ImageColorReplace(&image, color, replace);
        } else if (op == "colorContrast" || op == "colorBrightness") {
            r.fields(*entry, {"op", "value"});
            charge(image.width, image.height);
            if (op == "colorContrast") ImageColorContrast(&image, r.number(r.required(*entry, "value"), "contrast", -100, 100));
            else ImageColorBrightness(&image, r.integer(r.required(*entry, "value"), "brightness", -255, 255));
        } else {
            r.fields(*entry, {"op"});
            charge(image.width, image.height);
            if (op == "flipHorizontal") ImageFlipHorizontal(&image);
            else if (op == "flipVertical") ImageFlipVertical(&image);
            else if (op == "colorInvert") ImageColorInvert(&image);
            else if (op == "alphaPremultiply") ImageAlphaPremultiply(&image);
            else if (op == "colorGrayscale") {
                // Keep alpha; native ImageColorGrayscale converts to a format
                // without alpha. All public image values remain RGBA8.
                auto * pixels = static_cast<Color *>(image.data);
                for (int i = 0; i < image.width*image.height; ++i) {
                    unsigned char gray = static_cast<unsigned char>(0.299f*pixels[i].r + 0.587f*pixels[i].g + 0.114f*pixels[i].b);
                    pixels[i].r = pixels[i].g = pixels[i].b = gray;
                }
            } else r.fail("unknown image operation '" + op + "'");
        }
        normalize(r, image);
    }
    publish(state, out, std::move(result));
}

void imageInfo(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    auto image = imageValue(state, pos, *args[0]);
    auto info = state.buildBindings(3);
    info.alloc("width").mkInt(image->value.width);
    info.alloc("height").mkInt(image->value.height);
    info.alloc("format").mkString("rgba8", state.mem);
    out.mkAttrs(info);
}

void imagePixel(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto image = imageValue(state, pos, *args[0]);
    r.fields(*args[1], {"x", "y"});
    int x = r.integer(r.required(*args[1], "x"), "x", 0, image->value.width - 1);
    int y = r.integer(r.required(*args[1], "y"), "y", 0, image->value.height - 1);
    auto color = static_cast<const Color *>(image->value.data)[y*image->value.width + x];
    auto pixel = state.buildList(4);
    int channels[]{color.r, color.g, color.b, color.a};
    for (size_t i = 0; i < 4; ++i) { pixel[i] = state.allocValue(); pixel[i]->mkInt(channels[i]); }
    out.mkList(pixel);
}

void exportImage(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    if (state.settings.pureEval || state.settings.restrictEval) r.fail("exportImage requires impure, unrestricted evaluation");
    r.fields(*args[0], {"image", "path"});
    auto image = imageValue(state, pos, r.required(*args[0], "image"));
    auto path = r.string(r.required(*args[0], "path"));
    if (path.empty() || path.front() != '/' || !IsFileExtension(path.c_str(), ".png"))
        r.fail("image export requires an absolute .png destination string");
    configureLogging();
    int count = 0;
    std::unique_ptr<unsigned char, decltype(&MemFree)> bytes(ExportImageToMemory(image->value, ".png", &count), MemFree);
    if (!bytes || count < 1) r.fail("could not encode PNG image");
    ExportFile file;
    std::string name = (std::filesystem::path(path).parent_path() / ".nixray-image-XXXXXX").string();
    file.fd = ::mkstemp(name.data());
    if (file.fd < 0) r.fail("could not create image export temporary: " + std::string(std::strerror(errno)));
    file.temporary = std::move(name);
    for (int offset = 0; offset < count;) {
        nix::checkInterrupt();
        ssize_t n = ::write(file.fd, bytes.get() + offset, count - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) r.fail("could not write image export");
        offset += n;
    }
    int fd = std::exchange(file.fd, -1);
    if (::close(fd) < 0) r.fail("could not close image export");
    if (::link(file.temporary.c_str(), path.c_str()) < 0)
        r.fail("could not publish image export (destination must not exist): " + std::string(std::strerror(errno)));
    out.mkString(path, state.mem);
}

} // namespace nixray
