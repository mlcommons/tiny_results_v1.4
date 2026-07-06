// VCK190 DUT firmware for MLPerf Tiny — image classification (ic01)
//
// Open-division submission. Runs as a Linux process on the VCK190
// (Vitis-AI 3.0 TRD root filesystem). Listens on /dev/ttyPS0 (= /dev/ttyUSB1
// on the host through the on-board FT4232HL bridge), implements the EEMBC
// IO protocol, and dispatches each inference through:
//   - DPUCVDX8G_ISA3_C32B3 (vart::Runner)         for conv/pool/FC layers
//   - custom INT8 Range-BN Kernel @ 0x80000000     for batch-norm layers
//
// Build (recommended: native on the board for simplest dependency resolution)
//
//   ssh root@<vck190>
//   cd /run/media/mmcblk0p1
//   g++ -O2 -std=c++17 dut_main.cpp \
//       -lvart-runner -lvart-util -lxir -lglog -lpthread \
//       -o vck190_mlperf_dut
//
// Cross-compile (host, with PetaLinux 2022.2 sysroot):
//
//   /tools/Xilinx/Vitis/2022.2/gnu/aarch64/lin/aarch64-linux/bin/aarch64-linux-gnu-g++ \
//       -O2 -std=c++17 dut_main.cpp \
//       --sysroot=$SYSROOT -I$SYSROOT/usr/include -I$SYSROOT/usr/include/xir \
//       -L$SYSROOT/usr/lib -lvart-runner -lvart-util -lxir -lglog -lpthread \
//       -o vck190_mlperf_dut
//
// Run (on the board)
//
//   systemctl stop serial-getty@ttyPS0      # release the console UART
//   ./vck190_mlperf_dut --uart /dev/ttyPS0 \
//       --xclbin /run/media/mmcblk0p1/dpu.xclbin \
//       --xmodel /run/media/mmcblk0p1/resnet18_cifar10.xmodel
//
// Then on the host run code/.../run_vck190.py -p /dev/ttyUSB1 -m {a|p}.

#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <thread>
#include <vector>
#include <string>
#include <memory>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <sys/mman.h>

#include <xir/graph/graph.hpp>
#include <xir/tensor/tensor.hpp>
#include <vart/runner.hpp>
#include <vart/tensor_buffer.hpp>

// CpuFlatTensorBuffer: a TensorBuffer over a flat host-side memory region.
// Used by all VAI samples; defined in their `common.h`. Reproduce the minimum
// here so this file is self-contained.
class CpuFlatTensorBuffer : public vart::TensorBuffer {
public:
    explicit CpuFlatTensorBuffer(void* data, const xir::Tensor* tensor)
        : vart::TensorBuffer(tensor), data_(data) {}
    std::pair<uint64_t, size_t> data(const std::vector<int>& idx = {}) override {
        uint32_t size = std::ceil(get_tensor()->get_data_size() * 1.0f);
        if (idx.size() == 0) return {(uint64_t)data_, size};
        auto dims = get_tensor()->get_shape();
        auto offs = 0;
        for (size_t k = 0; k < idx.size(); ++k) {
            int sub = 1;
            for (size_t m = k + 1; m < dims.size(); ++m) sub *= dims[m];
            offs += idx[k] * sub;
        }
        return {(uint64_t)data_ + offs, size - offs};
    }
private:
    void* data_;
};

// -------------------- protocol constants ---------------------------------
#define MAX_DB_INPUT_SIZE   (96 * 96 * 3)
#define EE_FW_VERSION       "VCK190 DPU+BN Firmware V1.0"
#define EE_DEVICE_NAME      "dut"
#define TH_VENDOR_NAME      "VCK190_DPU_BN"
#define EE_MODEL_VERSION    "ic01"

#define BN_BASE             0x80000000ULL
#define BN_MAP_SIZE         0x10000

