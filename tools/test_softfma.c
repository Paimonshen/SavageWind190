// Checks runtime/simd_softfma.h (the game code's fma without FMA instructions) bit for bit against the FMA
// instructions, in every MXCSR rounding mode with and without FTZ / DAZ. Needs a CPU with FMA.
//   clang -O1 -mfma -Iruntime tools/test_softfma.c -o build/test_softfma && build/test_softfma [millions] [seed]
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xmmintrin.h>

#include "simd_softfma.h"

#ifndef __FMA__
#error "build with -mfma: the FMA instructions are the reference"
#endif

static uint64_t g_rng;
static uint64_t rnd(void) {  // splitmix64
    uint64_t z = (g_rng += 0x9e3779b97f4a7c15ull);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

// an operand of a format (MB fraction bits, EB exponent bits) with its exponent near e (biased), or a special value
static uint64_t operand(int MB, int EB, int e) {
    const int emax = (1 << EB) - 1;
    uint64_t sgn = rnd() & 1, frac = rnd() & ((1ull << MB) - 1);
    switch (rnd() % 16) {
    case 0: frac = 0; break;                                     // a power of two
    case 1: frac = (1ull << MB) - 1 - (rnd() & 7); break;        // all ones, nearly
    case 2: frac &= ~((1ull << (rnd() % MB)) - 1); break;        // few significant bits
    case 3: e = 0; break;                                        // a denormal (or zero)
    case 4: {                                                    // special values
        static const int be[] = {0, 0, 1, -1, -2};
        int b = be[rnd() % 5];
        e = b < 0 ? emax + b + 1 : b;  // (-1: inf / NaN, -2: the largest finite exponent)
        if (rnd() & 1) frac = rnd() & 1 ? 0 : 1;
        break;
    }
    }
    if (e < 0) e = 0;
    if (e > emax) e = emax;
    return sgn << (MB + EB) | (uint64_t)e << MB | frac;
}

typedef struct { uint64_t x, y, z; } Case;

// operands whose sum lands where the rounding is hard: exponents near each other, cancellation, the underflow and
// overflow edges
static Case make_case(int MB, int EB, int dbl) {
    const int bias = (1 << (EB - 1)) - 1;
    Case c;
    int kind = rnd() % 6;
    if (kind == 0) {  // anything
        c.x = rnd(), c.y = rnd(), c.z = rnd();
        if (!dbl) c.x &= 0xffffffff, c.y &= 0xffffffff, c.z &= 0xffffffff;
        return c;
    }
    int target;  // the product's biased exponent
    switch (kind) {
    case 1: target = 1 + (int)(rnd() % 6) - 3; break;            // the underflow edge
    case 2: target = 2 * bias - (int)(rnd() % 4); break;         // the overflow edge
    case 3: target = -(int)(rnd() % (MB + 4)); break;            // product below the denormals
    default: target = (int)(rnd() % (2 * bias + 1)); break;
    }
    int ex = (int)(rnd() % (2 * bias + 1)) - bias + bias;  // x anywhere, y to reach target
    int ey = target - ex + bias;
    c.x = operand(MB, EB, ex), c.y = operand(MB, EB, ey);
    int ez = target + (int)(rnd() % 7) - 3;
    if (rnd() % 4 == 0) ez = target - (int)(rnd() % (3 * MB));  // far below
    c.z = operand(MB, EB, ez);
    if (rnd() % 3 == 0) {  // z near -x*y: cancellation
        unsigned csr = _mm_getcsr();
        _mm_setcsr(0x1f80);
        if (dbl) {
            double x, y, z;
            memcpy(&x, &c.x, 8), memcpy(&y, &c.y, 8);
            z = -(x * y);
            memcpy(&c.z, &z, 8);
        } else {
            float x, y, z;
            uint32_t ux = (uint32_t)c.x, uy = (uint32_t)c.y, uz;
            memcpy(&x, &ux, 4), memcpy(&y, &uy, 4);
            z = -(x * y);
            memcpy(&uz, &z, 4);
            c.z = uz;
        }
        _mm_setcsr(csr);
        c.z += (uint64_t)(int64_t)((int)(rnd() % 5) - 2);  // a few ulp off
        if (!dbl) c.z &= 0xffffffff;
    }
    return c;
}

int main(int argc, char **argv) {
    long n = (argc > 1 ? atol(argv[1]) : 2) * 1000000;
    g_rng = argc > 2 ? strtoull(argv[2], NULL, 0) : 1;
    long fails = 0, done = 0;
    for (long i = 0; i < n; i++) {
        int dbl = i & 1;
        Case c = dbl ? make_case(52, 11, 1) : make_case(23, 8, 0);
        unsigned mode = (unsigned)(rnd() & 15);
        unsigned csr = 0x1f80 | (mode & 3) << 13 | (mode & 4 ? 0x40u : 0) | (mode & 8 ? 0x8000u : 0);
        uint64_t want, got;
        int nan_want, nan_got;
        if (dbl) {
            volatile double x, y, z;
            memcpy((double *)&x, &c.x, 8), memcpy((double *)&y, &c.y, 8), memcpy((double *)&z, &c.z, 8);
            _mm_setcsr(csr);
            double w = __builtin_fma(x, y, z), g = simd_soft_fma_d(x, y, z);
            _mm_setcsr(0x1f80);
            memcpy(&want, &w, 8), memcpy(&got, &g, 8);
            nan_want = w != w, nan_got = g != g;
        } else {
            volatile float x, y, z;
            uint32_t ux = (uint32_t)c.x, uy = (uint32_t)c.y, uz = (uint32_t)c.z, uw, ug;
            memcpy((float *)&x, &ux, 4), memcpy((float *)&y, &uy, 4), memcpy((float *)&z, &uz, 4);
            _mm_setcsr(csr);
            float w = __builtin_fmaf(x, y, z), g = simd_soft_fma_s(x, y, z);
            _mm_setcsr(0x1f80);
            memcpy(&uw, &w, 4), memcpy(&ug, &g, 4);
            want = uw, got = ug;
            nan_want = w != w, nan_got = g != g;
        }
        done++;
        if (nan_want && nan_got) continue;
        if (want != got) {
            if (fails++ < 20)
                printf("%s rc=%u daz=%d ftz=%d  x=%016llx y=%016llx z=%016llx  want %016llx got %016llx\n",
                       dbl ? "fma " : "fmaf", mode & 3, !!(mode & 4), !!(mode & 8), (unsigned long long)c.x,
                       (unsigned long long)c.y, (unsigned long long)c.z, (unsigned long long)want,
                       (unsigned long long)got);
        }
    }
    printf("%ld cases (fma and fmaf, every rounding mode, FTZ / DAZ): %ld failing\n", done, fails);
    return fails != 0;
}
