#include "atomos/exact_program.hpp"
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace ex = atomos::exact;
namespace {
int assertions = 0;
void check(bool condition, const char* label) {
    ++assertions;
    if (!condition) throw std::runtime_error(label);
}
ex::Node literal(std::int32_t a, std::int32_t b, std::uint32_t units = 0) {
    ex::Node n{}; n.op = ex::Op::Literal; n.literal = {a,b}; n.units = units; return n;
}
ex::Node input(std::uint32_t slot, std::uint32_t units = 0) {
    ex::Node n{}; n.op = ex::Op::Input; n.input_slot = slot; n.units = units; return n;
}
ex::Node binary(ex::Op op, std::uint32_t a, std::uint32_t b, std::uint32_t units = 0) {
    ex::Node n{}; n.op = op; n.args[0] = a; n.args[1] = b; n.units = units; return n;
}
struct Fixture {
    ex::Program* program = nullptr;
    std::vector<std::uint32_t> words;
    Fixture(const std::vector<ex::Node>& nodes, std::uint32_t inputs, std::uint32_t root)
        : words(ex::seed_word_count(static_cast<std::uint32_t>(nodes.size()))) {
        char error[512]{};
        if (!ex::encode_seed(nodes.data(), static_cast<std::uint32_t>(nodes.size()), inputs, root,
                0xfedcba9876543210ULL, words.data(), words.size(), error, sizeof(error)))
            throw std::runtime_error(std::string("encode: ")+error);
        if (!ex::create_program(words.data(), words.size(), &program, error, sizeof(error)))
            throw std::runtime_error(std::string("create: ")+error);
    }
    ~Fixture() { ex::destroy_program(program); }
    std::vector<ex::Result> run(const std::vector<ex::Coeff>& samples, std::size_t count) {
        char error[512]{};
        std::vector<ex::Result> results(count);
        if (!ex::evaluate(program, samples.empty() ? nullptr : samples.data(), count, results.data(), error, sizeof(error)))
            throw std::runtime_error(std::string("evaluate: ")+error);
        return results;
    }
    void roundtrip() {
        std::vector<std::uint32_t> fetched(words.size());
        char error[512]{};
        check(ex::read_seed_words(program, fetched.data(), fetched.size(), error, sizeof(error)), "texture readback succeeds");
        check(words == fetched, "all canonical seed bits survive bit-plane upload, GPU expansion and integer texture fetch");
    }
};
void value(const ex::Result& r, int a, int b, int sign) {
    check(r.status == (sign ? ex::Status::Value : ex::Status::Boundary), "resolved status");
    check(r.value.a == a && r.value.b == b, "exact coefficients");
    check(r.sign == sign && r.accept_hinge == (sign ? 1u : 0u), "exact sign and eligibility");
    check(r.failed_node == 0xffffffffu, "no failed node on success");
}
void unresolved(const ex::Result& r, std::uint32_t node) {
    check(r.status == ex::Status::Unresolved, "out of domain is unresolved");
    check(r.accept_hinge == 0 && r.sign == 0 && r.failed_node == node, "unresolved cannot enable a hinge");
}
void arithmetic() {
    auto pm = binary(ex::Op::PhiMultiply, 0, 0);
    Fixture phi({input(0),pm}, 1, 1);
    const int B = ex::coefficient_limit;
    auto r = phi.run({{1,0},{0,1},{-2,1},{B,B}}, 4);
    value(r[0],0,1,1); value(r[1],1,1,1); value(r[2],1,-1,-1); unresolved(r[3],1);
    phi.roundtrip();
    Fixture multiplication({input(0),input(1),binary(ex::Op::Multiply,0,1)},2,2);
    r = multiplication.run({{0,1},{-1,1}, {0,1},{0,1}, {B,0},{B,0}, {-2,1},{3,-1}},4);
    value(r[0],1,0,1); value(r[1],1,1,1); unresolved(r[2],2); value(r[3],-7,4,-1);
    Fixture addition({input(0),input(1),binary(ex::Op::Add,0,1)},2,2);
    r = addition.run({{B,0},{1,0}, {5,-3},{-5,3}, {0,0},{0,1}},3);
    unresolved(r[0],2); value(r[1],0,0,0); value(r[2],0,1,1);
    Fixture subtraction({input(0),input(1),binary(ex::Op::Subtract,0,1)},2,2);
    r = subtraction.run({{-B,0},{1,0}, {1,1},{0,1}},2);
    unresolved(r[0],2); value(r[1],1,0,1);
    Fixture literal_phi({literal(0,1),binary(ex::Op::Multiply,0,0)},0,1);
    value(literal_phi.run({},1)[0],1,1,1);
    literal_phi.roundtrip();
}
void signs_and_bounds() {
    const int B = ex::coefficient_limit;
    Fixture identity({input(0)},1,0);
    const std::vector<ex::Coeff> samples = {
        {-165580141,102334155}, {-267914296,165580141},
        {-433494437,267914296}, {-701408733,433494437},
        {B,B}, {-B,B}, {B,-B}, {0,0},
        {std::numeric_limits<std::int32_t>::max(),0},
        {std::numeric_limits<std::int32_t>::min(),0}, {0,-1}};
    auto r = identity.run(samples,samples.size());
    const int expected[] = {-1,1,-1,1,1,1,-1,0};
    for (int i=0;i<8;++i) value(r[i],samples[i].a,samples[i].b,expected[i]);
    unresolved(r[8],0); unresolved(r[9],0); value(r[10],0,-1,-1);
    identity.roundtrip();
    // Values outside the root dependency closure must not force fallback.
    Fixture closure({literal(1,-1),literal(std::numeric_limits<std::int32_t>::max(),0)},0,0);
    value(closure.run({},1)[0],1,-1,-1);
    closure.roundtrip();
    Fixture bad_literal({literal(std::numeric_limits<std::int32_t>::min(),0)},0,0);
    unresolved(bad_literal.run({},1)[0],0);
}
std::vector<ex::Node> plane_nodes() {
    std::vector<ex::Node> n = {literal(1,0),literal(0,0),literal(0,0),literal(0,1,ex::unit_length),
                              input(0,ex::unit_length),input(1,ex::unit_length),input(2,ex::unit_length)};
    ex::Node guard{}; guard.op=ex::Op::PlaneGuard; guard.units=ex::unit_length;
    const std::uint32_t args[] = {4,5,6,0,1,2,3};
    for(int i=0;i<7;++i) guard.args[i]=args[i];
    n.push_back(guard); return n;
}
void guards() {
    auto nodes = plane_nodes();
    Fixture plane(nodes,3,7);
    auto r = plane.run({{0,1},{0,0},{0,0}, {-1,1},{7,0},{-6,1}, {1,1},{-1,0},{1,-1}},3);
    value(r[0],0,0,0); value(r[1],-1,0,-1); value(r[2],1,0,1);
    // Eligibility repeated at a level is not an event identity or acceptance.
    value(plane.run({{1,1},{0,0},{0,0}},1)[0],1,0,1);
    plane.roundtrip();
    nodes[0]=literal(0,0);
    Fixture degenerate(nodes,3,7);
    unresolved(degenerate.run({{0,0},{0,0},{0,0}},1)[0],7);
    // Conservative bounded accumulation: cancellation later in the sum cannot
    // repair an intermediate result which left this native execution domain.
    nodes=plane_nodes(); nodes[1]=literal(1,0); nodes[2]=literal(1,0);
    Fixture limited(nodes,3,7);
    const int B=ex::coefficient_limit;
    unresolved(limited.run({{B,0},{B,0},{-B,0}},1)[0],7);
}
void malformed() {
    Fixture valid({literal(-123,456)},0,0);
    auto rejects = [&](std::vector<std::uint32_t> w) {
        ex::Program* p=nullptr; char error[512]{};
        const bool ok=ex::create_program(w.data(),w.size(),&p,error,sizeof(error));
        if(p) ex::destroy_program(p);
        check(!ok && p==nullptr && error[0],"malformed seed rejected before evaluation");
    };
    auto w=valid.words; w[0]^=1; rejects(w);
    w=valid.words; w.pop_back(); rejects(w);
    w=valid.words; w[5]=1; rejects(w);
    w=valid.words; w[ex::header_words+13]=1; rejects(w);
    w=valid.words; w[ex::header_words]=99; rejects(w);
    w=valid.words; w[ex::header_words+6]=1; rejects(w);
    std::vector<ex::Node> n={input(0),input(1,ex::unit_length),binary(ex::Op::Add,0,1)};
    w.resize(ex::seed_word_count(3)); char error[512]{};
    check(!ex::encode_seed(n.data(),3,2,2,0,w.data(),w.size(),error,sizeof(error)),"unit mismatch rejected");
    n={literal(0,0),binary(ex::Op::Add,0,1)};
    w.resize(ex::seed_word_count(2));
    check(!ex::encode_seed(n.data(),2,0,1,0,w.data(),w.size(),error,sizeof(error)),"forward reference rejected");
    n=plane_nodes(); n[4].units=0; w.resize(ex::seed_word_count(8));
    check(!ex::encode_seed(n.data(),8,3,7,0,w.data(),w.size(),error,sizeof(error)),"spatial coordinate must have length units");
    n={input(0),input(0,ex::unit_length)}; w.resize(ex::seed_word_count(2));
    check(!ex::encode_seed(n.data(),2,1,0,0,w.data(),w.size(),error,sizeof(error)),"sample slot unit alias rejected");
}
} // namespace
int main() {
    try {
        check(ex::device_available(),"CUDA device is required for native exact execution tests");
        arithmetic(); signs_and_bounds(); guards(); malformed();
        std::cout << "exact_program_tests: " << assertions << " assertions passed on CUDA\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "exact_program_tests: " << error.what() << '\n'; return 1;
    }
}
