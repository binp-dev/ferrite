#pragma once

#include <array>

#include "format.hpp"

enum class LogLevel {
    Fatal = 0,
    Error,
    Warning,
    Info,
    Debug,
    Trace,
};

namespace log_impl {

constexpr std::array<const char *, size_t(LogLevel::Trace) + 1> LEVEL_NAMES = {
    "fatal",
    "error",
    "warning",
    "info",
    "debug",
    "trace",
};

template <LogLevel LEVEL, format_impl::Literal FMT_STR, typename... Ts>
void log(Ts &&...args) {
    constexpr auto LOG_FMT_STR = format_impl::Literal("[app:{}] ").append(FMT_STR);
    format_impl::print<LOG_FMT_STR>(std::cout, true, LEVEL_NAMES[size_t(LEVEL)], std::forward<Ts>(args)...);
}

} // namespace log_impl

#define core_log(level, fmt, ...) ::log_impl::log<level, fmt>(__VA_ARGS__)

/* clang-format off */
#define core_log_fatal(  fmt, ...) core_log(::LogLevel::Fatal,   fmt, ##__VA_ARGS__)
#define core_log_error(  fmt, ...) core_log(::LogLevel::Error,   fmt, ##__VA_ARGS__)
#define core_log_warning(fmt, ...) core_log(::LogLevel::Warning, fmt, ##__VA_ARGS__)
#define core_log_info(   fmt, ...) core_log(::LogLevel::Info,    fmt, ##__VA_ARGS__)
#define core_log_debug(  fmt, ...) core_log(::LogLevel::Debug,   fmt, ##__VA_ARGS__)
#define core_log_trace(  fmt, ...) core_log(::LogLevel::Trace,   fmt, ##__VA_ARGS__)
/* clang-format on */