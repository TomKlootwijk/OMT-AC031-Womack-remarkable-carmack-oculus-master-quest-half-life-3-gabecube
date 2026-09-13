#pragma once
#include "atomos/host.hpp"
namespace atomos {
// K1 host dictionary compiler. The GPU consumes packed cells from this chart.
struct LogPolarChart {
 double r_min=0.25,r_max=64.0;u32 rows=128,angles=1024;
 void validate()const{
  if(!finite(r_min)||!finite(r_max)||r_min<=0||r_max<=r_min||!rows||!angles)
   throw std::invalid_argument("invalid log-polar chart");
  if(!finite(std::log(r_max)-std::log(r_min)))throw std::invalid_argument("log span is nonfinite");
 }
 std::array<double,2> node(u32 radial,u32 angular)const{
  validate();if(radial>=rows||angular>=angles)throw std::out_of_range("log-polar node");
  const double rho=std::log(r_min)+(double(radial)+0.5)/rows*(std::log(r_max)-std::log(r_min));
  return {rho,TAU*angular/angles};
 }
 std::array<u32,2> quantize(double radius,double phi)const{
  validate();if(!finite(radius)||!finite(phi)||radius<r_min||radius>=r_max)throw std::out_of_range("point outside half-open chart");
  const double relative=(std::log(radius)-std::log(r_min))/(std::log(r_max)-std::log(r_min));
  double angular=std::fmod(phi,TAU);if(angular<0)angular+=TAU;if(angular>=TAU)angular=0;
  return {std::min(rows-1,u32(relative*rows)),u32(angular/TAU*angles+0.5)%angles};
 }
};
}