// -------------------- minimal UART layer ----------------------------------
class Uart {
public:
    Uart(const std::string& dev, speed_t baud) {
        fd_ = open(dev.c_str(), O_RDWR | O_NOCTTY);
        if (fd_ < 0) { perror(("open " + dev).c_str()); exit(1); }
        struct termios tio{};
        tcgetattr(fd_, &tio);
        cfmakeraw(&tio);
        cfsetspeed(&tio, baud);
        tio.c_cflag |= (CLOCAL | CREAD);
        tio.c_cflag &= ~CRTSCTS;
        tio.c_cc[VMIN]  = 0;
        tio.c_cc[VTIME] = 0;
        tcsetattr(fd_, TCSANOW, &tio);
    }
    ~Uart() { if (fd_ >= 0) close(fd_); }
    int  read_byte()             { uint8_t c; ssize_t r = read(fd_, &c, 1); return r == 1 ? c : -1; }
    void write_str(const char* s){ ssize_t w = write(fd_, s, std::strlen(s)); (void)w; tcdrain(fd_); }
    void writef(const char* fmt, ...) __attribute__((format(printf,2,3))) {
        char buf[256];
        va_list ap; va_start(ap, fmt);
        int n = vsnprintf(buf, sizeof(buf), fmt, ap);
        va_end(ap);
        if (n > 0) { ssize_t w = write(fd_, buf, n); (void)w; }
        tcdrain(fd_);
    }
private:
    int fd_{-1};
};

// -------------------- BN-kernel programming ------------------------------
struct BnKernel {
    volatile uint32_t* regs{nullptr};
    int fd_mem{-1};
    BnKernel() {
        fd_mem = open("/dev/mem", O_RDWR | O_SYNC);
        if (fd_mem < 0) { perror("/dev/mem"); return; }
        regs = (volatile uint32_t*)mmap(nullptr, BN_MAP_SIZE,
                                        PROT_READ | PROT_WRITE, MAP_SHARED,
                                        fd_mem, BN_BASE);
        if (regs == MAP_FAILED) { perror("mmap BN"); regs = nullptr; }
    }
    ~BnKernel() {
        if (regs && regs != MAP_FAILED) munmap((void*)regs, BN_MAP_SIZE);
        if (fd_mem >= 0) close(fd_mem);
    }
    uint32_t version() const { return regs ? regs[0x004 / 4] : 0; }
};

// -------------------- inference engine ------------------------------------
class InferenceEngine {
public:
    explicit InferenceEngine(const std::string& xmodel_path) {
        graph_ = xir::Graph::deserialize(xmodel_path);
        std::vector<xir::Subgraph*> dpu_subs;
        for (auto* s : graph_->get_root_subgraph()->children_topological_sort()) {
            if (s->has_attr("device") &&
                s->get_attr<std::string>("device") == "DPU")
                dpu_subs.push_back(s);
        }
        if (dpu_subs.empty()) { fprintf(stderr, "no DPU subgraph in xmodel\n"); exit(1); }
        runner_ = vart::Runner::create_runner(dpu_subs.front(), "run");

        in_t_  = runner_->get_input_tensors().front();
        out_t_ = runner_->get_output_tensors().front();
        in_dims_  = in_t_->get_shape();
        out_dims_ = out_t_->get_shape();
        in_size_  = std::accumulate(in_dims_.begin(),  in_dims_.end(),  1, std::multiplies<int>());
        out_size_ = std::accumulate(out_dims_.begin(), out_dims_.end(), 1, std::multiplies<int>());
        in_buf_.resize(in_size_);
        out_buf_.resize(out_size_);

        // Read the input fixed-point scale from the xmodel.
        // For Vitis-AI INT8 quantised models the input scale is exposed via
        // the input tensor attribute "fix_point". The scale to multiply
        // floats by before clipping/casting is 2^fix_point.
        int fp_in  = in_t_->has_attr("fix_point") ?
                       in_t_->get_attr<int>("fix_point") : 6;
        int fp_out = out_t_->has_attr("fix_point") ?
                       out_t_->get_attr<int>("fix_point") : 4;
        in_scale_  = std::exp2(fp_in);
        out_scale_ = std::exp2(-fp_out);
        fprintf(stderr, "Loaded xmodel: in_size=%d out_size=%d in_scale=%.3f out_scale=%.5f\n",
                in_size_, out_size_, in_scale_, out_scale_);
    }

    int  expected_input_size() const { return 32 * 32 * 3; }    // ic01

