#include "audio.hh"
#include "assets.hh"
#include "reader.hh"

#include <cmath>

namespace nixray {

namespace {

float nativePan(float pan)
{
#if RAYLIB_VERSION_MAJOR == 5 && RAYLIB_VERSION_MINOR < 6
    // raylib 5.5 mixes 1 as left and 0 as right; 5.6 uses -1..1.
    return (1.0f - pan) / 2.0f;
#else
    return pan;
#endif
}

} // namespace

AudioDevice::AudioDevice(bool enabled, const Reader & r)
{
    if (!enabled) return;
    if (IsAudioDeviceReady()) r.fail("an audio device is already active");
    InitAudioDevice();
    ready = IsAudioDeviceReady();
    if (!ready) r.fail("could not initialize the audio device");
}

AudioDevice::~AudioDevice()
{
    if (ready) CloseAudioDevice();
}

std::vector<Command> audioCommands(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    state.forceList(value, pos, context);
    std::vector<Command> result;
    result.reserve(value.listSize());
    for (auto * entry : value.listView()) {
        auto op = r.string(r.required(*entry, "op"));
        bool sound = op == "playSound" || op == "pauseSound" || op == "resumeSound" ||
                     op == "stopSound" || op == "setSoundVolume" || op == "setSoundPitch" || op == "setSoundPan";
        bool music = op == "playMusic" || op == "pauseMusic" || op == "resumeMusic" ||
                     op == "stopMusic" || op == "setMusicVolume" || op == "setMusicPitch" ||
                     op == "setMusicPan" || op == "seekMusic";
        if (!sound && !music) r.fail("unknown audio operation '" + op + "'");
        bool volume = op == "setSoundVolume" || op == "setMusicVolume";
        bool pitch = op == "setSoundPitch" || op == "setMusicPitch";
        bool pan = op == "setSoundPan" || op == "setMusicPan";
        bool seek = op == "seekMusic";
        const char * resource = sound ? "sound" : "music";
        if (volume) r.fields(*entry, {"op", resource, "volume"});
        else if (pitch) r.fields(*entry, {"op", resource, "pitch"});
        else if (pan) r.fields(*entry, {"op", resource, "pan"});
        else if (seek) r.fields(*entry, {"op", resource, "position"});
        else r.fields(*entry, {"op", resource});
        auto name = r.string(r.required(*entry, resource));
        if (name.empty()) r.fail(sound ? "sound name must not be empty" : "music name must not be empty");
        float amount = volume ? r.number(r.required(*entry, "volume"), "volume", 0, 1) :
                       pitch ? r.number(r.required(*entry, "pitch"), "pitch", 0.125f, 8) :
                       pan ? r.number(r.required(*entry, "pan"), "pan", -1, 1) :
                       seek ? r.number(r.required(*entry, "position"), "position", 0) : 0;
        Sound effect{};
        Music track{};
        if (assets && sound) {
            auto * found = assets->sound(name);
            if (!found) r.fail("unknown sound '" + name + "'");
            effect = *found;
        } else if (assets) {
            auto * found = assets->music(name);
            if (!found) r.fail("unknown music '" + name + "'");
            track = *found;
            if (seek) {
                if (!assets->musicCanSeek(name)) r.fail("seeking is not supported for this music format");
                if (amount > GetMusicTimeLength(track)) r.fail("music seek position must not exceed the track length");
                // Native seek truncates this float product to unsigned frames.
                // Rounding must not exceed the track or signed time-query range.
                float frames = amount * track.stream.sampleRate;
                if (!std::isfinite(frames) || static_cast<double>(frames) >= static_cast<double>(track.frameCount) + 1.0)
                    r.fail("music seek position must fit native frame coordinates");
            }
        }
        result.emplace_back([=] {
            if (op == "playSound") PlaySound(effect);
            else if (op == "pauseSound") PauseSound(effect);
            else if (op == "resumeSound") ResumeSound(effect);
            else if (op == "stopSound") StopSound(effect);
            else if (op == "setSoundVolume") SetSoundVolume(effect, amount);
            else if (op == "setSoundPitch") SetSoundPitch(effect, amount);
            else if (op == "setSoundPan") SetSoundPan(effect, nativePan(amount));
            else if (op == "playMusic") PlayMusicStream(track);
            else if (op == "pauseMusic") PauseMusicStream(track);
            else if (op == "resumeMusic") ResumeMusicStream(track);
            else if (op == "stopMusic") StopMusicStream(track);
            else if (op == "setMusicVolume") SetMusicVolume(track, amount);
            else if (op == "setMusicPitch") SetMusicPitch(track, amount);
            else if (op == "setMusicPan") SetMusicPan(track, nativePan(amount));
            else SeekMusicStream(track, amount);
        });
    }
    return result;
}

void audioSnapshot(EvalState & state, bool enabled, const Assets & assets, Value & out)
{
    auto result = state.buildBindings(3);
    result.alloc("enabled").mkBool(enabled);
    auto sounds = state.buildBindings(assets.soundNames().size());
    for (const auto & name : assets.soundNames()) {
        auto status = state.buildBindings(1);
        status.alloc("playing").mkBool(IsSoundPlaying(*assets.sound(name)));
        sounds.alloc(name).mkAttrs(status);
    }
    result.alloc("sounds").mkAttrs(sounds);
    auto music = state.buildBindings(assets.musicNames().size());
    for (const auto & name : assets.musicNames()) {
        auto track = *assets.music(name);
        auto status = state.buildBindings(4);
        status.alloc("playing").mkBool(IsMusicStreamPlaying(track));
        status.alloc("looping").mkBool(track.looping);
        status.alloc("timePlayed").mkFloat(GetMusicTimePlayed(track));
        status.alloc("timeLength").mkFloat(GetMusicTimeLength(track));
        music.alloc(name).mkAttrs(status);
    }
    result.alloc("music").mkAttrs(music);
    out.mkAttrs(result);
}

} // namespace nixray
