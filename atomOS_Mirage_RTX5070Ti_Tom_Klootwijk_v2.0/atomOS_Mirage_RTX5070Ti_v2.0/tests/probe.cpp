#include "atomos/runtime.hpp"
#include <iostream>
#include <sstream>
#include <string>
#include <stdexcept>
using namespace atomos;
std::vector<std::uint8_t> unhex(const std::string&s){if(s=="-")return{};if(s.size()%2)throw std::runtime_error("odd hex");std::vector<std::uint8_t>b;for(std::size_t i=0;i<s.size();i+=2){std::size_t used;auto v=std::stoul(s.substr(i,2),&used,16);if(used!=2)throw std::runtime_error("bad hex");b.push_back(std::uint8_t(v));}return b;}
int main(){std::string line;while(std::getline(std::cin,line)){try{std::istringstream s(line);std::string op;s>>op;
 if(op=="sha"){std::string h;s>>h;std::cout<<hex(sha256(unhex(h)))<<'\n';}
 else if(op=="word"){std::uint32_t p,j,m;unsigned is_or;s>>p>>j>>m>>is_or;if(!s)throw std::runtime_error("word args");std::cout<<word_step(p,j,m,is_or!=0)<<'\n';}
 else if(op=="jitter"){std::string root;std::uint64_t tick,child;unsigned th;s>>root>>tick>>child>>th;auto b=unhex(root);if(b.size()!=32||!s)throw std::runtime_error("jitter args");Digest d{};std::copy(b.begin(),b.end(),d.begin());std::cout<<jitter_bit(d,tick,child,th)<<'\n';}
 else if(op=="vm"){unsigned states,halt,budget;std::uint32_t tape;VMState v;s>>states>>halt>>budget>>v.state>>v.head>>tape;std::vector<std::uint32_t>p(states*2);for(auto&w:p)s>>w;if(!s)throw std::runtime_error("VM args");for(unsigned k=0;k<budget&&v.status==VMStatus::Running;++k)vm_step(v,&tape,32,states,halt,HostProgram{p.data()});std::cout<<v.state<<' '<<v.head<<' '<<unsigned(v.status)<<' '<<v.steps<<' '<<tape<<'\n';}
 else throw std::runtime_error("unknown op");
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
}