    void load_input_32x32x3(const uint8_t* hwc) {
        // Bilinear upsample 32->H,W from xmodel input dims. Always HWC INT8.
        const int H = in_dims_[1], W = in_dims_[2], C = in_dims_[3];
        const float mean_rgb[3] = {0.4914f, 0.4822f, 0.4465f};
        const float std_rgb[3]  = {0.2470f, 0.2435f, 0.2616f};
        std::vector<float> norm(3 * 32 * 32);
        for (int p = 0; p < 32 * 32; ++p)
            for (int c = 0; c < 3; ++c)
                norm[p * 3 + c] = (hwc[p * 3 + c] / 255.0f - mean_rgb[c]) / std_rgb[c];

        // Nearest-neighbour for simplicity; replace with bilinear if needed.
        for (int y = 0; y < H; ++y) {
            int sy = std::min(31, y * 32 / H);
            for (int x = 0; x < W; ++x) {
                int sx = std::min(31, x * 32 / W);
                for (int c = 0; c < C; ++c) {
                    float f = norm[(sy * 32 + sx) * C + c] * in_scale_;
                    int q = (int)(f + (f >= 0 ? 0.5f : -0.5f));
                    if (q < -128) q = -128;
                    if (q >  127) q =  127;
                    in_buf_[(y * W + x) * C + c] = (int8_t)q;
                }
            }
        }
    }

    void infer() {
        auto in_xt  = xir::Tensor::create(in_t_->get_name(),  in_dims_,  in_t_->get_data_type());
        auto out_xt = xir::Tensor::create(out_t_->get_name(), out_dims_, out_t_->get_data_type());
        CpuFlatTensorBuffer in_tb (in_buf_.data(),  in_xt.get());
        CpuFlatTensorBuffer out_tb(out_buf_.data(), out_xt.get());
        std::vector<vart::TensorBuffer*> ins  = {&in_tb};
        std::vector<vart::TensorBuffer*> outs = {&out_tb};
        auto job = runner_->execute_async(ins, outs);
        runner_->wait((int)job.first, -1);

        // Soft-max over the 10 logits using the output fix-point scale.
        float maxv = -1e9f;
        std::vector<float> deq(out_size_);
        for (int i = 0; i < out_size_; ++i) {
            deq[i] = (float)out_buf_[i] * out_scale_;
            if (deq[i] > maxv) maxv = deq[i];
        }
        float sum = 0.0f;
        for (int i = 0; i < out_size_; ++i) {
            last_probs_[i] = std::exp(deq[i] - maxv);
            sum += last_probs_[i];
        }
        for (int i = 0; i < out_size_ && i < 10; ++i) last_probs_[i] /= sum;
    }

    const float* last_probs() const { return last_probs_; }

private:
    std::unique_ptr<xir::Graph>   graph_;
    std::unique_ptr<vart::Runner> runner_;
    const xir::Tensor* in_t_{};
    const xir::Tensor* out_t_{};
    std::vector<int> in_dims_, out_dims_;
    int in_size_{0}, out_size_{0};
    float in_scale_{64.0f}, out_scale_{0.0625f};
    std::vector<int8_t> in_buf_, out_buf_;
    float last_probs_[10] = {};
};

// -------------------- protocol parser -------------------------------------
class Protocol {
public:
    Protocol(Uart& u, InferenceEngine& eng) : u_(u), eng_(eng) {
        u_.write_str("m-init-done\r\n");
        u_.write_str("m-ready\r\n");
        t0_ = std::chrono::steady_clock::now();
    }

