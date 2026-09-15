#pragma once
// Declared R1/R2 perturbation dynamics and literal two-stage word state.
#include "self_reference.hpp"
#include <cstdint>

namespace orbit {
constexpr int MAX_DEGREE=32;
constexpr int GRAVITY_MAX_DEGREE=12;
enum Status : unsigned { OK=0, OUTSIDE_FORCING=1, NUMERIC_FAILURE=2, WORK_LIMIT=3 };
struct Segment { double t0{},t1{}; int degree{}; double coefficients[9][MAX_DEGREE+1]{}; };
struct Series { const Segment* segments{}; int count{},components{}; };
struct Model {
 double epoch_gpst{},epoch_jd_tt{},step{}; std::uint64_t checkpoint_stride{},max_checkpoints{},max_steps{};
 double initial[6]{},mu{},radius{},j2{},j3{},j4{},c22{},s22{},mu_sun{},mu_moon{},au{},srp{};
 unsigned shadow{}; double rtn[3]{},era0{},era_rate{},xp{},yp{};
 // Negative degree selects the original R1 equations. R2 coefficients are
 // unnormalized, without the Condon--Shortley phase, and include C00=1.
 int gravity_degree{-1};double gravity_c[13][13]{},gravity_s[13][13]{};
 unsigned relativity{};double speed_of_light{};
 Series q{},sun{},moon{},eop{};
};
struct Query { double time{},state[6]{}; std::uint64_t steps{}; unsigned status{}; };
struct Words {
 std::uint32_t q{},drive{},present{},a1{},n1{},b1{},a2{},n2{},b2{};
 std::uint8_t x_lut{},j_lut{},k_lut{};
};
struct WordTrace { std::uint32_t before{},drive{},x{},j{},k{},after{}; satnav::WordResult stage_a{},stage_b{}; };
SAT_HD inline WordTrace transition(const Words& w) {
 WordTrace t{};t.before=w.q;t.drive=w.drive;t.x=selfref::lut2(w.q,w.drive,w.x_lut);
 t.stage_a=satnav::asa_word(t.x,w.a1,w.n1,w.b1,w.present);
 t.stage_b=satnav::asa_word(t.stage_a.output,w.a2,w.n2,w.b2,w.present);
 t.j=selfref::lut3(w.q,t.stage_b.output,w.drive,w.j_lut);
 t.k=selfref::lut3(w.q,t.stage_b.output,w.drive,w.k_lut);
 t.after=((t.j&~w.q)|(~t.k&w.q))&w.present;return t;
}
SAT_HD inline double norm(const double* r) {return ::sqrt(r[0]*r[0]+r[1]*r[1]+r[2]*r[2]);}
SAT_HD inline double dot(const double* a,const double* b) {return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
SAT_HD inline void cross(const double* a,const double* b,double* c) {c[0]=a[1]*b[2]-a[2]*b[1];c[1]=a[2]*b[0]-a[0]*b[2];c[2]=a[0]*b[1]-a[1]*b[0];}
SAT_HD inline bool finite(const double* a,int n) {for(int i=0;i<n;++i)if(!satnav::finite(a[i]))return false;return true;}
SAT_HD inline bool evaluate(const Series& s,double t,double* result) {
 if(!s.count)return false;
 int lo=0,hi=s.count;
 while(lo+1<hi){const int mid=(lo+hi)/2;if(s.segments[mid].t0<=t)lo=mid;else hi=mid;}
 const Segment& p=s.segments[lo];if(t<p.t0||t>p.t1)return false;
 const double x=2*(t-p.t0)/(p.t1-p.t0)-1;
 for(int c=0;c<s.components;++c){double b1=0,b2=0;for(int k=p.degree;k>=1;--k){const double b=2*x*b1-b2+p.coefficients[c][k];b2=b1;b1=b;}result[c]=x*b1-b2+p.coefficients[c][0];}
 return finite(result,s.components);
}
// ERFA convention: passive Rz(ERA), polar P=Rx(-yp)*Ry(-xp).
SAT_HD inline bool frame(const Model& m,double t,double* result) {
 double q[9];if(!evaluate(m.q,t,q))return false;
 double correction=0,xp=m.xp,yp=m.yp;
 if(m.gravity_degree>=0){double eop[3];if(!evaluate(m.eop,t,eop))return false;correction=eop[0];xp=eop[1];yp=eop[2];}
 const double angle=m.era0+m.era_rate*t+correction,c=::cos(angle),s=::sin(angle),cx=::cos(xp),sx=::sin(xp),cy=::cos(yp),sy=::sin(yp);
 for(int col=0;col<3;++col){const double a=c*q[col]+s*q[3+col],b=-s*q[col]+c*q[3+col],z=q[6+col];
  const double u=cx*a+sx*z,w=-sx*a+cx*z;
  result[col]=u;result[3+col]=cy*b-sy*w;result[6+col]=sy*b+cy*w;}
 return finite(result,9);
}
// Forward analytic derivatives through nonsingular Cartesian solid harmonics.
// Streaming each order retains only the diagonal and two preceding degrees.
// This avoids a per-thread 13x13 array of four-component dual values on CUDA.
struct Dual3 {double v{},x{},y{},z{};};
SAT_HD inline Dual3 operator+(Dual3 a,Dual3 b){return {a.v+b.v,a.x+b.x,a.y+b.y,a.z+b.z};}
SAT_HD inline Dual3 operator-(Dual3 a,Dual3 b){return {a.v-b.v,a.x-b.x,a.y-b.y,a.z-b.z};}
SAT_HD inline Dual3 operator*(Dual3 a,Dual3 b){return {a.v*b.v,a.x*b.v+a.v*b.x,a.y*b.v+a.v*b.y,a.z*b.v+a.v*b.z};}
SAT_HD inline Dual3 operator*(double a,Dual3 b){return {a*b.v,a*b.x,a*b.y,a*b.z};}
SAT_HD inline void add_harmonic(const Model& m,int n,int order,Dual3 v,Dual3 w,double* a){
 const double c=m.gravity_c[n][order],s=m.gravity_s[n][order];a[0]+=c*v.x+s*w.x;a[1]+=c*v.y+s*w.y;a[2]+=c*v.z+s*w.z;
}
SAT_HD inline void harmonic_gravity(const Model& m,const double* r,double* a){
 const Dual3 x{r[0],1,0,0},y{r[1],0,1,0},z{r[2],0,0,1};
 const Dual3 r2=x*x+y*y+z*z;const double inverse=1/r2.v,di=-inverse*inverse;
 const Dual3 inv{inverse,di*r2.x,di*r2.y,di*r2.z};
 const double ri=::sqrt(inverse),dr=-.5*ri*inverse;
 const Dual3 invr{ri,dr*r2.x,dr*r2.y,dr*r2.z};
 const Dual3 xf=m.radius*(x*inv),yf=m.radius*(y*inv),zf=m.radius*(z*inv),rf=(m.radius*m.radius)*inv;
 Dual3 vd=m.radius*invr,wd{};a[0]=a[1]=a[2]=0;
 for(int order=0;order<=m.gravity_degree;++order){
  if(order){const Dual3 nextv=(2.*order-1)*(xf*vd-yf*wd),nextw=(2.*order-1)*(xf*wd+yf*vd);vd=nextv;wd=nextw;}
  add_harmonic(m,order,order,vd,wd,a);
  if(order==m.gravity_degree)continue;
  Dual3 v2=vd,w2=wd,v1=(2.*order+1)*(zf*vd),w1=(2.*order+1)*(zf*wd);
  add_harmonic(m,order+1,order,v1,w1,a);
  for(int n=order+2;n<=m.gravity_degree;++n){
   const Dual3 v=((2.*n-1)/(n-order))*(zf*v1)-((n+order-1.)/(n-order))*(rf*v2);
   const Dual3 w=((2.*n-1)/(n-order))*(zf*w1)-((n+order-1.)/(n-order))*(rf*w2);
   add_harmonic(m,n,order,v,w,a);v2=v1;v1=v;w2=w1;w1=w;
  }
 }
 for(int i=0;i<3;++i)a[i]*=m.mu/m.radius;
}
SAT_HD inline unsigned acceleration(const Model& m,double t,const double* state,double* out) {
 double rot[9],r[3];if(!frame(m,t,rot))return OUTSIDE_FORCING;
 for(int i=0;i<3;++i){r[i]=0;for(int j=0;j<3;++j)r[i]+=rot[3*i+j]*state[j];}
 const double d=norm(r);if(!(d>0)||!satnav::finite(d))return NUMERIC_FAILURE;
 double a[3];if(m.gravity_degree>=0)harmonic_gravity(m,r,a);else {
 const double s=r[2]/d,s2=s*s,re=m.radius/d,base=m.mu/(d*d*d);
 for(int i=0;i<3;++i)a[i]=-base*r[i];
 const double js[3]={m.j2,m.j3,m.j4};
 const double ps[3]={(3*s2-1)/2,(5*s*s2-3*s)/2,(35*s2*s2-30*s2+3)/8};
 const double ds[3]={3*s,(15*s2-3)/2,(140*s*s2-60*s)/8};
 double power=re*re;
 for(int n=2;n<=4;++n){const double k=base*js[n-2]*power,v=(n+1)*ps[n-2]+s*ds[n-2];for(int i=0;i<3;++i)a[i]+=k*v*r[i];a[2]-=k*d*ds[n-2];power*=re;}
 const double f=3*m.c22*(r[0]*r[0]-r[1]*r[1])+6*m.s22*r[0]*r[1],k=base*re*re;
 const double grad[3]={6*m.c22*r[0]+6*m.s22*r[1],-6*m.c22*r[1]+6*m.s22*r[0],0};
 for(int i=0;i<3;++i)a[i]+=k*(grad[i]-5*f*r[i]/(d*d));
 }
 for(int i=0;i<3;++i){out[i]=0;for(int j=0;j<3;++j)out[i]+=rot[3*j+i]*a[j];}
 double sun[3]{};
 for(int b=0;b<2;++b){const double mu=b?m.mu_moon:m.mu_sun;if(mu==0&&!(b==0&&m.srp!=0))continue;
  double body[3],delta[3];if(!evaluate(b?m.moon:m.sun,t,body))return OUTSIDE_FORCING;
  if(b==0)for(int j=0;j<3;++j)sun[j]=body[j];
  for(int j=0;j<3;++j)delta[j]=body[j]-state[j];const double db=norm(body),dd=norm(delta);
  if(!(db>0&&dd>0))return NUMERIC_FAILURE;
  for(int j=0;j<3;++j)out[j]+=mu*(delta[j]/(dd*dd*dd)-body[j]/(db*db*db));}
 if(m.srp!=0){const double ns=norm(sun);if(!(ns>0))return NUMERIC_FAILURE;
  const double projection=dot(state,sun)/ns;double perpendicular[3],away[3];
  for(int i=0;i<3;++i){perpendicular[i]=state[i]-projection*sun[i]/ns;away[i]=state[i]-sun[i];}
  const bool shadow=m.shadow&&projection<0&&norm(perpendicular)<m.radius;const double distance=norm(away);
  if(!(distance>0))return NUMERIC_FAILURE;if(!shadow){const double factor=m.srp*(m.au/distance)*(m.au/distance)/distance;for(int i=0;i<3;++i)out[i]+=factor*away[i];}}
 if(m.rtn[0]!=0||m.rtn[1]!=0||m.rtn[2]!=0){double radial[3],normal[3],tangent[3];const double nr=norm(state);cross(state,state+3,normal);const double nn=norm(normal);
  if(!(nr>0&&nn>0))return NUMERIC_FAILURE;for(int i=0;i<3;++i){radial[i]=state[i]/nr;normal[i]/=nn;}cross(normal,radial,tangent);
  for(int i=0;i<3;++i)out[i]+=m.rtn[0]*radial[i]+m.rtn[1]*tangent[i]+m.rtn[2]*normal[i];}
 if(m.relativity){const double nr=norm(state),vv=dot(state+3,state+3),rv=dot(state,state+3),factor=m.mu/(m.speed_of_light*m.speed_of_light*nr*nr*nr);
  for(int i=0;i<3;++i)out[i]+=factor*((4*m.mu/nr-vv)*state[i]+4*rv*state[i+3]);}
 return finite(out,3)?OK:NUMERIC_FAILURE;
}
SAT_HD inline unsigned derivative(const Model& m,double t,const double* state,double* out) {
 for(int i=0;i<3;++i)out[i]=state[i+3];return acceleration(m,t,state,out+3);
}
SAT_HD inline unsigned rk4(const Model& m,double t,double h,double* state) {
 double k1[6],k2[6],k3[6],k4[6],temp[6];unsigned status=derivative(m,t,state,k1);if(status)return status;
 for(int i=0;i<6;++i)temp[i]=state[i]+h*k1[i]/2;status=derivative(m,t+h/2,temp,k2);if(status)return status;
 for(int i=0;i<6;++i)temp[i]=state[i]+h*k2[i]/2;status=derivative(m,t+h/2,temp,k3);if(status)return status;
 for(int i=0;i<6;++i)temp[i]=state[i]+h*k3[i];status=derivative(m,t+h,temp,k4);if(status)return status;
 for(int i=0;i<6;++i)temp[i]=state[i]+(h/6)*(k1[i]+2*k2[i]+2*k3[i]+k4[i]);
 if(!finite(temp,6))return NUMERIC_FAILURE;
 for(int i=0;i<6;++i)state[i]=temp[i];return OK;
}
SAT_HD inline Query from_epoch(const Model& m,double t) {
 Query q{};q.time=t;for(int i=0;i<6;++i)q.state[i]=m.initial[i];
 if(!satnav::finite(t)||::fabs(t/m.step)>static_cast<double>(m.max_steps)){q.status=WORK_LIMIT;return q;}
 const long long target=static_cast<long long>(t/m.step),direction=target<0?-1:1;
 for(long long n=0;n!=target;n+=direction){q.status=rk4(m,n*m.step,direction*m.step,q.state);++q.steps;if(q.status)return q;}
 const double remainder=t-target*m.step;if(remainder!=0){q.status=rk4(m,target*m.step,remainder,q.state);++q.steps;}return q;
}
} // namespace orbit
