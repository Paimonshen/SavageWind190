// Fused multiply-add in integer arithmetic, for x86-64 game code built without FMA (the compatible target,
// runtime/gamebuild.c). It does what the FMA instructions do with the thread's MXCSR: DAZ flushes denormal
// operands, RC rounds, FTZ flushes tiny results (tininess after rounding, as x86 detects it).
// The C library's fma is no use there: glibc's software fallback (taken on CPUs without FMA) is a few ulp off with
// FTZ/DAZ set or in a directed rounding mode (tools/test_simd.py: fmadd/fnmadd/fnmsub on d registers), and costs
// ~400 cycles a call. tools/test_softfma.c checks this one bit for bit against the FMA instructions.
// NaN results only have to be NaNs: simd_fp.h's FBAD path gives ARM's.
#pragma once
#include <stdint.h>
#include <string.h>
#include <xmmintrin.h>

typedef __uint128_t sfma_u128;

static inline __attribute__((always_inline)) int sfma_bitlen(sfma_u128 m) {
    uint64_t hi = (uint64_t)(m >> 64), lo = (uint64_t)m;
    return hi ? 128 - __builtin_clzll(hi) : lo ? 64 - __builtin_clzll(lo) : 0;
}

// m >> d, any bits shifted out kept as a sticky bit 0 (the other operand's bit 0 is always clear, so a sum or
// difference with it never lands on a rounding boundary: see sfma_core)
static inline __attribute__((always_inline)) sfma_u128 sfma_shr(sfma_u128 m, int d) {
    if (d == 0) return m;
    if (d >= 128) return m != 0;
    return (m >> d) | ((m & (((sfma_u128)1 << d) - 1)) != 0);
}

// x*y + z for finite, non-zero operands of a binary format with MB fraction and EB exponent bits (binary32: 23, 8;
// binary64: 52, 11), as bit patterns. csr: MXCSR (RC, FTZ; DAZ is applied by the caller).
static inline __attribute__((always_inline)) uint64_t sfma_core(uint64_t ux, uint64_t uy, uint64_t uz, const int MB,
                                                               const int EB, unsigned csr) {
    const int bias = (1 << (EB - 1)) - 1, emin = 1 - bias, mine = emin - MB;  // mine: the smallest subnormal's
    const int p = MB + 1;                                                    // exponent; p: the precision
    const uint64_t sgn = 1ull << (MB + EB), fmask = (1ull << MB) - 1, inf = (((1ull << EB) - 1) << MB);
    const int rc = (csr >> 13) & 3;  // 0 to nearest, 1 down, 2 up, 3 toward zero
    // operand = m * 2^e
#define SFMA_UNPACK(u, m, e)                                                                                           \
    do {                                                                                                                \
        int be_ = (int)(((u) >> MB) & ((1u << EB) - 1));                                                                \
        m = ((u) & fmask) | (be_ ? 1ull << MB : 0);                                                                     \
        e = (be_ ? be_ : 1) - bias - MB;                                                                                \
    } while (0)
    uint64_t mx, my, mz;
    int ex, ey, ez;
    SFMA_UNPACK(ux, mx, ex);
    SFMA_UNPACK(uy, my, ey);
    SFMA_UNPACK(uz, mz, ez);
#undef SFMA_UNPACK
    int sp = (int)(((ux ^ uy) >> (MB + EB)) & 1), sz = (int)((uz >> (MB + EB)) & 1);
    // the exact product (at most 106 bits) and the addend, both with their top bit at bit 125: the product's lowest
    // set bit is then at bit 20 or above, the addend's at 73 or above. So a shift of 20 bits or less (the only case
    // where the two can cancel) is exact; a longer one leaves the larger operand's top bit at 125 and the sum's at
    // 124 or above, 70 bits over where it is rounded.
    sfma_u128 P = (sfma_u128)mx * my, Z = mz;
    int ep = ex + ey, sh;
    sh = 125 - sfma_bitlen(P), P <<= sh, ep -= sh;
    sh = 125 - sfma_bitlen(Z), Z <<= sh, ez -= sh;
    int e, s;
    if (ep >= ez) Z = sfma_shr(Z, ep - ez), e = ep;
    else P = sfma_shr(P, ez - ep), e = ez;
    sfma_u128 M;
    if (sp == sz) M = P + Z, s = sp;
    else if (P >= Z) M = P - Z, s = sp;
    else M = Z - P, s = sz;
    if (!M) return rc == 1 ? sgn : 0;  // exact zero of opposite signs: +0, -0 rounding down

    // round M * 2^e to the format: k bits (fewer when subnormal), q * 2^qe
    int n = sfma_bitlen(M), L = e + n - 1;  // L: the exponent of the top bit
    int k = L >= emin ? p : L - mine + 1;
    uint64_t q;
    int qe = mine, up = 0;
    if (k <= 0) {  // below the smallest subnormal (k == 0: at least half of it)
        q = 0;
        int above_half = k == 0 && (M & (M - 1)) != 0;
        up = rc == 0 ? above_half : rc == 1 ? s : rc == 2 ? !s : 0;
    } else if (n <= k) {
        q = (uint64_t)M << (k - n), qe = e - (k - n);
    } else {
        int d = n - k;
        sfma_u128 rem = M & (((sfma_u128)1 << d) - 1), half = (sfma_u128)1 << (d - 1);
        q = (uint64_t)(M >> d), qe = e + d;
        up = rc == 0 ? rem > half || (rem == half && (q & 1)) : rc == 1 ? rem && s : rc == 2 ? rem && !s : 0;
    }
    q += up;

    // FTZ: a tiny result (below the smallest normal once rounded to p bits with an unbounded exponent) is zero
    if ((csr & 0x8000u) && L < emin) {
        int tiny = 1;
        if (L == emin - 1 && n > p) {  // just below: rounding may carry it up to the smallest normal
            int d = n - p;
            sfma_u128 rem = M & (((sfma_u128)1 << d) - 1), half = (sfma_u128)1 << (d - 1);
            uint64_t q2 = (uint64_t)(M >> d);
            int up2 = rc == 0 ? rem > half || (rem == half && (q2 & 1)) : rc == 1 ? rem && s : rc == 2 ? rem && !s : 0;
            tiny = q2 + up2 < (1ull << p);
        }
        if (tiny) return s ? sgn : 0;
    }

    uint64_t r;
    if (!q) {
        r = 0;
    } else {
        int lb = 64 - __builtin_clzll(q), Lq = qe + lb - 1;
        if (Lq > bias) {  // overflow: infinity, or the largest finite value when rounding toward zero from it
            r = rc == 0 || (rc == 1 && s) || (rc == 2 && !s) ? inf : inf - 1;
        } else if (Lq >= emin) {
            if (lb > p) q >>= 1, lb--;  // (rounded up to 2^p: exact)
            r = ((uint64_t)(Lq + bias) << MB) | ((q << (p - lb)) & fmask);
        } else {
            r = q;  // subnormal (qe == mine)
        }
    }
    return r | (s ? sgn : 0);
}

