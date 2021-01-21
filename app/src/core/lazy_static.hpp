#pragma once

#include <atomic>
#include <mutex>
#include <memory>

template <typename T>
class LazyStatic {
private:
    mutable std::atomic_bool initialized;
    mutable std::mutex mutex;
    mutable T value;

protected:
    virtual T init_value() const = 0;

public:
    LazyStatic() : initialized(false) {}
    ~LazyStatic() = default;

    LazyStatic(const LazyStatic &) = delete;
    LazyStatic &operator=(const LazyStatic &) = delete;
    LazyStatic(LazyStatic &&) = delete;
    LazyStatic &operator=(LazyStatic &&) = delete;

    void try_init() const {
        if (!initialized.load()) {
            std::lock_guard<std::mutex> guard(mutex);
            if (!initialized.load()) {
                value = std::move(init_value());
                initialized.store(true);
            }
        }
    }
    const T &operator*() const {
        try_init();
        return value;
    }
    const T *operator->() const {
        return &*this;
    }
};