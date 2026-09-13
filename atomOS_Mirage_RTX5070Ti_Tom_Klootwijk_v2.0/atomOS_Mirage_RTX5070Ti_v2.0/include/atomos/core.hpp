#pragma once
// atomOS Mirage / Ring Edition 2.0 -- Tom Klootwijk.
// Shared, typed CPU/CUDA semantics. No device, OS, network, or actuator access here.
#include <cstdint>
#include <cmath>
#include <limits>

#ifdef __CUDACC__
#define ATOMOS_HD __host__ __device__
#else
#define ATOMOS_HD
#endif

namespace atomos {
constexpr float tau = 6.2831853071795864769f;
constexpr std::uint32_t no_cell = 0xffffffffu;
enum class Topology : std::uint32_t { Annulus = 0, Klein = 1 };
enum class Status : std::uint32_t {
    Active = 0, JitterVeto = 1, RadialSink = 2, ObstacleSink = 3,
    NumericFault = 4, LineageOverflow = 5, InactiveParent = 6
};
struct Vec2 { float x, y; };
struct Node {
    std::uint64_t branch = 1;
    float rho = 0.0f, phi = 0.0f;
    std::uint32_t alive = 1, cell = no_cell;
    Status status = Status::Active;
    std::uint32_t orientation = 0;
};
static_assert(sizeof(Node) == 32, "Node layout must be 32 bytes");
static_assert(sizeof(Vec2) == 8, "Vec2 layout must be 8 bytes");
struct Config {
    std::uint32_t n_rho = 128, n_phi = 1024, phi_step = 11, substeps = 4;
    float rho_min = -1.0f, rho_max = 2.0f, dt = 0.125f;
    float growth = 0.3f, omega = 0.45f, wind_x = 0.08f, wind_y = -0.04f;
    Topology topology = Topology::Annulus;
};
ATOMOS_HD inline bool finite(float x) {
    return x == x && x <= 3.402823466e38f && x >= -3.402823466e38f;
}
ATOMOS_HD inline float wrap_phi(float phi) {
    float out = ::fmodf(phi, tau);
    if (out < 0.0f) out += tau;
    return out >= tau ? 0.0f : out;
}
ATOMOS_HD inline std::uint32_t phi_index(float phi, std::uint32_t n) {
    const auto j = static_cast<std::uint32_t>(wrap_phi(phi) * (float(n) / tau));
    return j < n ? j : 0u;
}
ATOMOS_HD inline std::uint32_t pack_coordinate(std::uint32_t radial, std::uint32_t angular) {
    return ((radial & 0xffffu) << 16) | (angular & 0xffffu);
}
ATOMOS_HD inline std::uint32_t rotl32(std::uint32_t x, unsigned s) {
    s &= 31u;
    return s ? ((x << s) | (x >> (32u-s))) : x;
}
ATOMOS_HD inline unsigned popcount32(std::uint32_t x) {
#ifdef __CUDA_ARCH__
    return __popc(x);
#else
    unsigned n = 0;
    while (x) { x &= x-1u; ++n; }
    return n;
#endif
}
// Literal source-register profile, separate from child-node addressing.
// A zero register is absorbing. OR and XOR merge are distinct configurations.
ATOMOS_HD inline std::uint32_t word_step(std::uint32_t psi, std::uint32_t jitter,
                                         std::uint32_t mask, bool merge_or = false) {
    if (!psi) return 0u;
    const auto a = psi << 1, b = psi >> 1;
    const auto shifted = merge_or ? (a | b) : (a ^ b);
    const auto blended = shifted ^ jitter;
    return popcount32(blended & mask) ? 0u : blended;
}
// Quotient: (rho+L, phi) ~ (rho, -phi), and phi ~ phi+2*pi.
// In Klein mode rho is a quotient coordinate, NOT a global physical radius.
ATOMOS_HD inline Status normalize(Node& n, const Config& c) {
    if (!finite(n.rho) || !finite(n.phi)) return Status::NumericFault;
    if (c.topology == Topology::Klein) {
        const float L = c.rho_max-c.rho_min;
        const float qf = ::floorf((n.rho-c.rho_min)/L);
        if (::fabsf(qf) > 1048576.0f) return Status::NumericFault;
        const auto q = static_cast<long long>(qf);
        n.rho -= float(q)*L;
        // Correct a possible one-ULP endpoint after floating-point subtraction.
        if (n.rho < c.rho_min) n.rho = c.rho_min;
        if (n.rho >= c.rho_max) n.rho = ::nextafterf(c.rho_max, c.rho_min);
        if (q % 2 != 0) { n.phi = -n.phi; n.orientation ^= 1u; }
    } else if (n.rho < c.rho_min || n.rho >= c.rho_max) {
        return Status::RadialSink;
    }
    n.phi = wrap_phi(n.phi);
    const float v = (n.rho-c.rho_min)/(c.rho_max-c.rho_min);
    auto i = static_cast<std::uint32_t>(v*float(c.n_rho));
    if (i >= c.n_rho) i = c.n_rho-1;
    n.cell = i*c.n_phi + phi_index(n.phi,c.n_phi);
    return Status::Active;
}
struct HostTables {
    const Vec2* angles;
    const std::uint32_t* mask;
    const std::uint32_t* jitter;
    ATOMOS_HD Vec2 angle(std::uint32_t j) const { return angles[j]; }
    ATOMOS_HD std::uint32_t mask_word(std::uint32_t j) const { return mask[j]; }
    ATOMOS_HD std::uint32_t jitter_word(std::uint32_t j) const { return jitter[j]; }
};
template<class Tables>
ATOMOS_HD inline Vec2 angle_components(float phi,const Config& c,const Tables& t) {
    const float p=wrap_phi(phi);
    const bool reflect=p>tau*0.5f;
    const float a=reflect?tau-p:p;
    auto j=static_cast<std::uint32_t>(::floorf(a*float(c.n_phi)/tau+0.5f));
    if(j>c.n_phi/2)j=c.n_phi/2;
    auto cs=t.angle(j);
    // Explicit odd/even extension also removes residual sin(pi) roundoff.
    if(j==0||j==c.n_phi/2)cs.y=0.0f;
    else if(reflect)cs.y=-cs.y;
    return cs;
}
template<class Tables>
ATOMOS_HD inline Vec2 rhs(Vec2 y, const Config& c, const Tables& t) {
    if (!finite(y.x) || !finite(y.y)) return {NAN,NAN};
    const auto cs = angle_components(y.y,c,t);
    if (c.topology == Topology::Klein) {
        // Even radial and odd angular components are equivariant under phi -> -phi.
        // Symmetric nearest-angle lookup preserves the odd/even interpretation.
        return {c.growth+c.wind_x*cs.x, c.omega*cs.y+c.wind_y*(2.0f*cs.x*cs.y)};
    }
    const float inv_r = ::expf(-y.x); // reference radius is 1 in the synthetic demo
    return {c.growth+inv_r*(c.wind_x*cs.x+c.wind_y*cs.y),
            c.omega+inv_r*(-c.wind_x*cs.y+c.wind_y*cs.x)};
}
ATOMOS_HD inline Vec2 add(Vec2 a, Vec2 b, float h) { return {a.x+h*b.x,a.y+h*b.y}; }
template<class Tables>
ATOMOS_HD inline Vec2 rk4(Vec2 y, float h, const Config& c, const Tables& t) {
    const auto k1=rhs(y,c,t), k2=rhs(add(y,k1,h*0.5f),c,t);
    const auto k3=rhs(add(y,k2,h*0.5f),c,t), k4=rhs(add(y,k3,h),c,t);
    return {y.x+(h/6.0f)*(k1.x+2.0f*k2.x+2.0f*k3.x+k4.x),
            y.y+(h/6.0f)*(k1.y+2.0f*k2.y+2.0f*k3.y+k4.y)};
}
template<class Tables>
ATOMOS_HD inline Node propagate_child(const Node& parent, std::uint32_t side,
                                       std::uint32_t candidate, const Config& c,
                                       const Tables& t) {
    Node n=parent;
    n.alive=0; n.cell=no_cell;
    if (!parent.alive) { n.status=Status::InactiveParent; return n; }
    if (parent.branch == 0 || parent.branch > 0x7fffffffffffffffull) {
        n.status=Status::LineageOverflow; return n;
    }
    // Tier 1: two child identifiers are (id << 1) and (id << 1)|1.
    n.branch=(parent.branch << 1) | (side & 1u);
    // Tier 2: one-bit Hadamard-labelled XOR veto, drawn from the supplied jitter log.
    const auto j=(t.jitter_word(candidate >> 5) >> (candidate & 31u)) & 1u;
    if ((1u ^ j) == 0) { n.status=Status::JitterVeto; return n; }
    // Tier 3: local phi hinge; orientation records a reflected Klein seam.
    float sign=side ? -1.0f : 1.0f;
    if (parent.orientation) sign=-sign;
    n.phi+=sign*tau*float(c.phi_step)/float(c.n_phi);
    n.status=normalize(n,c);
    if (n.status!=Status::Active) return n;
    const auto blocked=[&]() { return (t.mask_word(n.cell>>5) >> (n.cell&31u)) & 1u; };
    if (blocked()) { n.status=Status::ObstacleSink; return n; }
    const float h=c.dt/float(c.substeps);
    for (std::uint32_t k=0;k<c.substeps;++k) {
        const auto y=rk4({n.rho,n.phi},h,c,t);
        n.rho=y.x; n.phi=y.y;
        n.status=normalize(n,c);
        if (n.status!=Status::Active) return n;
        if (blocked()) { n.status=Status::ObstacleSink; return n; }
    }
    n.alive=1;
    return n;
}

enum class VMStatus : std::uint32_t { Running=0,Halted=1,TapeExhausted=2,BadProgram=3 };
struct VMState { std::uint32_t state=0; std::int32_t head=0;
    VMStatus status=VMStatus::Running; std::uint32_t steps=0; };
static_assert(sizeof(VMState)==16,"VMState layout must be 16 bytes");
ATOMOS_HD inline std::uint32_t encode_instruction(std::uint32_t next, unsigned write, int move) {
    return (next<<8) | (std::uint32_t(move+1)<<1) | (write&1u) | 8u;
}
struct HostProgram { const std::uint32_t* words;
    ATOMOS_HD std::uint32_t fetch(std::uint32_t i) const { return words[i]; } };
template<class Program>
ATOMOS_HD inline void vm_step(VMState& s,std::uint32_t* tape,std::uint32_t tape_bits,
                              std::uint32_t states,std::uint32_t halt,const Program& p) {
    if (s.status!=VMStatus::Running) return;
    if (s.state==halt) { s.status=VMStatus::Halted; return; }
    if (s.state>=states || s.steps==0xffffffffu) { s.status=VMStatus::BadProgram; return; }
    if (s.head<0 || std::uint32_t(s.head)>=tape_bits) { s.status=VMStatus::TapeExhausted; return; }
    const auto head=std::uint32_t(s.head);
    const auto read=(tape[head>>5]>>(head&31u))&1u;
    const auto ins=p.fetch((s.state<<1)|read);
    const auto next=ins>>8, move_code=(ins>>1)&3u;
    if (!(ins&8u) || (ins&0xf0u) || move_code==3u || next>=states) {
        s.status=VMStatus::BadProgram; return;
    }
    const long long next_head=static_cast<long long>(s.head)+int(move_code)-1;
    if (next_head<0 || next_head>=tape_bits) { s.status=VMStatus::TapeExhausted; return; }
    const auto bit=1u<<(head&31u);
    tape[head>>5]=(tape[head>>5]&~bit)|((ins&1u)?bit:0u);
    s.head=static_cast<std::int32_t>(next_head); s.state=next; ++s.steps;
    if (s.state==halt) s.status=VMStatus::Halted;
}
} // namespace atomos
