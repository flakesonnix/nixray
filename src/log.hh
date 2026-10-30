#pragma once

#include <raylib.h>
#include <cstdio>

namespace nixray {

inline void configureLogging()
{
    // CPU image operations can run before any window exists. Raylib's default
    // stdout logger would corrupt evaluator JSON in that case too.
    SetTraceLogCallback([](int, const char * message, va_list args) {
        std::fputs("nixray: ", stderr);
        std::vfprintf(stderr, message, args);
        std::fputc('\n', stderr);
    });
    SetTraceLogLevel(LOG_WARNING);
}

} // namespace nixray
