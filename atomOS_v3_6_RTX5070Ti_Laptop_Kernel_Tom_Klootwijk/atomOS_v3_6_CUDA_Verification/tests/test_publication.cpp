#include "atomos/publication.hpp"
#include <fstream>
#include <iostream>
#include <string>

namespace fs=std::filesystem;
namespace P=atomos::publication;
static void require(bool condition,const char*message){if(!condition)throw std::runtime_error(message);}
static void put(const fs::path&path,const char*text){std::ofstream out(path);out<<text;out.close();require(bool(out),"write test file");}
static std::string read(const fs::path&path){std::ifstream in(path);return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};}
int main(){fs::path root;try{
 const fs::path temporary=fs::weakly_canonical(fs::temp_directory_path());
 root=temporary/("atomos_publish_test_"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
 require(fs::create_directory(root),"create isolated publication test directory");
 const auto cleanup=[&]{require(root.parent_path()==temporary&&root.filename().string().rfind("atomos_publish_test_",0)==0,"cleanup confined to created test directory");fs::remove_all(root);};
 unsigned checks=0;
 {
  const auto source=root/"retry_source",destination=root/"retry_destination";fs::create_directory(source);put(source/"COMMITTED","verified payload");
  unsigned calls=0,sleeps=0;const unsigned attempts=P::publish_directory(source,destination,[&](const fs::path&a,const fs::path&b,std::error_code&error){++calls;if(calls<=3)error=std::make_error_code(std::errc::permission_denied);else P::rename_no_replace(a,b,error);},[&](auto delay){require(delay==std::chrono::milliseconds(50),"declared retry delay");++sleeps;},5);
  require(attempts==4&&calls==4&&sleeps==3,"retry count and eventual success");require(!fs::exists(source)&&read(destination/"COMMITTED")=="verified payload","retry preserves verified payload");++checks;
 }
 {
  const auto source=root/"existing_source",destination=root/"existing_destination";fs::create_directory(source);fs::create_directory(destination);put(source/"COMMITTED","new");put(destination/"COMMITTED","old");
  unsigned calls=0;bool rejected=false;try{P::publish_directory(source,destination,[&](const auto&,const auto&,auto&){++calls;},[](auto){});}catch(const fs::filesystem_error&){rejected=true;}
  require(rejected&&calls==0&&read(destination/"COMMITTED")=="old"&&read(source/"COMMITTED")=="new","existing destination never overwritten");++checks;
 }
 {
  const auto source=root/"permanent_source",destination=root/"permanent_destination";fs::create_directory(source);put(source/"COMMITTED","retained");unsigned calls=0,sleeps=0;bool rejected=false;
  try{P::publish_directory(source,destination,[&](const auto&,const auto&,std::error_code&error){++calls;error=std::make_error_code(std::errc::permission_denied);},[&](auto){++sleeps;},4);}catch(const fs::filesystem_error&){rejected=true;}
  require(rejected&&calls==4&&sleeps==3&&read(source/"COMMITTED")=="retained"&&!fs::exists(destination),"bounded transient failure retains staging");++checks;
 }
 {
  const auto source=root/"invalid_source",destination=root/"invalid_destination";fs::create_directory(source);unsigned calls=0,sleeps=0;bool rejected=false;
  try{P::publish_directory(source,destination,[&](const auto&,const auto&,std::error_code&error){++calls;error=std::make_error_code(std::errc::invalid_argument);},[&](auto){++sleeps;},4);}catch(const fs::filesystem_error&){rejected=true;}
  require(rejected&&calls==1&&sleeps==0&&fs::exists(source),"nontransient failure is immediate");++checks;
 }
 {
  const auto source=root/"racing_source",destination=root/"racing_destination";fs::create_directory(source);put(source/"COMMITTED","new");bool rejected=false;
  try{P::publish_directory(source,destination,[&](const auto&a,const auto&b,std::error_code&error){fs::create_directory(b);put(b/"COMMITTED","racing writer");P::rename_no_replace(a,b,error);},[](auto){});}catch(const fs::filesystem_error&){rejected=true;}
  require(rejected&&read(destination/"COMMITTED")=="racing writer"&&read(source/"COMMITTED")=="new","racing destination never overwritten");++checks;
 }
 cleanup();std::cout<<"publication regression: "<<checks<<" checks passed\n";return 0;
 }catch(const std::exception&error){std::cerr<<error.what()<<"; retained test directory: "<<root.string()<<'\n';return 1;}
}
