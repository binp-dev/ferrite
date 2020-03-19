#pragma once

#include <array>
#include <vector>
#include <memory>
#include <atomic>
#include <mutex>
#include <thread>
#include <cstring>
#include <cassert>
#include <random>
#include <chrono>
#include <sstream>
#include <iomanip>

#include <utils/slice.hpp>
#include <utils/panic.hpp>
#include <channel/channel.hpp>
#include <encoder.hpp>
#include <../common/proto.h>


#define TIMEOUT 1000 // ms


class Device {
private:
    const size_t _max_points;
    const size_t _max_transfer;

    // Shared data
    std::vector<double> waveforms[3];
    std::atomic_bool swap_ready;
    std::mutex swap_mutex;
    std::atomic_bool done;

    // Worker data
    std::unique_ptr<Channel> channel;
    std::unique_ptr<const ArrayEncoder<double>> encoder;
    std::vector<uint8_t> send_buffer, recv_buffer;
    size_t waveform_pos = 0;

    // Device support data
    std::thread worker;

    // Worker methods
private:
    void fill(uint8_t **dst, size_t *dst_size) {
        std::pair<size_t, size_t> shift = encoder->encode(
            *dst, *dst_size,
            waveforms[0].data() + waveform_pos,
            waveforms[0].size() - waveform_pos
        );

        *dst += shift.first;
        *dst_size -= shift.first;
        waveform_pos += shift.second;
    }

    bool try_swap() {
        if (waveform_pos >= waveforms[0].size()) {
            if (swap_ready.load()) {
                std::lock_guard<std::mutex> guard(swap_mutex);
                std::swap(waveforms[0], waveforms[1]);
                swap_ready.store(false);
            }
            waveform_pos = 0;
            return true;
        } else {
            return false;
        }
    }

    size_t fill_until_full(uint8_t *data, size_t size) {
        size_t orig_size = size;

        try_swap();
        fill(&data, &size);

        while (true) {
            if (!try_swap()) {
                break;
            }
            fill(&data, &size);
        }

        return orig_size - size;
    }

    class Stat {
    public:
        double m2 = 0.0;
        uint64_t count = 0;
        double mean = 0.0;
        double var = 0.0;
        double min = -1.0;
        double max = -1.0;
        void update(double rate) {
            count += 1;
            double delta = rate - mean;
            mean += delta/count;
            double delta2 = rate - mean;
            m2 += delta*delta2;

            var = sqrt(m2/(count - 1));

            if (min < 0.0 || rate < min) {
                min = rate;
            }
            if (rate > max) {
                max = rate;
            }
        }
    };

    static std::string format_rate(double rate) {
        static const char PREFS[] = "KMGT"; 
        std::string pref = "";
        for (size_t i = 0; i < sizeof(PREFS) - 1; ++i) {
            if (rate >= 1e3) {
                rate /= 1e3;
                pref = PREFS[i];
            } else {
                break;
            }
        }
        std::stringstream ss;
        ss << std::fixed << std::setprecision(3) << rate << " " << pref;
        return ss.str();
    }

    template <int P, int N, int L>
    class Data {
    public:
        std::minstd_rand rng;
        uint8_t send[P][N][L];
        uint8_t recv[P][N][L];

        void prepare() {
            for (int k = 0; k < P; ++k) {
                for (int j = 0; j < N; ++j) {
                    for (int i = 0; i < L; ++i) {
                        send[k][j][i] = uint8_t(255*(double(rng())/std::minstd_rand::max()));
                    }
                }
            }
        }

        bool exchange(Channel *channel) {
            for (int k = 0; k < P; ++k) {
                for (int j = 0; j < N; ++j) {
                    channel->send(send[k][j], L, TIMEOUT);
                }
                for (int j = 0; j < N; ++j) {
                    int l = channel->receive(recv[k][j], L, TIMEOUT);
                    if (l != L) {
                        return false;
                    }
                }
            }
            return true;
        }

