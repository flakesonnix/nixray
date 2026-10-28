#pragma once

#include "commands.hh"

namespace nixray {

class Reader;

class AudioDevice {
    bool ready = false;

public:
    AudioDevice(bool enabled, const Reader & reader);
    ~AudioDevice();
    AudioDevice(const AudioDevice &) = delete;
    AudioDevice & operator=(const AudioDevice &) = delete;
};

// A null registry validates syntax only; those actions must never execute.
std::vector<Command> audioCommands(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                                   const Assets * assets = nullptr);
void audioSnapshot(nix::EvalState & state, bool enabled, const Assets & assets, nix::Value & out);

} // namespace nixray
