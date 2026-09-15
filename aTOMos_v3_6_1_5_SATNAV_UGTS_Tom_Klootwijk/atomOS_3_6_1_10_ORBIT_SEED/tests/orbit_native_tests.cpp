#include "orbit_core.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <random>
#include <stdexcept>
namespace {
void require(bool yes,const char* message){if(!yes)throw std::runtime_error(message);}
orbit::Model basic(orbit::Segment& q){q.t0=-1e7;q.t1=1e7;q.degree=0;q.coefficients[0][0]=q.coefficients[4][0]=q.coefficients[8][0]=1;orbit::Model m{};m.q={&q,1,9};m.mu=3.986004418e14;m.radius=6378136.3;m.au=149597870700.;m.step=10;m.max_steps=1000000;return m;}
double potential(const orbit::Model& m,const double* r){const double d=orbit::norm(r),s=r[2]/d,re=m.radius/d;const double p2=(3*s*s-1)/2,p3=(5*s*s*s-3*s)/2,p4=(35*s*s*s*s-30*s*s+3)/8;return m.mu/d*(1-m.j2*re*re*p2-m.j3*re*re*re*p3-m.j4*re*re*re*re*p4)+m.mu*m.radius*m.radius*(3*m.c22*(r[0]*r[0]-r[1]*r[1])+6*m.s22*r[0]*r[1])/std::pow(d,5);}
std::uint32_t independent_lut(std::uint32_t q,std::uint32_t y,std::uint32_t d,unsigned lut,bool three){std::uint32_t result=0;for(unsigned bit=0;bit<32;++bit){const unsigned qb=(q>>bit)&1,yb=(y>>bit)&1,db=(d>>bit)&1,index=three?4*qb+2*yb+db:2*qb+db;if((lut>>index)&1)result|=std::uint32_t(1)<<bit;}return result;}
void words(){std::mt19937 random(3619);for(unsigned i=0;i<4000;++i){orbit::Words w{};w.present=random();w.q=random()&w.present;w.drive=random();w.a1=random();w.n1=random();w.b1=i%2?0:random();w.a2=random();w.n2=random();w.b2=i%3?0:random();w.x_lut=static_cast<std::uint8_t>(random()&15);w.j_lut=static_cast<std::uint8_t>(random());w.k_lut=static_cast<std::uint8_t>(random());const auto r=orbit::transition(w);const auto x=independent_lut(w.q,0,w.drive,w.x_lut,false),a=x&w.a1&w.present,an=a&w.n1,ay=(an&w.b1)?0:an,b=ay&w.a2&w.present,bn=b&w.n2,y=(bn&w.b2)?0:bn,j=independent_lut(w.q,y,w.drive,w.j_lut,true),k=independent_lut(w.q,y,w.drive,w.k_lut,true),next=((j&~w.q)|(~k&w.q))&w.present;require(r.x==x&&r.stage_a.asa==a&&r.stage_a.na==an&&r.stage_a.output==ay&&r.stage_b.asa==b&&r.stage_b.na==bn&&r.stage_b.output==y&&r.j==j&&r.k==k&&r.after==next,"two-stage word recurrence");}
 orbit::Words w{};w.present=w.drive=w.a1=w.n1=w.a2=w.n2=15;w.b2=8;w.x_lut=14;w.j_lut=204;const auto r=orbit::transition(w);require(r.stage_a.output==15&&r.stage_b.output==0&&r.stage_b.hits==1&&r.after==0,"stage B must absorb whole word");}
void dynamics(){orbit::Segment q{};auto m=basic(q);const double a=26560000.,speed=std::sqrt(m.mu/a),rate=speed/a;m.initial[0]=a;m.initial[4]=speed;
 for(double t:{0.,-12345.678,12345.678,43200.}){const auto y=orbit::from_epoch(m,t);require(y.status==orbit::OK,"two-body propagation status");const double exact[6]={a*std::cos(rate*t),a*std::sin(rate*t),0,-speed*std::sin(rate*t),speed*std::cos(rate*t),0};for(int i=0;i<3;++i)require(std::abs(y.state[i]-exact[i])<.002,"circular Kepler position oracle");for(int i=3;i<6;++i)require(std::abs(y.state[i]-exact[i])<1e-6,"circular Kepler velocity oracle");}
 m.j2=.00108262668;m.j3=-2.532656e-6;m.j4=-1.61962e-6;m.c22=1.574e-6;m.s22=-.903e-6;double state[6]={18000000.,-21000000.,17000000.,1000.,3000.,-700.},acc[3];require(orbit::acceleration(m,0,state,acc)==0,"harmonic force status");for(int i=0;i<3;++i){double p[3]={state[0],state[1],state[2]},n[3]={state[0],state[1],state[2]};p[i]+=2;n[i]-=2;const double derivative=(potential(m,p)-potential(m,n))/4;require(std::abs(derivative-acc[i])<2e-9,"harmonic force potential gradient");}
 m.xp=.012;m.yp=-.023;m.era0=.47;m.era_rate=.00007292115;double rot[9];require(orbit::frame(m,42,rot),"frame status");const double xp=m.xp,yp=m.yp,cx=std::cos(xp),sx=std::sin(xp),cy=std::cos(yp),sy=std::sin(yp),angle=m.era0+m.era_rate*42,c=std::cos(angle),s=std::sin(angle);const double p[9]={cx,0,sx,sy*sx,cy,-sy*cx,-cy*sx,sy,cy*cx},r[9]={c,s,0,-s,c,0,0,0,1};for(int i=0;i<3;++i)for(int j=0;j<3;++j){double value=0;for(int k=0;k<3;++k)value+=p[3*i+k]*r[3*k+j];require(std::abs(value-rot[3*i+j])<1e-15,"polar and ERA multiplication");}
 require(orbit::from_epoch(m,2e7).status==orbit::WORK_LIMIT,"query work domain");double outside[3];require(orbit::acceleration(m,2e7,state,outside)==orbit::OUTSIDE_FORCING,"forcing domain status");}
void chebyshev(){orbit::Segment p{};p.t0=-4;p.t1=6;p.degree=3;for(int k=0;k<4;++k)p.coefficients[0][k]=k+1;orbit::Series s{&p,1,1};for(double t:{-4.,-3.75,0.,5.1,6.}){double actual{};require(orbit::evaluate(s,t,&actual),"Chebyshev evaluation");const double x=2*(t+4)/10-1,expected=1+2*x+3*(2*x*x-1)+4*(4*x*x*x-3*x);require(std::abs(actual-expected)<3e-14,"Chebyshev polynomial oracle");}double v;require(!orbit::evaluate(s,6.01,&v),"Chebyshev extrapolation status");}
void admission(){
 orbit::Segment q{};auto m=basic(q);m.initial[0]=26560000.;m.initial[4]=std::sqrt(m.mu/m.initial[0]);
 m.domain_declared=1;m.domain_start=-1.25;m.domain_end=2.5;m.step=.1;
 for(double t:{m.domain_start,0.,m.domain_end})require(orbit::from_epoch(m,t).status==orbit::OK,"closed domain endpoints admit fractional lattice steps");
 for(double t:{std::nextafter(m.domain_start,-INFINITY),std::nextafter(m.domain_end,INFINITY)}){const auto out=orbit::from_epoch(m,t);require(out.status==orbit::OUTSIDE_DOMAIN&&out.steps==0,"one ULP beyond explicit domain rejected before work");}
 m.initial[0]=m.radius+1;m.initial[3]=-1000;m.initial[4]=0;m.step=.01;
 const auto crossing=orbit::from_epoch(m,.01);require(crossing.status==orbit::INSIDE_REFERENCE_EARTH,"RK4 intermediate cannot propagate through reference Earth");
 for(int i=0;i<6;++i)require(crossing.state[i]==m.initial[i],"failed physical step preserves last accepted state");
 require(orbit::from_epoch(m,-.01).status==orbit::OK,"opposite time direction remains valid after failed impact query");
 m.initial[0]=m.radius;require(orbit::from_epoch(m,0).status==orbit::INSIDE_REFERENCE_EARTH,"epoch query checks reference surface");
 m.initial[0]=INFINITY;require(orbit::from_epoch(m,0).status==orbit::NUMERIC_FAILURE,"epoch query checks nonfinite state");
 m.initial[0]=26560000.;q.t0=.1;require(orbit::from_epoch(m,0).status==orbit::OUTSIDE_FORCING,"epoch query cannot bypass missing frame");
}
// Independent spherical Legendre recurrence and spherical partial derivatives.
// Used away from the poles; production uses Cartesian derivatives everywhere.
void spherical_oracle(const orbit::Model& model,const double* r,double* a){
 const double d=orbit::norm(r),s=r[2]/d,c=std::sqrt(1-s*s),longitude=std::atan2(r[1],r[0]);
 double p[13][13]{},dp[13][13]{};p[0][0]=1;
 for(int m=1;m<=model.gravity_degree;++m){p[m][m]=(2*m-1)*c*p[m-1][m-1];dp[m][m]=(2*m-1)*(c*dp[m-1][m-1]-s/c*p[m-1][m-1]);}
 for(int m=0;m<=model.gravity_degree;++m){
  if(m<model.gravity_degree){p[m+1][m]=(2*m+1)*s*p[m][m];dp[m+1][m]=(2*m+1)*(p[m][m]+s*dp[m][m]);}
  for(int n=m+2;n<=model.gravity_degree;++n){p[n][m]=((2*n-1)*s*p[n-1][m]-(n+m-1)*p[n-2][m])/(n-m);dp[n][m]=((2*n-1)*(p[n-1][m]+s*dp[n-1][m])-(n+m-1)*dp[n-2][m])/(n-m);}
 }
 double ar=0,alat=0,alon=0;
 for(int n=0;n<=model.gravity_degree;++n)for(int m=0;m<=n;++m){const double scale=model.mu/(d*d)*std::pow(model.radius/d,n),cs=std::cos(m*longitude),sn=std::sin(m*longitude),amplitude=model.gravity_c[n][m]*cs+model.gravity_s[n][m]*sn;
  ar-=(n+1)*scale*p[n][m]*amplitude;alat+=scale*dp[n][m]*c*amplitude;alon+=scale*p[n][m]*m*(-model.gravity_c[n][m]*sn+model.gravity_s[n][m]*cs)/c;}
 const double cl=std::cos(longitude),sl=std::sin(longitude);a[0]=ar*c*cl-alat*s*cl-alon*sl;a[1]=ar*c*sl-alat*s*sl+alon*cl;a[2]=ar*s+alat*c;
}
void r2_dynamics(){
 orbit::Segment q{},eop{};auto legacy=basic(q);eop.t0=q.t0;eop.t1=q.t1;auto m=legacy;m.gravity_degree=12;m.gravity_c[0][0]=1;m.eop={&eop,1,3};
 // Synthetic fully populated normalized spectrum, converted independently.
 for(int n=1;n<=12;++n)for(int k=0;k<=n;++k){const double normalization=std::sqrt((k?2.:1.)*(2*n+1)*std::tgamma(n-k+1.)/std::tgamma(n+k+1.));m.gravity_c[n][k]=normalization*1e-7*std::sin(3*n+7*k);m.gravity_s[n][k]=k?normalization*1e-7*std::cos(5*n+2*k):0;}
 m.gravity_c[2][0]=-.00108262668;
 const double points[][3]={{7000000.,-2000000.,1000000.},{18000000.,-21000000.,17000000.},{42164000.,3200000.,-11000000.},{10000.,-10000.,7000000.},{-27000000.,33000000.,-44000000.}};
 for(const auto& point:points){double actual[3],expected[3];orbit::harmonic_gravity(m,point,actual);spherical_oracle(m,point,expected);for(int i=0;i<3;++i)require(std::abs(actual[i]-expected[i])<2e-12,"R2 degree12 independent spherical derivative oracle");}
 for(double z:{-7000000.,7000000.}){double axis[3]={0,0,z},near[3]={.001,-.001,z},a[3],b[3];orbit::harmonic_gravity(m,axis,a);orbit::harmonic_gravity(m,near,b);require(orbit::finite(a,3),"R2 Cartesian gravity finite at pole");for(int i=0;i<3;++i)require(std::abs(a[i]-b[i])<3e-9,"R2 polar continuity");}
 // The old declared zonals and tesseral terms must be the same physical basis.
 legacy.j2=.00108262668;legacy.j3=-2.532656e-6;legacy.j4=-1.61962e-6;legacy.c22=1.574e-6;legacy.s22=-.903e-6;
 auto sparse=legacy;sparse.gravity_degree=4;sparse.gravity_c[0][0]=1;sparse.gravity_c[2][0]=-legacy.j2;sparse.gravity_c[3][0]=-legacy.j3;sparse.gravity_c[4][0]=-legacy.j4;sparse.gravity_c[2][2]=legacy.c22;sparse.gravity_s[2][2]=legacy.s22;sparse.eop={&eop,1,3};
 double state[6]={18000000.,-21000000.,17000000.,1000.,3000.,-700.},a[3],b[3];require(orbit::acceleration(legacy,0,state,a)==0&&orbit::acceleration(sparse,0,state,b)==0,"R1/R2 sparse status");for(int i=0;i<3;++i)require(std::abs(a[i]-b[i])<3e-15,"R1/R2 unnormalized basis equivalence");
 sparse.relativity=1;sparse.speed_of_light=299792458.;double gr[3];require(orbit::acceleration(sparse,0,state,gr)==0,"R2 relativity status");const double d=orbit::norm(state),v2=orbit::dot(state+3,state+3),rv=orbit::dot(state,state+3);for(int i=0;i<3;++i){const double expected=sparse.mu/(sparse.speed_of_light*sparse.speed_of_light*d*d*d)*((4*sparse.mu/d-v2)*state[i]+4*rv*state[i+3]);require(std::abs((gr[i]-b[i])-expected)<3e-17,"Schwarzschild acceleration oracle");}
 eop.degree=1;eop.coefficients[0][0]=.001;eop.coefficients[0][1]=.0002;eop.coefficients[1][0]=.012;eop.coefficients[1][1]=.004;eop.coefficients[2][0]=-.023;eop.coefficients[2][1]=.007;
 for(double t:{-1e7,0.,43210.,1e7}){double values[3],actual[9],expected[9];require(orbit::evaluate(sparse.eop,t,values),"R2 EOP status");auto fixed=legacy;fixed.era0+=values[0];fixed.xp=values[1];fixed.yp=values[2];require(orbit::frame(sparse,t,actual)&&orbit::frame(fixed,t,expected),"R2 frame status");for(int i=0;i<9;++i)require(std::abs(actual[i]-expected[i])<2e-15,"R2 forecast EOP frame composition");}
 eop.t0=-100;eop.t1=100;double matrix[9];require(!orbit::frame(sparse,101,matrix),"R2 EOP extrapolation rejected");
}
}
int main(){try{words();dynamics();chebyshev();r2_dynamics();admission();std::cout<<"orbit native: 4000 two-stage recurrences; R1 Kepler, harmonic-potential, frame and polynomial; R2 degree12 spherical oracle, pole continuity, sparse basis, Schwarzschild and forecast EOP; closed domain, physical surface and transactional rejection checks passed\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