        bool check() const {
            bool equal = true;
            for (int k = 0; k < P; ++k) {
                for (int j = 0; j < N; ++j) {
                    for (int i = 0; i < L; ++i) {
                        equal = equal && (send[k][j][i] == recv[k][j][i]);
                    }
                }
            }
            return equal;
        }
    };

    void serve_loop() {
        try {
            std::cout << "[ioc] Channel serve thread started" << std::endl;
            
            std::minstd_rand rng;

            static const int NPASS = 64, NBUFS = 8, LEN = 256;
            Data<NPASS, NBUFS, LEN> data;

            uint64_t bits_sent = 0;
            double secs_elapsed = 0.0;

            const double print_period = 2.0; // sec
            Stat stat;

            while(!this->done.load()) {
                data.prepare();


                auto start = std::chrono::steady_clock::now();

                if (!data.exchange(&*channel)) {
                    throw Exception("Bad length of received data");
                }

                auto stop = std::chrono::steady_clock::now();

                if (!data.check()) {
                    throw Exception("Bad content of received data");
                }

                uint64_t bits = NPASS*NBUFS*2*LEN*8;
                double time = 1e-3*std::chrono::duration_cast<std::chrono::milliseconds>(stop - start).count();

                stat.update(bits/time);

                bits_sent += bits;
                secs_elapsed += time;

                if (secs_elapsed > print_period) {
                    std::cout << std::endl;
                    std::array<std::pair<std::string, double>, 4> par = {
                        std::make_pair("avg", stat.mean),
                        std::make_pair("var", stat.var),
                        std::make_pair("min", stat.min),
                        std::make_pair("max", stat.max),
                    };
                    for (auto p : par) {
                        std::cout << p.first << ": " << format_rate(p.second) << "bps" << std::endl;
                    }

                    double rate = bits_sent/secs_elapsed;
                    std::cout << "Currnet data rate: " << format_rate(rate) << "bits per second" << std::endl;
                    
                    bits_sent = 0;
                    secs_elapsed = 0.0;
                }
            }
        } catch(const Exception &e) {
            std::cerr << "Exception in thread `serve_loop`:" << std::endl;
            std::cerr << e.what() << std::endl;
            panic();
        } catch(...) {
            std::cerr << "Unknown exception in thread `serve_loop`" << std::endl;
            panic();
        }
    }

    // Device support methods
public:
    Device(const Device &dev) = delete;
    Device &operator=(const Device &dev) = delete;

    Device(
        std::unique_ptr<Channel> channel,
        std::unique_ptr<const ArrayEncoder<double>> encoder,
        size_t max_points,
        size_t max_transfer
    ) :
        _max_points(max_points),
        _max_transfer(max_transfer),

        swap_ready(false),

        channel(std::move(channel)),
        encoder(std::move(encoder)),

        send_buffer(max_transfer, 0),
        recv_buffer(max_transfer, 0)
    {
        for (int i = 0; i < 3; ++i) {
            waveforms[i].resize(max_points, 0.0);
        }

        done.store(false);
        worker = std::thread([this]() { this->serve_loop(); });
    }
    virtual ~Device() {
        done.store(true);
        worker.join();
    }

    void set_waveform(const_slice<double> waveform) {
        assert(waveform.size() <= max_points());
        if (!swap_ready.load()) {
            std::copy(waveform.begin(), waveform.end(), waveforms[1].begin());
            swap_ready.store(true);
        } else {
            std::copy(waveform.begin(), waveform.end(), waveforms[2].begin());
            {
                std::lock_guard<std::mutex> guard(swap_mutex);
                std::swap(waveforms[1], waveforms[2]);
                swap_ready.store(true);
            }
        }
    }

    size_t max_points() const {
        return _max_points;
    }
    size_t max_transfer() const {
        return _max_transfer;
    }
};
