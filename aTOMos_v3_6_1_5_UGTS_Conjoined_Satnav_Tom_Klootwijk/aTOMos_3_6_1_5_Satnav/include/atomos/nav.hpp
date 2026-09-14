#pragma once
#include "math.hpp"
namespace ao {
constexpr unsigned max_sats=32;
enum Status:std::uint32_t {ok=0,insufficient=1,absorbed=2,invalid_input=3,rank_deficient=4,iteration_limit=5,numeric_failure=6};
inline const char* status_name(unsigned s){switch(s){case ok:return "ok";case insufficient:return "insufficient_observations";case absorbed:return "whole_word_absorbed";case invalid_input:return "invalid_input";case rank_deficient:return "rank_deficient";case iteration_limit:return "iteration_limit";default:return "numeric_failure";}}
struct Observation {double x,y,z,code,sigma;};
struct Epoch {
 std::uint64_t id,tick_ms;double initial[4];double hinge;
 std::uint32_t count,asa_mask,na_mask,boundary_mask,q_before,j,k,blend_bits;
};
struct SolveConfig {unsigned max_iterations;double position_tolerance,clock_tolerance,rank_relative;};
inline SolveConfig default_solver(){return {20,1e-4,1e-4,1e-11};}
struct Solution {
 std::uint32_t status,iterations,used,asa,na,hits,output_mask,q_after;
 double state[4],rms_m,chi2,formal_sigma[4];
};
struct Diagnostic {
 double east,north,up,rho,theta,delta_rho,delta_theta,otan_raw,otan_relative,otan_directed,cone_residual,sphere_l,sphere_r;
 std::uint64_t key_contiguous,key_morton;
 std::uint32_t chart_status,otan_status;std::int32_t cone_class;std::uint32_t sphere_flags;
};
AO_HD inline Solution empty_solution(){
 Solution s{};s.status=invalid_input;for(int i=0;i<4;++i){s.state[i]=bad();s.formal_sigma[i]=bad();}s.rms_m=s.chi2=bad();return s;
}
// Streaming Givens QR, no normal equations in the position update.
struct QR4 {
 double R[4][4],z[4];
 AO_HD void clear(){for(int i=0;i<4;++i){z[i]=0;for(int j=0;j<4;++j)R[i][j]=0;}}
 AO_HD void add_row(double a[4],double b){
  for(int k=0;k<4;++k){double r=::hypot(R[k][k],a[k]);if(r==0)continue;
   double c=R[k][k]/r,s=a[k]/r;R[k][k]=r;
   for(int j=k+1;j<4;++j){double v=c*R[k][j]+s*a[j];a[j]=-s*R[k][j]+c*a[j];R[k][j]=v;}
   double v=c*z[k]+s*b;b=-s*z[k]+c*b;z[k]=v;
  }
 }
 AO_HD bool full_rank(double tol) const{double scale=0;for(int i=0;i<4;++i)scale=::fmax(scale,::fabs(R[i][i]));
  if(!finite(scale)||scale==0)return false;
  for(int i=0;i<4;++i){if(!finite(R[i][i])||::fabs(R[i][i])<=tol*scale)return false;}
  return true;}
 AO_HD bool backsolve(const double rhs[4],double x[4]) const{
  for(int i=3;i>=0;--i){double v=rhs[i];for(int j=i+1;j<4;++j)v-=R[i][j]*x[j];x[i]=v/R[i][i];if(!finite(x[i]))return false;}return true;
 }
};
struct LocalReader {const Observation* data;AO_HD Observation get(unsigned i)const{return data[i];}};
template<class Reader>
AO_HD bool form_qr(const Reader& reader,const Epoch& e,const double x[4],std::uint32_t mask,QR4& qr,double& ss,double& chi){
 qr.clear();ss=chi=0;
 for(unsigned i=0;i<e.count;++i){if(!(mask&(1u<<i)))continue;Observation o=reader.get(i);
  double dx=x[0]-o.x,dy=x[1]-o.y,dz=x[2]-o.z,r=::sqrt(dx*dx+dy*dy+dz*dz);
  if(!finite(r)||r<=0)return false;
  double residual=o.code-(r+x[3]);
  double row[4]={dx/(r*o.sigma),dy/(r*o.sigma),dz/(r*o.sigma),1/o.sigma};
  double b=residual/o.sigma;if(!finite(b))return false;
  for(int c=0;c<4;++c){if(!finite(row[c]))return false;}
  qr.add_row(row,b);ss+=residual*residual;chi+=b*b;
 }
 for(int r=0;r<4;++r){if(!finite(qr.z[r]))return false;for(int c=0;c<4;++c){if(!finite(qr.R[r][c]))return false;}}
 return finite(ss)&&finite(chi);
}
template<class Reader>
AO_HD Solution solve(const Reader& reader,const Epoch& e,const SolveConfig& cfg){
 Solution s=empty_solution();if(e.count>max_sats||e.j>1||e.k>1||e.q_before>1)return s;
 s.q_after=jk(e.q_before,e.j,e.k);CoreWord c=asa_word(low_mask(e.count),e.asa_mask,e.na_mask,e.boundary_mask,low_mask(e.count));
 s.asa=c.asa;s.na=c.na;s.hits=c.hits;s.output_mask=c.output;s.used=popcount(c.output);
 if(c.hits){s.status=absorbed;return s;}if(s.used<4){s.status=insufficient;return s;}
 for(unsigned i=0;i<e.count;++i){if(!(c.output&(1u<<i)))continue;auto o=reader.get(i);
  if(!finite(o.x)||!finite(o.y)||!finite(o.z)||!finite(o.code)||!finite(o.sigma)||o.sigma<=0||o.code<=0)return s;}
 if(!cfg.max_iterations||!finite(cfg.position_tolerance)||!finite(cfg.clock_tolerance)||!finite(cfg.rank_relative)||cfg.position_tolerance<=0||cfg.clock_tolerance<=0||cfg.rank_relative<=0)return s;
 for(int k=0;k<4;++k){if(!finite(e.initial[k]))return s;s.state[k]=e.initial[k];}
 bool converged=false;QR4 qr;double ss=0,chi=0;
 for(unsigned it=0;it<cfg.max_iterations;++it){
  if(!form_qr(reader,e,s.state,c.output,qr,ss,chi)){s.status=numeric_failure;return s;}
  if(!qr.full_rank(cfg.rank_relative)){s.status=rank_deficient;return s;}
  double delta[4]={};if(!qr.backsolve(qr.z,delta)){s.status=numeric_failure;return s;}
  for(int k=0;k<4;++k){s.state[k]+=delta[k];if(!finite(s.state[k])){s.status=numeric_failure;return s;}}
  s.iterations=it+1;double step=::sqrt(sq(delta[0])+sq(delta[1])+sq(delta[2]));
  if(step<=cfg.position_tolerance&&::fabs(delta[3])<=cfg.clock_tolerance){converged=true;break;}
 }
 if(!form_qr(reader,e,s.state,c.output,qr,ss,chi)){s.status=numeric_failure;return s;}
 s.rms_m=::sqrt(ss/s.used);s.chi2=chi;
 if(!qr.full_rank(cfg.rank_relative)){s.status=rank_deficient;return s;}
 // Formal covariance diag = diag(R^{-1} R^{-T}), supplied independent code variances.
 double diag[4]={};for(int j=0;j<4;++j){double rhs[4]={},column[4]={};rhs[j]=1;
  if(!qr.backsolve(rhs,column)){s.status=numeric_failure;return s;}for(int i=0;i<4;++i)diag[i]+=column[i]*column[i];}
 for(int i=0;i<4;++i){s.formal_sigma[i]=::sqrt(diag[i]);if(!finite(s.formal_sigma[i])){s.status=numeric_failure;return s;}}
 s.status=converged?ok:iteration_limit;return s;
}
AO_HD inline Diagnostic empty_diagnostic(){Diagnostic d{};d.chart_status=1;d.otan_status=1;d.cone_class=2;
 d.east=d.north=d.up=d.rho=d.theta=d.delta_rho=d.delta_theta=d.otan_raw=d.otan_relative=d.otan_directed=d.cone_residual=d.sphere_l=d.sphere_r=bad();return d;}
AO_HD inline Diagnostic enrich(const Solution& s,const Epoch& e,const Solution* previous,const Epoch* previous_epoch,const GeoConfig& g){
 Diagnostic d=empty_diagnostic();if(s.status!=ok)return d;
 Vec3 local=enu({s.state[0],s.state[1],s.state[2]},g);d.east=local.x;d.north=local.y;d.up=local.z;
 d.cone_residual=cone_sdf(local,g.cone);d.cone_class=relation({d.cone_residual,d.cone_residual},g.relation_margin);
 d.sphere_l=sphere_sdf(local,g.sphere_l,g.sphere_radius);d.sphere_r=sphere_sdf(local,g.sphere_r,g.sphere_radius);
 d.sphere_flags=(d.sphere_l<=0?1u:0u)|(d.sphere_r<=0?2u:0u);
 double r=::hypot(local.x,local.y);if(r<g.core_radius){d.chart_status=2;return d;}
 d.rho=::log(r/g.r0);d.theta=wrap(::atan2(local.y,local.x));
 if(!finite(d.rho)||d.rho< -20||d.rho>0||!finite(e.hinge)){d.chart_status=3;return d;}
 d.chart_status=0;auto q=quantize(d.rho,d.theta,e.tick_ms,e.hinge);d.key_contiguous=pack_contiguous(q);d.key_morton=pack_morton(q);
 if(!previous||!previous_epoch||previous->status!=ok||e.tick_ms<=previous_epoch->tick_ms)return d;
 Vec3 pl=enu({previous->state[0],previous->state[1],previous->state[2]},g);double pr=::hypot(pl.x,pl.y);
 if(pr<g.core_radius)return d;
 double prev_rho=::log(pr/g.r0);
 if(!finite(prev_rho)||prev_rho< -20||prev_rho>0)return d;
 d.delta_rho=d.rho-prev_rho;d.delta_theta=wrap(d.theta-::atan2(pl.y,pl.x));
 if(d.delta_rho==0&&d.delta_theta==0){d.otan_status=2;return d;}
 d.otan_directed=wrap(::atan2(d.delta_theta,d.delta_rho)-g.axis_angle);
 if(d.delta_rho==0){d.otan_status=3;return d;}double ratio=d.delta_theta/d.delta_rho;
 if(!finite(ratio)||(d.delta_theta!=0&&ratio==0)){d.otan_status=4;return d;}
 d.otan_raw=::atan(ratio);d.otan_relative=d.otan_raw-g.axis_angle;d.otan_status=0;return d;
}
}
