#pragma once
// CGK-R1 / 3.6.1.7. Executable geometry -> ASA/NA + JK -> mechanics -> geometry.
#include "satnav_core.hpp"
#include <cstdint>

namespace coupled {
constexpr double PI=3.141592653589793238462643383279502884;
enum Chart : unsigned { CHART_DEFINED=0, ORIGIN_CORE=1, CHART_NOT_EVALUATED=2 };
enum Otan : unsigned { OTAN_DEFINED=0,FIRST_OBSERVATION=1,OTAN_ORIGIN_CORE=2,ZERO_INCREMENT=3,RATIO_UNDEFINED=4,NUMERICAL_RANGE=5,OTAN_NOT_EVALUATED=6 };
enum Status : unsigned { ADVANCED=0,NUMERIC_FAILURE=1,PREVIOUS_FAILURE=2 };
struct Table { std::uint64_t words[4]{}; };
struct Channel {
 double u[3]{},k_off{},k_on{},force_off{},force_on{},angle_center{},angle_tolerance{},error_limit{},fringe_width{};
 unsigned support_kind{}; double center[3]{},extent{},axis[3]{},angle{};
};
struct Job {
 std::uint64_t id{},offset{},steps{};
 std::uint32_t q0{},present{},asa_mask{},na_mask{},boundary_mask{};
 double initial_time{},p0[3]{},v0[3]{},mass[3]{},damping[3]{},base[9]{},r0{},core{},blend_weight{},axis{},hoop0{},hoop_rate{};
 Channel channels[32]{}; Table drive_lut{},x_lut{},j_lut{},k_lut{};
};
struct Sample {
 std::uint64_t epoch_id{}; double time{}; unsigned valid{};
 double target[3]{},observed_ecef[3]{},clock_bias_m{},force[3]{};
};
struct State {
 double p[3]{},v[3]{},phi{},time{},previous_rho{},previous_theta{};
 std::uint32_t q{}; bool has_previous{},previous_chart_defined{},failed{};
};
struct Step {
 double time_before{},time_after{},dt{},p_before[3]{},v_before[3]{},phi_before{},rho{},theta{},otan{},bearing{},blend{};
 unsigned chart_status{},otan_status{},blend_defined{};
 std::uint32_t q_before{},alignment{},limit{},fringe{},support{},drive{},x{},asa{},na{},hits{},output{},j{},k{},q_after{};
 double stiffness[9]{},eigenmatrix[9]{},eigenvalues[3]{},eigenvectors[9]{},eigen_residual{},force[3]{},mechanical_matrix[9]{},mechanical_rhs[3]{},p_after[3]{},v_after[3]{},phi_after{};
 unsigned status{};
};
SAT_HD inline double wrap(double a) {
 double r=::fmod(a,2*PI); if(r>=PI)r-=2*PI; if(r< -PI)r+=2*PI; return r==0?0:r;
}
SAT_HD inline double circle_plus(double a,double b,double weight){return wrap(a+weight*wrap(b-a));}
SAT_HD inline double dot3(const double* a,const double* b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
SAT_HD inline double norm3(const double* a) { return ::hypot(::hypot(a[0],a[1]),a[2]); }
SAT_HD inline bool finite_array(const double* a,int n) {for(int i=0;i<n;++i)if(!satnav::finite(a[i]))return false;return true;}
SAT_HD inline double segment_distance(double x,double y,double ax,double ay,double bx,double by) {
 const double dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy;
 double t=den==0?0:((x-ax)*dx+(y-ay)*dy)/den; if(t<0)t=0;if(t>1)t=1;
 return ::hypot(x-ax-t*dx,y-ay-t*dy);
}
SAT_HD inline double support_sdf(const double* point,const Channel& c) {
 double v[3];for(int i=0;i<3;++i)v[i]=point[i]-c.center[i];
 if(c.support_kind==0)return norm3(v)-c.extent;
 const double z=dot3(v,c.axis);double radial[3];for(int i=0;i<3;++i)radial[i]=v[i]-z*c.axis[i];
 const double q=norm3(radial),h=c.extent*::cos(c.angle),radius=c.extent*::sin(c.angle);
 double distance=segment_distance(q,z,-radius,h,radius,h);
 double side=segment_distance(q,z,radius,h,0,0);if(side<distance)distance=side;
 side=segment_distance(q,z,0,0,-radius,h);if(side<distance)distance=side;
 return z>=0&&z<=h&&q<=z*::tan(c.angle)?-distance:distance;
}
// First variable is the most significant table-index bit. Each bit is evaluated
// independently; ASA absorption below is intentionally a whole-word operation.
SAT_HD inline std::uint32_t evaluate(const Table& table,const std::uint32_t* inputs,unsigned count) {
 std::uint32_t word=0;
 for(unsigned bit=0;bit<32;++bit) {
  unsigned index=0;for(unsigned v=0;v<count;++v)index=(index<<1)|((inputs[v]>>bit)&1u);
  word|=static_cast<std::uint32_t>((table.words[index/64]>>(index%64))&1ull)<<bit;
 }
 return word;
}
SAT_HD inline State initial_state(const Job& job) {
 State s{};s.q=job.q0;s.phi=wrap(job.hoop0);s.time=job.initial_time;
 for(int i=0;i<3;++i){s.p[i]=job.p0[i];s.v[i]=job.v0[i];}return s;
}
// Partial pivoting uses an exact zero singularity condition; signed/near-singular
// systems are not replaced by a hold, clamped, or changed to positive matrices.
SAT_HD inline bool solve3(const double* matrix,const double* rhs,double* solution) {
 if(!finite_array(matrix,9)||!finite_array(rhs,3))return false;
 double a[3][4];for(int i=0;i<3;++i){for(int j=0;j<3;++j)a[i][j]=matrix[3*i+j];a[i][3]=rhs[i];}
 for(int col=0;col<3;++col) {
  int pivot=col;for(int row=col+1;row<3;++row)if(satnav::absd(a[row][col])>satnav::absd(a[pivot][col]))pivot=row;
  if(a[pivot][col]==0||!satnav::finite(a[pivot][col]))return false;
  if(pivot!=col)for(int j=col;j<4;++j){const double t=a[col][j];a[col][j]=a[pivot][j];a[pivot][j]=t;}
  for(int row=col+1;row<3;++row) {
   const double factor=a[row][col]/a[col][col];a[row][col]=0;
   for(int j=col+1;j<4;++j)a[row][j]-=factor*a[col][j];
  }
 }
 for(int row=2;row>=0;--row) {
  double value=a[row][3];for(int col=row+1;col<3;++col)value-=a[row][col]*solution[col];
  if(a[row][row]==0)return false;solution[row]=value/a[row][row];if(!satnav::finite(solution[row]))return false;
 }
 return true;
}
// Symmetric Jacobi eigensystem, scaled to avoid squaring large matrix entries.
// Residual is max_ij |(D V - V diag(lambda))_ij| in inverse-seconds squared.
SAT_HD inline bool eigensystem(const double* matrix,double* values,double* vectors,double& residual) {
 if(!finite_array(matrix,9))return false;
 double scale=0;for(int i=0;i<9;++i)scale=satnav::maxd(scale,satnav::absd(matrix[i]));
 double a[9];for(int i=0;i<9;++i){a[i]=scale==0?0:matrix[i]/scale;vectors[i]=(i%4==0)?1:0;}
 bool converged=scale==0;
 for(int iteration=0;iteration<64&&!converged;++iteration) {
  int p=0,q=1;double off=0;
  // A global cutoff can erase low-frequency modes in a small independent block.
  // Judge each pair against its own two diagonal magnitudes instead.
  for(int row=0;row<2;++row)for(int col=row+1;col<3;++col) {
   const double candidate=satnav::absd(a[3*row+col]);
   const double threshold=2e-15*::sqrt(satnav::absd(a[3*row+row]))*::sqrt(satnav::absd(a[3*col+col]));
   if(candidate>threshold&&candidate>off){p=row;q=col;off=candidate;}
  }
  if(off==0){converged=true;break;}
  const double app=a[3*p+p],aqq=a[3*q+q],apq=a[3*p+q];
  const double delta=(aqq-app)/2;
  const double t=delta==0?(apq<0?-1.:1.):apq/(delta+(delta<0?-1.:1.)*::hypot(delta,apq));
  const double c=1/::sqrt(1+t*t),s=t*c;
  a[3*p+p]=app-t*apq;
  a[3*q+q]=aqq+t*apq;a[3*p+q]=a[3*q+p]=0;
  for(int k=0;k<3;++k)if(k!=p&&k!=q) {
   const double akp=a[3*k+p],akq=a[3*k+q];a[3*k+p]=a[3*p+k]=c*akp-s*akq;a[3*k+q]=a[3*q+k]=s*akp+c*akq;
  }
  for(int k=0;k<3;++k){const double vp=vectors[3*k+p],vq=vectors[3*k+q];vectors[3*k+p]=c*vp-s*vq;vectors[3*k+q]=s*vp+c*vq;}
 }
 if(!converged)return false;
 for(int i=0;i<3;++i)values[i]=a[3*i+i]*scale;
 for(int i=0;i<2;++i)for(int j=i+1;j<3;++j)if(values[j]<values[i]) {
  double t=values[i];values[i]=values[j];values[j]=t;
  for(int k=0;k<3;++k){t=vectors[3*k+i];vectors[3*k+i]=vectors[3*k+j];vectors[3*k+j]=t;}
 }
 residual=0;for(int i=0;i<3;++i)for(int j=0;j<3;++j) {
  double value=0;for(int k=0;k<3;++k)value+=matrix[3*i+k]*vectors[3*k+j];
  const double component=satnav::absd(value-vectors[3*i+j]*values[j]);
  if(!satnav::finite(component))return false;residual=satnav::maxd(residual,component);
 }
 return finite_array(values,3)&&finite_array(vectors,9)&&satnav::finite(residual);
}
SAT_HD inline Step transition(const Job& job,const Sample& sample,State& state) {
 Step r{};r.time_before=state.time;r.time_after=sample.time;r.dt=sample.time-state.time;
 r.q_before=r.q_after=state.q;r.phi_before=r.phi_after=state.phi;
 for(int i=0;i<3;++i){r.p_before[i]=r.p_after[i]=state.p[i];r.v_before[i]=r.v_after[i]=state.v[i];}
 if(state.failed){r.status=PREVIOUS_FAILURE;r.chart_status=CHART_NOT_EVALUATED;r.otan_status=OTAN_NOT_EVALUATED;return r;}
 const double radius=::hypot(state.p[0],state.p[1]);
 r.chart_status=radius>=job.core?CHART_DEFINED:ORIGIN_CORE;
 if(r.chart_status==CHART_DEFINED){r.rho=::log(radius/job.r0);r.theta=::atan2(state.p[1],state.p[0]);}
 if(!state.has_previous)r.otan_status=FIRST_OBSERVATION;
 else if(r.chart_status!=CHART_DEFINED||!state.previous_chart_defined)r.otan_status=OTAN_ORIGIN_CORE;
 else {
  const double dtheta=wrap(r.theta-state.previous_theta),drho=r.rho-state.previous_rho;
  if(dtheta==0&&drho==0)r.otan_status=ZERO_INCREMENT;
  else if(drho==0)r.otan_status=RATIO_UNDEFINED;
  else {
   const double ratio=dtheta/drho;
   if(!satnav::finite(ratio)||(ratio==0&&dtheta!=0))r.otan_status=NUMERICAL_RANGE;
   else {r.otan=::atan(ratio)-job.axis;r.otan_status=OTAN_DEFINED;}
  }
 }
 double error[3];for(int i=0;i<3;++i)error[i]=sample.target[i]-state.p[i];
 const bool bearing_defined=sample.valid&&::hypot(error[0],error[1])>=job.core;
 if(bearing_defined)r.bearing=::atan2(error[1],error[0]);
 r.blend_defined=bearing_defined&&r.otan_status==OTAN_DEFINED;
 if(r.blend_defined)r.blend=wrap(circle_plus(r.bearing,r.otan,job.blend_weight)+state.phi);
 bool numeric_ok=finite_array(error,3)&&satnav::finite(radius)&&satnav::finite(r.rho)&&satnav::finite(r.otan)&&satnav::finite(r.blend);
 for(unsigned i=0;i<32;++i)if(job.present&(std::uint32_t(1)<<i)) {
  const Channel& c=job.channels[i];const auto bit=std::uint32_t(1)<<i;
  const double sdf=support_sdf(state.p,c),projection=dot3(c.u,error);
  if(r.blend_defined&&satnav::absd(wrap(r.blend-c.angle_center))<=c.angle_tolerance)r.alignment|=bit;
  if(sample.valid&&satnav::absd(projection)>c.error_limit)r.limit|=bit;
  if(satnav::absd(sdf)<=c.fringe_width)r.fringe|=bit;
  if(sdf<=0)r.support|=bit;
  numeric_ok=numeric_ok&&satnav::finite(sdf)&&satnav::finite(projection);
 }
 const std::uint32_t valid=sample.valid?0xffffffffu:0;
 const std::uint32_t dvars[6]={state.q,r.alignment,r.limit,r.fringe,r.support,valid};r.drive=evaluate(job.drive_lut,dvars,6);
 const std::uint32_t xvars[7]={state.q,r.drive,r.alignment,r.limit,r.fringe,r.support,valid};r.x=evaluate(job.x_lut,xvars,7);
 const satnav::WordResult word=satnav::asa_word(r.x,job.asa_mask,job.na_mask,job.boundary_mask,job.present);
 r.asa=word.asa;r.na=word.na;r.hits=word.hits;r.output=word.output;
 const std::uint32_t jkvars[8]={state.q,r.output,r.drive,r.alignment,r.limit,r.fringe,r.support,valid};
 r.j=evaluate(job.j_lut,jkvars,8);r.k=evaluate(job.k_lut,jkvars,8);
 r.q_after=((r.j&~state.q)|(~r.k&state.q))&job.present;
 for(int i=0;i<9;++i)r.stiffness[i]=job.base[i];for(int i=0;i<3;++i)r.force[i]=sample.force[i];
 for(unsigned i=0;i<32;++i)if(job.present&(std::uint32_t(1)<<i)) {
  const Channel& c=job.channels[i];const bool on=(r.q_after&(std::uint32_t(1)<<i))!=0;
  const double stiffness=on?c.k_on:c.k_off,force=on?c.force_on:c.force_off;
  for(int row=0;row<3;++row){r.force[row]+=force*c.u[row];for(int col=row;col<3;++col){r.stiffness[3*row+col]+=stiffness*(c.u[row]*c.u[col]);r.stiffness[3*col+row]=r.stiffness[3*row+col];}}
 }
 for(int row=0;row<3;++row)for(int col=row;col<3;++col){r.eigenmatrix[3*row+col]=r.stiffness[3*row+col]/::sqrt(job.mass[row])/::sqrt(job.mass[col]);r.eigenmatrix[3*col+row]=r.eigenmatrix[3*row+col];}
 for(int row=0;row<3;++row) {
  double spring=0;
  for(int col=0;col<3;++col) {
   const int index=3*row+col;
   r.mechanical_matrix[index]=sample.valid?r.dt*r.dt*r.stiffness[index]:0;
   if(sample.valid)spring+=r.stiffness[index]*error[col];
  }
  r.mechanical_matrix[3*row+row]+=job.mass[row]+r.dt*job.damping[row];
  r.mechanical_rhs[row]=job.mass[row]*state.v[row]+r.dt*(r.force[row]+spring);
 }
 numeric_ok=numeric_ok&&finite_array(r.stiffness,9)&&finite_array(r.force,3);
 const bool eigen_ok=eigensystem(r.eigenmatrix,r.eigenvalues,r.eigenvectors,r.eigen_residual);
 double velocity[3]{};const bool solved=solve3(r.mechanical_matrix,r.mechanical_rhs,velocity);
 double position[3];for(int i=0;i<3;++i)position[i]=state.p[i]+r.dt*velocity[i];
 const double phase=wrap(state.phi+r.dt*job.hoop_rate);
 numeric_ok=numeric_ok&&eigen_ok&&solved&&r.dt>0&&satnav::finite(r.dt)&&finite_array(position,3)&&satnav::finite(phase);
 state.q=r.q_after;
 if(!numeric_ok){state.failed=true;r.status=NUMERIC_FAILURE;return r;}
 for(int i=0;i<3;++i){state.p[i]=r.p_after[i]=position[i];state.v[i]=r.v_after[i]=velocity[i];}
 state.phi=r.phi_after=phase;state.time=sample.time;
 state.previous_rho=r.rho;state.previous_theta=r.theta;state.previous_chart_defined=r.chart_status==CHART_DEFINED;state.has_previous=true;
 r.status=ADVANCED;return r;
}
inline const char* chart_name(unsigned s){return s==CHART_DEFINED?"defined":s==ORIGIN_CORE?"origin_core":"not_evaluated";}
inline const char* otan_name(unsigned s){switch(s){case OTAN_DEFINED:return "defined";case FIRST_OBSERVATION:return "first_observation";case OTAN_ORIGIN_CORE:return "origin_core";case ZERO_INCREMENT:return "zero_increment";case RATIO_UNDEFINED:return "ratio_undefined";case OTAN_NOT_EVALUATED:return "not_evaluated";default:return "numerical_range";}}
inline const char* status_name(unsigned s){return s==ADVANCED?"advanced":s==NUMERIC_FAILURE?"numeric_failure":"previous_failure";}
} // namespace coupled
