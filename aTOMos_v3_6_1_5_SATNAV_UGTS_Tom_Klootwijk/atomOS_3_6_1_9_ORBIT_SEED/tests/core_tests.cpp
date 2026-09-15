#include "backend.hpp"
#include <iostream>
#include <random>
#include <stdexcept>
#include <cstring>
using namespace satnav;
static std::uint64_t checks=0;
void test(bool v,const char* what){++checks;if(!v)throw std::runtime_error(what);}
void near(double a,double b,double t,const char* what){test(absd(a-b)<=t,what);}
int main(){try{
 for(int q=0;q<2;++q){test(jk_bit(q,0,0)==q,"JK hold");test(jk_bit(q,1,0)==1,"JK set");test(jk_bit(q,0,1)==0,"JK reset");test(jk_bit(q,1,1)==1-q,"JK toggle");}
 for(std::uint32_t v=0;v<65536;++v){int n=0;for(int j=0;j<16;++j)n+=(v>>j)&1;test(pop32(v)==n,"popcount");}
 test(asa_word(255,255,255,128,255).output==0,"whole word");test(asa_word(3,1,3,2,3).output==1,"nonmonotone narrower aperture");
 std::mt19937 random(3615);
 for(int t=0;t<10000;++t){auto x=random(),a=random(),n=random(),b=random(),v=random();auto r=asa_word(x,a,n,b,v);std::uint32_t aa=0,nn=0;int count=0;
  for(int bit=0;bit<32;++bit){std::uint32_t mask=std::uint32_t(1)<<bit;if((x&mask)&&(a&mask)&&(v&mask)){aa|=mask;if(n&mask){nn|=mask;if(b&mask)++count;}}}
  test(r.asa==aa,"ASA oracle");test(r.na==nn,"NA oracle");test(r.hits==std::uint32_t(count),"hits oracle");test(r.output==(count?0:nn),"output oracle");}
 {QR4 qr;for(int i=0;i<4;++i){double row[4]{};row[i]=2.;qr.append(row,2.*(i+1));}double value[4]{};test(qr.solve(value,1e-10),"QR rank");double diag[4]{};test(qr.covariance_diagonal(diag,1e-10),"QR covariance");for(int j=0;j<4;++j){near(value[j],j+1,1e-12,"QR answer");near(diag[j],.25,1e-12,"covariance");}}
 {QR4 qr;double row[4]={1,1,1,1};qr.append(row,4);double value[4]{};test(!qr.solve(value,1e-10),"rank deficient");}
 {Data data;Epoch ep;ep.id=0;ep.seed[0]=1;ep.ready=ep.present=7;data.epochs.push_back(ep);data.observations.assign(192,0);auto result=cpu_run(data,Config{});test(result.results[0].status==TOO_FEW,"missing obs");data.epochs[0].boundary_mask=1;result=cpu_run(data,Config{});test(result.results[0].status==MASK_ABSORBED,"mask status");}
 std::cout<<"PASS counted_checks="<<checks<<" epoch_bytes="<<sizeof(Epoch)<<" result_bytes="<<sizeof(Result)<<"\n";return 0;
 }catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