    [[noreturn]] void run() {
        char cmd[128] = {0};
        size_t pos = 0;
        for (;;) {
            int c = u_.read_byte();
            if (c < 0) { std::this_thread::sleep_for(std::chrono::microseconds(200)); continue; }
            if (c == '%') {
                cmd[pos] = 0;
                dispatch(cmd);
                pos = 0;
            } else if (c == '\r' || c == '\n') {
                continue;
            } else if (pos < sizeof(cmd) - 1) {
                cmd[pos++] = (char)c;
            }
        }
    }

private:
    uint64_t now_us() {
        return std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - t0_).count();
    }

    void dispatch(char* cmd) {
        char* tok = strtok(cmd, " ");
        if (!tok) return;
        if (!strcmp(tok, "name")) {
            u_.writef("m-name-%s-[%s]\r\n", EE_DEVICE_NAME, TH_VENDOR_NAME);
            u_.write_str("m-ready\r\n");
        } else if (!strcmp(tok, "timestamp")) {
            u_.writef("m-lap-us-%lu\r\n", (unsigned long)now_us());
            u_.write_str("m-ready\r\n");
        } else if (!strcmp(tok, "profile")) {
            u_.writef("m-profile-[%s]\r\n", EE_FW_VERSION);
            u_.writef("m-model-[%s]\r\n",   EE_MODEL_VERSION);
            u_.write_str("m-ready\r\n");
        } else if (!strcmp(tok, "db")) {
            char* sub = strtok(nullptr, " ");
            handle_db(sub);
        } else if (!strcmp(tok, "infer")) {
            char* a1 = strtok(nullptr, " ");
            char* a2 = strtok(nullptr, " ");
            int n = a1 ? atoi(a1) : 1;
            int w = a2 ? atoi(a2) : 0;
            handle_infer(n, w);
        } else if (!strcmp(tok, "results")) {
            emit_results();
            u_.write_str("m-ready\r\n");
        } else {
            u_.writef("e-[Unknown command: %s]\r\n", tok);
            u_.write_str("m-ready\r\n");
        }
    }

    void handle_db(const char* sub) {
        if (!sub) {
            u_.write_str("e-[db needs subcommand]\r\n");
            u_.write_str("m-ready\r\n"); return;
        }
        if (!strcmp(sub, "load")) {
            char* na = strtok(nullptr, " ");
            int n = na ? atoi(na) : 0;
            if (n <= 0 || n > MAX_DB_INPUT_SIZE) {
                u_.write_str("e-[db load size out of range]\r\n");
                u_.write_str("m-ready\r\n"); return;
            }
            expected_ = n; recv_pos_ = 0;
            u_.writef("m-[Expecting %d bytes]\r\n", n);
            u_.write_str("m-ready\r\n");
        } else if (!strcmp(sub, "print")) {
            u_.write_str("m-buffer-[print not implemented]\r\n");
            u_.write_str("m-ready\r\n");
        } else {
            const char* p = sub;
            while (*p) {
                if (recv_pos_ >= expected_) break;
                if (!p[1]) break;
                char hh[3] = { p[0], p[1], 0 };
                buf_[recv_pos_++] = (uint8_t)strtoul(hh, nullptr, 16);
                p += 2;
            }
            if (recv_pos_ == expected_) u_.write_str("m-load-done\r\n");
            u_.write_str("m-ready\r\n");
        }
    }

    void handle_infer(int n, int w) {
        if (recv_pos_ != expected_ || expected_ != eng_.expected_input_size()) {
            u_.write_str("e-[input buffer size mismatch]\r\n");
            u_.write_str("m-ready\r\n"); return;
        }
        eng_.load_input_32x32x3(buf_);
        u_.writef("m-warmup-start-%d\r\n", w);
        for (int i = 0; i < w; ++i) eng_.infer();
        u_.write_str("m-warmup-done\r\n");
        u_.writef("m-infer-start-%d\r\n", n);
        u_.writef("m-lap-us-%lu\r\n", (unsigned long)now_us());
        for (int i = 0; i < n; ++i) eng_.infer();
        u_.writef("m-lap-us-%lu\r\n", (unsigned long)now_us());
        u_.write_str("m-infer-done\r\n");
        emit_results();
        u_.write_str("m-ready\r\n");
    }

    void emit_results() {
        const float* p = eng_.last_probs();
        char buf[160];
        int n = snprintf(buf, sizeof(buf),
                         "m-results-[%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f]\r\n",
                         p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]);
        u_.write_str(buf);
    }

    Uart& u_;
    InferenceEngine& eng_;
    uint8_t  buf_[MAX_DB_INPUT_SIZE]{};
    int      expected_{0};
    int      recv_pos_{0};
    std::chrono::steady_clock::time_point t0_;
};

int main(int argc, char** argv) {
    std::string uart   = "/dev/ttyPS0";
    std::string xmodel = "/run/media/mmcblk0p1/resnet18_cifar10.xmodel";
    std::string xclbin = "/run/media/mmcblk0p1/dpu.xclbin";
    speed_t     baud   = B115200;

    for (int i = 1; i < argc; ++i) {
        if      (!strcmp(argv[i], "--uart")   && i+1 < argc) uart   = argv[++i];
        else if (!strcmp(argv[i], "--xmodel") && i+1 < argc) xmodel = argv[++i];
        else if (!strcmp(argv[i], "--xclbin") && i+1 < argc) xclbin = argv[++i];
    }

    setenv("XLNX_VART_FIRMWARE", xclbin.c_str(), 1);
    fprintf(stderr, "VCK190 MLPerf Tiny DUT firmware booting...\n");
    fprintf(stderr, "  UART  : %s\n", uart.c_str());
    fprintf(stderr, "  xmodel: %s\n", xmodel.c_str());
    fprintf(stderr, "  xclbin: %s\n", xclbin.c_str());

    BnKernel bn;
    fprintf(stderr, "  BN-kernel VERSION = 0x%08x\n", bn.version());
    InferenceEngine eng(xmodel);
    Uart u(uart, baud);
    Protocol p(u, eng);
    p.run();
}
