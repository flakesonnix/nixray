#pragma once

#include <nix/expr/eval.hh>

namespace nixray {

void checkCollisionRecs(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void checkCollisionCircles(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void checkCollisionCircleRec(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void checkCollisionPointRec(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void checkCollisionPointCircle(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void checkCollisionLines(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void getCollisionRec(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);

} // namespace nixray
