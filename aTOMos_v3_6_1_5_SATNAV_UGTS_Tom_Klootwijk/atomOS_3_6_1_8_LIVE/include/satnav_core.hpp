#pragma once
// atomOS 3.6.1.7 / SATNAV-R1. Passive corrected-code positioning.
// All GNSS modelling additions are identified in docs/CONTRACT.md.
#include <cmath>
#include <cstdint>
#include <cstddef>
#ifdef __CUDACC__
#define SAT_HD __host__ __device__
#else
#define SAT_HD
#endif
namespace satnav {
constexpr int CHANNELS=32, FIELDS=6;
constexpr double LIGHT_MPS=299792458.0;
SAT_HD inline bool finite(double x) { return x==x && x<=1.7976931348623157e308 && x>=-1.7976931348623157e308; }
SAT_HD inline double absd(double x) { return x<0?-x:x; }
SAT_HD inline double maxd(double a,double b) { return a>b?a:b; }
SAT_HD inline int pop32(std::uint32_t x) {
#ifdef __CUDA_ARCH__
 return __popc(x);
#else
 int n=0;while(x){x&=x-1;++n;}return n;
#endif
}
struct WordResult {std::uint32_t asa,na,hits,output;};
SAT_HD inline WordResult asa_word(std::uint32_t x,std::uint32_t a,std::uint32_t n,std::uint32_t b,std::uint32_t v) {
 WordResult r{};r.asa=x&a&v;r.na=r.asa&n;r.hits=static_cast<std::uint32_t>(pop32(r.na&b));r.output=r.hits?0:r.na;return r;
}
SAT_HD inline int jk_bit(int q,int j,int k) {return (j&(q^1))|((k^1)&q);}
struct Epoch {
 std::uint64_t id{}; double t_gpst_s{}; double seed[4]{};
 std::uint32_t present{},ready{},asa_mask{0xffffffffu},na_mask{0xffffffffu},boundary_mask{};
};
struct Config {
 int max_iterations{12};double position_tolerance_m{1e-4},clock_tolerance_m{1e-4};
 double rank_relative_tolerance{1e-10};double max_normalized_residual{6.0};
};
enum Status : std::uint32_t { CONVERGED=0,MASK_ABSORBED=1,TOO_FEW=2,RANK_DEFICIENT=3,ITERATION_LIMIT=4,NUMERIC_FAILURE=5 };
enum Fit : std::uint32_t { NOT_EVALUATED=0,NO_REDUNDANCY=1,WITHIN_RESIDUAL_BUDGET=2,RESIDUAL_ALERT=3 };
struct Result {
 std::uint32_t status{NUMERIC_FAILURE},fit{NOT_EVALUATED},iterations{},used{};
 WordResult selection{}; double estimate[4]{}; // ECEF metres; clock bias in metres
 double variance[4]{}; // formal diagonal covariance, not measured error
 double rms_m{},weighted_sse{},max_normalized{};
 double residual[CHANNELS]{}; // zero outside active mask; consult active mask
};
struct GlobalReader {
 const double* data;std::size_t epochs;
 SAT_HD double get(std::size_t epoch,int channel,int field) const {
  return data[(static_cast<std::size_t>(channel)*FIELDS+field)*epochs+epoch];
 }
};
// Online Givens QR on the whitened 4-column Jacobian; no normal-equation solve.
struct QR4 {
 double r[4][4]{};double z[4]{};
 SAT_HD void append(double* a,double rhs) {
  for(int j=0;j<4;++j){
   const double radius=::hypot(r[j][j],a[j]);if(radius==0)continue;
   const double c=r[j][j]/radius,s=a[j]/radius;r[j][j]=radius;
   for(int k=j+1;k<4;++k){const double old=r[j][k];r[j][k]=c*old+s*a[k];a[k]=-s*old+c*a[k];}
   const double old=z[j];z[j]=c*old+s*rhs;rhs=-s*old+c*rhs;
  }
 }
 SAT_HD bool full_rank(double relative) const {
  double largest=0;for(int j=0;j<4;++j)largest=maxd(largest,absd(r[j][j]));
  if(!finite(largest)||largest==0)return false;
  for(int j=0;j<4;++j)if(!finite(r[j][j])||absd(r[j][j])<=relative*largest)return false;
  return true;
 }
 SAT_HD bool solve(double* out,double relative) const {
  if(!full_rank(relative))return false;
  for(int j=3;j>=0;--j){double v=z[j];for(int k=j+1;k<4;++k)v-=r[j][k]*out[k];out[j]=v/r[j][j];if(!finite(out[j]))return false;}
  return true;
 }
 SAT_HD bool covariance_diagonal(double* diag,double relative) const {
  if(!full_rank(relative))return false;
  double inverse[4][4]{};
  for(int col=0;col<4;++col)for(int row=3;row>=0;--row){
   double v=row==col?1.0:0.0;for(int k=row+1;k<4;++k)v-=r[row][k]*inverse[k][col];inverse[row][col]=v/r[row][row];
  }
  for(int row=0;row<4;++row){diag[row]=0;for(int col=0;col<4;++col)diag[row]+=inverse[row][col]*inverse[row][col];if(!finite(diag[row]))return false;}
  return true;
 }
};
template<class Reader> SAT_HD bool model_row(const Reader& reader,std::size_t e,int ch,const double* state,double* h,double& residual,double& sigma) {
 const double dx=state[0]-reader.get(e,ch,0),dy=state[1]-reader.get(e,ch,1),dz=state[2]-reader.get(e,ch,2);
 const double distance=::hypot(::hypot(dx,dy),dz);sigma=reader.get(e,ch,5);
 const double corrected=reader.get(e,ch,3)+reader.get(e,ch,4);
 if(!finite(distance)||distance<=1.0||!finite(sigma)||sigma<=0||!finite(corrected))return false;
 residual=corrected-(distance+state[3]);if(!finite(residual))return false;
 h[0]=dx/distance;h[1]=dy/distance;h[2]=dz/distance;h[3]=1.0;return true;
}
template<class Reader> SAT_HD Result solve_epoch(const Epoch& epoch,const Reader& reader,std::size_t index,const Config& cfg) {
 Result out{};for(int j=0;j<4;++j)out.estimate[j]=epoch.seed[j];
 out.selection=asa_word(epoch.ready,epoch.asa_mask,epoch.na_mask,epoch.boundary_mask,epoch.present);
 out.used=static_cast<std::uint32_t>(pop32(out.selection.output));
 if(out.selection.hits){out.status=MASK_ABSORBED;return out;}
 if(out.used<4){out.status=TOO_FEW;return out;}
 for(int it=0;it<cfg.max_iterations;++it){
  QR4 qr{};
  for(int ch=0;ch<CHANNELS;++ch)if(out.selection.output&(std::uint32_t(1)<<ch)){
   double a[4],r,sigma;if(!model_row(reader,index,ch,out.estimate,a,r,sigma)){out.status=NUMERIC_FAILURE;return out;}
   for(int j=0;j<4;++j){a[j]/=sigma;}
   qr.append(a,r/sigma);
  }
  double delta[4]{};if(!qr.solve(delta,cfg.rank_relative_tolerance)){out.status=RANK_DEFICIENT;return out;}
  for(int j=0;j<4;++j){out.estimate[j]+=delta[j];if(!finite(out.estimate[j])){out.status=NUMERIC_FAILURE;return out;}}
  out.iterations=static_cast<std::uint32_t>(it+1);
  if(::hypot(::hypot(delta[0],delta[1]),delta[2])<=cfg.position_tolerance_m&&absd(delta[3])<=cfg.clock_tolerance_m){out.status=CONVERGED;break;}
 }
 if(out.status!=CONVERGED){out.status=ITERATION_LIMIT;return out;}
 QR4 final_qr{};double sse=0;
 for(int ch=0;ch<CHANNELS;++ch)if(out.selection.output&(std::uint32_t(1)<<ch)){
  double a[4],r,sigma;if(!model_row(reader,index,ch,out.estimate,a,r,sigma)){out.status=NUMERIC_FAILURE;return out;}
  out.residual[ch]=r;sse+=r*r;out.weighted_sse+=(r/sigma)*(r/sigma);out.max_normalized=maxd(out.max_normalized,absd(r/sigma));
  for(int j=0;j<4;++j){a[j]/=sigma;}
  final_qr.append(a,0);
 }
 if(!final_qr.covariance_diagonal(out.variance,cfg.rank_relative_tolerance)){out.status=RANK_DEFICIENT;return out;}
 out.rms_m=::sqrt(sse/out.used);
 if(!finite(out.rms_m)||!finite(out.weighted_sse)){out.status=NUMERIC_FAILURE;return out;}
 out.fit=out.used==4?NO_REDUNDANCY:(out.max_normalized<=cfg.max_normalized_residual?WITHIN_RESIDUAL_BUDGET:RESIDUAL_ALERT);
 return out;
}
inline const char* status_name(std::uint32_t s){switch(s){case CONVERGED:return "CONVERGED";case MASK_ABSORBED:return "MASK_ABSORBED";case TOO_FEW:return "TOO_FEW";case RANK_DEFICIENT:return "RANK_DEFICIENT";case ITERATION_LIMIT:return "ITERATION_LIMIT";default:return "NUMERIC_FAILURE";}}
inline const char* fit_name(std::uint32_t s){switch(s){case NO_REDUNDANCY:return "NO_REDUNDANCY";case WITHIN_RESIDUAL_BUDGET:return "WITHIN_RESIDUAL_BUDGET";case RESIDUAL_ALERT:return "RESIDUAL_ALERT";default:return "NOT_EVALUATED";}}
} // namespace satnav