// binary32 rounding to nearest (the game's mode), finite non-zero operands: the product is exact in a double, the sum's
// rounding error exact by TwoSum (no double here is ever denormal or near an infinity), and the sum rounded to odd
// (its last bit set when inexact) rounds to the same float as the exact value would.
static inline __attribute__((always_inline)) int sfma_fast_s(uint32_t ux, uint32_t uy, uint32_t uz, unsigned csr,
                                                            uint32_t *out) {
    if (csr & 0x6000u) return 0;  // (a directed rounding mode: sfma_core)
    float x, y, z;
    memcpy(&x, &ux, 4), memcpy(&y, &uy, 4), memcpy(&z, &uz, 4);
    double p = (double)x * (double)y, zd = z, s = p + zd, bv = s - p, err = (p - (s - bv)) + (zd - bv);
    if (err != 0) {
        uint64_t u;
        memcpy(&u, &s, 8);
        if (!(u & 1)) u += (err > 0) == (s > 0) ? 1 : (uint64_t)-1;
        memcpy(&s, &u, 8);
    }
    float r = (float)s;  // (MXCSR's FTZ flushes it as the FMA instruction would)
    memcpy(out, &r, 4);
    return 1;
}
static inline __attribute__((always_inline)) int sfma_fast_d(uint64_t ux, uint64_t uy, uint64_t uz, unsigned csr,
                                                            uint64_t *out) {
    (void)ux, (void)uy, (void)uz, (void)csr, (void)out;
    return 0;
}

// fma(x, y, z): the cases with an infinity, a NaN or a zero by the host's own multiply and add, which round and
// flush as the FMA instructions do there; the rest exactly.
#define SFMA_DEFINE(name, F, T, U, MB, EB)                                                                              \
    __attribute__((noinline)) static T name(T x, T y, T z) {                                                            \
        const U sgn = (U)1 << (MB + EB), inf = (((U)1 << EB) - 1) << MB;                                                \
        unsigned csr = _mm_getcsr();                                                                                    \
        U ux, uy, uz;                                                                                                   \
        memcpy(&ux, &x, sizeof ux), memcpy(&uy, &y, sizeof uy), memcpy(&uz, &z, sizeof uz);                             \
        if (csr & 0x40u) { /* DAZ */                                                                                    \
            if (!(ux & inf)) ux &= sgn;                                                                                 \
            if (!(uy & inf)) uy &= sgn;                                                                                 \
            if (!(uz & inf)) uz &= sgn;                                                                                 \
        }                                                                                                               \
        U ax = ux & ~sgn, ay = uy & ~sgn, az = uz & ~sgn;                                                               \
        if (ax >= inf || ay >= inf || az >= inf || !ax || !ay || !az) {                                                 \
            volatile T fx, fy, fz;                                                                                      \
            memcpy((T *)&fx, &ux, sizeof ux), memcpy((T *)&fy, &uy, sizeof uy), memcpy((T *)&fz, &uz, sizeof uz);       \
            if (az >= inf && ax < inf && ay < inf) return fz; /* (x*y alone may overflow to the other infinity) */      \
            if (!az && ax && ay && ax < inf && ay < inf) return fx * fy; /* the product's own rounding and sign */      \
            volatile T prod = fx * fy;                                                                                  \
            return prod + fz;                                                                                           \
        }                                                                                                               \
        U r;                                                                                                            \
        if (!sfma_fast_##F(ux, uy, uz, csr, &r)) r = (U)sfma_core(ux, uy, uz, MB, EB, csr);                             \
        T t;                                                                                                            \
        memcpy(&t, &r, sizeof t);                                                                                       \
        return t;                                                                                                       \
    }
SFMA_DEFINE(simd_soft_fma_s, s, float, uint32_t, 23, 8)
SFMA_DEFINE(simd_soft_fma_d, d, double, uint64_t, 52, 11)
#undef SFMA_DEFINE
