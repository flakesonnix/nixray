// Test-only tracing/failure injection; native decoding and playback still run.
#include <raylib.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <limits>

namespace {

template<typename Function>
Function original(const char * name)
{
    auto function = reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
    if (!function) {
        std::fprintf(stderr, "nixray audio fixture: cannot find %s\n", name);
        std::abort();
    }
    return function;
}

void trace(const char * event)
{
    if (auto * path = std::getenv("NIXRAY_TEST_AUDIO_TRACE"))
        if (auto * file = std::fopen(path, "a")) {
            std::fprintf(file, "%s\n", event);
            std::fclose(file);
        }
}

void trace(const char * event, float value)
{
    char message[128];
    std::snprintf(message, sizeof(message), "%s %.9g", event, value);
    trace(message);
}

} // namespace

extern "C" void InitAudioDevice()
{
    trace("device-init");
    if (std::getenv("NIXRAY_TEST_AUDIO_FAIL_INIT")) return;
    static const auto initialize = original<void (*)()>("InitAudioDevice");
    initialize();
}

extern "C" bool IsAudioDeviceReady()
{
    trace("device-ready");
    if (std::getenv("NIXRAY_TEST_AUDIO_ALREADY_READY")) return true;
    static const auto ready = original<bool (*)()>("IsAudioDeviceReady");
    return ready();
}

extern "C" void CloseAudioDevice()
{
    trace("device-close");
    static const auto close = original<void (*)()>("CloseAudioDevice");
    close();
}

extern "C" Sound LoadSound(const char * path)
{
    trace("load-sound");
    static const auto load = original<Sound (*)(const char *)>("LoadSound");
    return load(path);
}

extern "C" Music LoadMusicStream(const char * path)
{
    trace("load-music");
    static const auto load = original<Music (*)(const char *)>("LoadMusicStream");
    auto result = load(path);
    if (std::getenv("NIXRAY_TEST_AUDIO_LIMIT_MUSIC"))
        result.frameCount = static_cast<unsigned>(std::numeric_limits<int>::max());
    if (std::getenv("NIXRAY_TEST_AUDIO_OVERSIZE_MUSIC"))
        result.frameCount = static_cast<unsigned>(std::numeric_limits<int>::max()) + 1U;
    return result;
}

extern "C" void UnloadSound(Sound sound)
{
    trace("unload-sound");
    static const auto unload = original<void (*)(Sound)>("UnloadSound");
    unload(sound);
}

extern "C" void UnloadMusicStream(Music music)
{
    trace("unload-music");
    static const auto unload = original<void (*)(Music)>("UnloadMusicStream");
    unload(music);
}

extern "C" void PlaySound(Sound sound)
{
    trace("play-sound");
    static const auto play = original<void (*)(Sound)>("PlaySound");
    play(sound);
}

extern "C" void PauseSound(Sound sound)
{
    trace("pause-sound");
    static const auto pause = original<void (*)(Sound)>("PauseSound");
    pause(sound);
}

extern "C" void ResumeSound(Sound sound)
{
    trace("resume-sound");
    static const auto resume = original<void (*)(Sound)>("ResumeSound");
    resume(sound);
}

extern "C" void StopSound(Sound sound)
{
    trace("stop-sound");
    static const auto stop = original<void (*)(Sound)>("StopSound");
    stop(sound);
}

extern "C" void SetSoundVolume(Sound sound, float volume)
{
    trace("sound-volume", volume);
    static const auto set = original<void (*)(Sound, float)>("SetSoundVolume");
    set(sound, volume);
}

extern "C" void PlayMusicStream(Music music)
{
    trace("play-music", music.looping ? 1 : 0);
    static const auto play = original<void (*)(Music)>("PlayMusicStream");
    play(music);
}

extern "C" void PauseMusicStream(Music music)
{
    trace("pause-music");
    static const auto pause = original<void (*)(Music)>("PauseMusicStream");
    pause(music);
}

extern "C" void ResumeMusicStream(Music music)
{
    trace("resume-music");
    static const auto resume = original<void (*)(Music)>("ResumeMusicStream");
    resume(music);
}

extern "C" void StopMusicStream(Music music)
{
    trace("stop-music");
    static const auto stop = original<void (*)(Music)>("StopMusicStream");
    stop(music);
}

extern "C" void SetMusicVolume(Music music, float volume)
{
    trace("music-volume", volume);
    static const auto set = original<void (*)(Music, float)>("SetMusicVolume");
    set(music, volume);
}

extern "C" void SeekMusicStream(Music music, float position)
{
    trace("seek-music", position);
    static const auto seek = original<void (*)(Music, float)>("SeekMusicStream");
    seek(music, position);
}

extern "C" void UpdateMusicStream(Music music)
{
    trace("update-music", music.looping ? 1 : 0);
    static const auto update = original<void (*)(Music)>("UpdateMusicStream");
    update(music);
}

extern "C" void EndDrawing()
{
    static const auto finish = original<void (*)()>("EndDrawing");
    finish();
    trace("frame");
}

extern "C" void CloseWindow()
{
    trace("window-close");
    static const auto close = original<void (*)()>("CloseWindow");
    close();
}
