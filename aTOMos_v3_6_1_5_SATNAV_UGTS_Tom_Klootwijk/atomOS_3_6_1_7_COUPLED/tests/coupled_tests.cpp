#include "coupled_backend.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
namespace {
int checks=0;
void check(bool result,const char* message){++checks;if(!result)throw std::runtime_error(message);}
void close(double value,double expected,const char* message,double tolerance=1e-11){check(std::abs(value-expected)<=tolerance*std::max(1.,std::abs(expected)),message);}
template<class F> coupled::Table table(unsigned n,F fn){coupled::Table t{};for(unsigned index=0;index<(1u<<n);++index)if(fn(index))t.words[index/64]|=1ull<<(index%64);return t;}
coupled::Table variable(unsigned n,unsigned which){return table(n,[&](unsigned index){return ((index>>(n-1-which))&1u)!=0;});}
coupled::Job base_job(){coupled::Job j{};j.r0=100;j.core=1e-6;j.p0[0]=10;j.mass[0]=j.mass[1]=j.mass[2]=1;j.asa_mask=j.na_mask=0xffffffffu;return j;}
coupled::Channel base_channel(){coupled::Channel c{};c.u[0]=1;c.extent=100;c.angle_tolerance=coupled::PI;c.error_limit=.5;c.fringe_width=.1;return c;}
coupled::Sample sample(double t){coupled::Sample s{};s.time=t;s.valid=1;s.target[0]=10;return s;}
void free_and_force(){
 auto j=base_job();j.v0[0]=2;j.v0[1]=-3;j.v0[2]=.7;auto state=coupled::initial_state(j);auto s=sample(.25);auto r=coupled::transition(j,s,state);
 check(r.status==coupled::ADVANCED,"free advance status");for(int i=0;i<3;++i){close(r.v_after[i],j.v0[i],"free velocity");close(r.p_after[i],j.p0[i]+.25*j.v0[i],"free position");}
 j.mass[0]=2;j.mass[1]=3;j.mass[2]=4;state=coupled::initial_state(j);s.force[0]=4;s.force[1]=-6;s.force[2]=2;
 for(int step=1;step<=12;++step){s.time=.25*step;r=coupled::transition(j,s,state);for(int i=0;i<3;++i){const double acceleration=s.force[i]/j.mass[i];close(r.v_after[i],j.v0[i]+.25*step*acceleration,"constant force velocity");close(r.p_after[i],j.p0[i]+.25*step*j.v0[i]+.25*.25*acceleration*step*(step+1)/2,"constant force discrete position");}}
}
void spring_and_signed(){
 auto j=base_job();j.base[0]=4;j.mass[0]=2;j.damping[0]=3;j.v0[0]=1;auto s=sample(.2);s.target[0]=13;s.force[0]=5;auto state=coupled::initial_state(j);auto r=coupled::transition(j,s,state);
 const double velocity=(2+.2*(5+4*3))/(2+.2*3+.04*4);close(r.v_after[0],velocity,"backward Euler spring equation");close(r.p_after[0],10+.2*velocity,"spring position");close(r.eigenvalues[2],2,"mass normalized frequency");
 j.base[0]=-4;j.damping[0]=-3;state=coupled::initial_state(j);r=coupled::transition(j,s,state);check(r.status==coupled::ADVANCED,"signed coefficients allowed");close(r.v_after[0],(2+.2*(5-4*3))/(2-.2*3-.04*4),"signed backward Euler");close(r.eigenvalues[0],-2,"negative eigenvalue retained");
 s.valid=0;state=coupled::initial_state(j);r=coupled::transition(j,s,state);close(r.v_after[0],(2+.2*5)/(2-.2*3),"unavailable observation spring vanishes");close(r.stiffness[0],-4,"unavailable observation physical matrix retained");
 // Discrete spring convergence to p(t)=10+3*(1-cos(2t)) with p0=10,v0=0,target=13.
 j=base_job();j.base[0]=4;s=sample(0);s.target[0]=13;
 double errors[2]{};for(int resolution=0;resolution<2;++resolution){const int steps=resolution?200:100;state=coupled::initial_state(j);for(int n=1;n<=steps;++n){s.time=double(n)/steps;r=coupled::transition(j,s,state);}errors[resolution]=std::abs(r.p_after[0]-(13-3*std::cos(2.)));}
 check(errors[1]<errors[0]&&errors[1]<.03,"spring timestep refinement approaches analytic oscillator");
}
void eigenmodes(){
 const double matrix[9]={4,1,.5,1,3,-.25,.5,-.25,2};double values[3]{},vectors[9]{},residual=0;
 check(coupled::eigensystem(matrix,values,vectors,residual),"offdiagonal eigensystem success");check(values[0]<=values[1]&&values[1]<=values[2],"eigenvalues sorted");check(residual<1e-12,"offdiagonal eigen residual");
 for(int i=0;i<3;++i)for(int j=0;j<3;++j){double dot=0;for(int k=0;k<3;++k)dot+=vectors[3*k+i]*vectors[3*k+j];close(dot,i==j?1:0,"orthonormal eigenvectors");}
 auto job=base_job();job.mass[0]=4;job.mass[1]=9;job.mass[2]=16;for(int i=0;i<3;++i)for(int j=0;j<3;++j)job.base[3*i+j]=matrix[3*i+j]*std::sqrt(job.mass[i])*std::sqrt(job.mass[j]);auto state=coupled::initial_state(job);auto r=coupled::transition(job,sample(.01),state);
 for(int i=0;i<9;++i)close(r.eigenmatrix[i],matrix[i],"mass normalization all matrix entries");for(int i=0;i<3;++i)close(r.eigenvalues[i],values[i],"mass normalized eigenvalues");
 for(int mode=0;mode<3;++mode)for(int row=0;row<3;++row){double lhs=0;for(int col=0;col<3;++col)lhs+=job.base[3*row+col]*r.eigenvectors[3*col+mode]/std::sqrt(job.mass[col]);const double rhs=r.eigenvalues[mode]*job.mass[row]*r.eigenvectors[3*row+mode]/std::sqrt(job.mass[row]);close(lhs,rhs,"generalized physical mass mode");}
 const double repeated[9]={2,0,0,0,2,0,0,0,2};check(coupled::eigensystem(repeated,values,vectors,residual),"repeated eigenmodes");for(double v:values)close(v,2,"repeated eigenvalue");
 const double multiscale[9]={1e308,0,0,0,1,.5,0,.5,1};check(coupled::eigensystem(multiscale,values,vectors,residual),"multiscale independent block modes");close(values[0],.5,"small first mode beside huge stiffness");close(values[1],1.5,"small second mode beside huge stiffness");close(values[2],1e308,"huge stiffness eigenvalue");
 const double tiny_coupling[9]={1,1e-200,0,1e-200,0,0,0,0,2};check(coupled::eigensystem(tiny_coupling,values,vectors,residual),"tiny coupling stable rotation");close(values[0],0,"tiny coupling does not invent low eigenvalue",1e-100);close(values[1],1,"tiny coupling preserves positive mode");
}
void coupling_and_absorption(){
 auto j=base_job();j.present=1;j.channels[0]=base_channel();j.channels[0].k_on=2;j.channels[0].force_on=3;
 j.drive_lut=variable(6,2);j.x_lut=variable(7,1);j.j_lut=variable(8,1);j.k_lut=variable(8,3);
 auto a=coupled::initial_state(j),b=coupled::initial_state(j);auto far=sample(.1),near=sample(.1);far.target[0]=12;near.target[0]=10.1;
 auto r=coupled::transition(j,far,a),counter=coupled::transition(j,near,b);
 check(r.limit==1&&counter.limit==0,"geometry changes limit");check(r.q_after==1&&counter.q_after==0,"geometry changes persistent word");check(r.stiffness[0]==2&&counter.stiffness[0]==0,"q changes stiffness");check(r.force[0]==3&&counter.force[0]==0,"q changes force");check(r.p_after[0]>counter.p_after[0],"state dependent mechanical response");
 // Identical geometric input, only initial q differs. Hold tables preserve it.
 j.j_lut={};j.k_lut={};j.q0=0;a=coupled::initial_state(j);j.q0=1;b=coupled::initial_state(j);r=coupled::transition(j,far,a);counter=coupled::transition(j,far,b);
 check(r.p_after[0]!=counter.p_after[0],"q to geometry counterfactual");far.time=.2;r=coupled::transition(j,far,a);counter=coupled::transition(j,far,b);check(r.rho!=counter.rho,"physical state returns to next chart");
 j=base_job();j.present=3;j.channels[0]=j.channels[1]=base_channel();j.x_lut=table(7,[](unsigned){return true;});j.j_lut=variable(8,1);j.k_lut=table(8,[](unsigned){return true;});j.boundary_mask=2;j.q0=3;a=coupled::initial_state(j);r=coupled::transition(j,sample(.1),a);
 check(r.na==3&&r.hits==1&&r.output==0,"literal whole word absorption");check(r.q_after==0,"absorption does not insert hidden JK hold");
 j.present=1;j.channels[0].extent=1;j.j_lut=table(8,[](unsigned){return true;});j.k_lut={};j.q0=0;a=coupled::initial_state(j);r=coupled::transition(j,sample(.1),a);check(r.support==0&&r.q_after==1,"no hidden support hold");
}
void geometry(){
 auto j=base_job();j.present=1;j.channels[0]=base_channel();j.channels[0].extent=10;j.channels[0].fringe_width=0;
 auto state=coupled::initial_state(j);auto s=sample(.1);auto r=coupled::transition(j,s,state);check(r.support==1&&r.fringe==1,"sphere closed boundary");check(r.otan_status==coupled::FIRST_OBSERVATION,"first phase status");s.time=.2;r=coupled::transition(j,s,state);check(r.otan_status==coupled::ZERO_INCREMENT,"literal zero increment");
 state=coupled::initial_state(j);state.has_previous=state.previous_chart_defined=true;state.previous_rho=std::log(.1);state.previous_theta=.1;r=coupled::transition(j,s,state);check(r.otan_status==coupled::RATIO_UNDEFINED,"literal zero radial denominator is undefined");
 state=coupled::initial_state(j);state.has_previous=state.previous_chart_defined=true;state.previous_rho=std::log(.1)+1;state.previous_theta=.5;r=coupled::transition(j,s,state);check(r.otan_status==coupled::OTAN_DEFINED,"literal ratio defined");close(r.otan,std::atan(.5),"atan ratio not atan2");
 j.p0[0]=0;state=coupled::initial_state(j);r=coupled::transition(j,s,state);check(r.chart_status==coupled::ORIGIN_CORE,"origin core status");check(!r.blend_defined,"undefined blend alignment only");check(r.status==coupled::ADVANCED,"undefined phase does not hold mechanics");
 close(coupled::wrap(coupled::PI),-coupled::PI,"minus pi tie");
 close(coupled::circle_plus(170*coupled::PI/180,-170*coupled::PI/180,.5),-coupled::PI,"circle plus crosses wrapped branch");
 close(coupled::circle_plus(.7,-1.2,0),.7,"circle plus weight zero");close(coupled::circle_plus(.7,-1.2,1),-1.2,"circle plus weight one");
 j.p0[0]=10;j.blend_weight=.5;j.hoop0=.3;j.hoop_rate=.7;j.channels[0].angle_center=coupled::wrap(.5*std::atan(.5)+.3);j.channels[0].angle_tolerance=1e-12;
 state=coupled::initial_state(j);state.has_previous=state.previous_chart_defined=true;state.previous_rho=std::log(.1)+1;state.previous_theta=.5;s.target[0]=12;s.time=.2;r=coupled::transition(j,s,state);
 check(r.blend_defined&&r.alignment==1,"defined circle plus reaches alignment encoder");close(r.blend,j.channels[0].angle_center,"blend includes old hoop phase");close(r.phi_after,.44,"hoop phase persistent synchronous advance");
 j.channels[0].angle_center+=.01;state=coupled::initial_state(j);state.has_previous=state.previous_chart_defined=true;state.previous_rho=std::log(.1)+1;state.previous_theta=.5;r=coupled::transition(j,s,state);check(r.alignment==0,"outside alignment tolerance");
 coupled::Channel cone{};cone.support_kind=1;cone.extent=2;cone.axis[2]=1;cone.angle=coupled::PI/4;
 const double inside[3]={0,0,.5},outside[3]={3,0,.5},apex[3]={0,0,0};check(coupled::support_sdf(inside,cone)<0,"cone interior");check(coupled::support_sdf(outside,cone)>0,"cone exterior");close(coupled::support_sdf(apex,cone),0,"cone apex boundary");
}
void failures_and_luts(){
 auto j=base_job();j.present=1;j.channels[0]=base_channel();j.j_lut=table(8,[](unsigned){return true;});j.damping[0]=-1;
 auto state=coupled::initial_state(j);auto s=sample(1);s.force[0]=1;auto r=coupled::transition(j,s,state);
 check(r.status==coupled::NUMERIC_FAILURE,"singular mechanics explicit failure");check(r.q_after==1&&state.q==1,"failure keeps computed q trace");close(state.time,0,"failure retains valid time");close(r.p_after[0],10,"failure retains physical position");s.time=2;r=coupled::transition(j,s,state);check(r.status==coupled::PREVIOUS_FAILURE,"failed trajectory stops");check(r.chart_status==coupled::CHART_NOT_EVALUATED&&r.otan_status==coupled::OTAN_NOT_EVALUATED,"failed trajectory diagnostics not evaluated");check(r.q_before==1&&r.q_after==1,"failed trajectory state frozen");
 j=base_job();j.base[0]=1e308;state=coupled::initial_state(j);s=sample(2);r=coupled::transition(j,s,state);check(r.status==coupled::NUMERIC_FAILURE,"finite input overflow explicitly fails");check(!satnav::finite(r.mechanical_matrix[0]),"nonfinite mechanical diagnostic retained for null serialization");check(satnav::finite(r.eigenvalues[2])&&r.eigenvalues[2]==1e308,"finite eigenpairs retained on mechanical overflow");
 j=base_job();j.present=0xffffffffu;j.q0=0x80000001u;for(auto& c:j.channels)c=base_channel();state=coupled::initial_state(j);r=coupled::transition(j,sample(.1),state);check(r.q_after==0x80000001u&&r.support==0xffffffffu,"full present word including bit31");
 double mat[9]={1e-14,0,0,0,1,0,0,0,-2},rhs[3]={1e-14,2,-6},solution[3]{};check(coupled::solve3(mat,rhs,solution),"near singular signed matrix still solved");for(int i=0;i<3;++i){close(solution[i],i+1,"near singular signed solution");double residual=-rhs[i];for(int k=0;k<3;++k)residual+=mat[3*i+k]*solution[k];close(residual,0,"mechanical solve residual");}
 for(unsigned n=6;n<=8;++n)for(unsigned variable_index=0;variable_index<n;++variable_index){const auto t=variable(n,variable_index);std::uint32_t words[8]={0x01234567u,0x89abcdefu,0x55555555u,0xaaaaaaaau,0x11111111u,0xf0f0f0f0u,0xff00ff00u,0x80000000u};check(coupled::evaluate(t,words,n)==words[variable_index],"all LUT variables and slots");}
 auto table_full=table(8,[](unsigned index){return index==255;});std::uint32_t ones[8];for(auto& w:ones)w=0xffffffffu;check(coupled::evaluate(table_full,ones,8)==0xffffffffu,"LUT last bit 255");
}
}
int main(){try{free_and_force();spring_and_signed();eigenmodes();coupling_and_absorption();geometry();failures_and_luts();std::cout<<"CGK-R1: "<<checks<<" checks passed\n";return 0;}catch(const std::exception& e){std::cerr<<"CGK-R1 failed after "<<checks<<" checks: "<<e.what()<<'\n';return 1;}}
