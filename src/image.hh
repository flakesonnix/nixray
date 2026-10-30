#pragma once

#include <nix/expr/eval.hh>
#include <raylib.h>
#include <memory>

namespace nixray {

struct ImageData {
    Image value{};
    ~ImageData();
    ImageData() = default;
    ImageData(const ImageData &) = delete;
    ImageData & operator=(const ImageData &) = delete;
};

std::shared_ptr<const ImageData> imageValue(nix::EvalState & state, nix::PosIdx pos, nix::Value & value);
void loadImage(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void genImage(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void imageTransform(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void imageInfo(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void imagePixel(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void exportImage(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);

} // namespace nixray
