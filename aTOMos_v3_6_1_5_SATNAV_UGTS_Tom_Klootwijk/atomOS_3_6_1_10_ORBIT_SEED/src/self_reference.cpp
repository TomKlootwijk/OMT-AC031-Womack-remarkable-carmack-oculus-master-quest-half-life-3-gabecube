#include "self_reference_backend.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <unordered_set>

namespace selfref {
Run cpu_run(const std::vector<Job>& jobs,std::size_t trace_rows) {
 Run run;run.backend="cpu";run.trace.resize(trace_rows);
 const auto begin=std::chrono::steady_clock::now();
 for(const Job& job:jobs) {
  std::uint32_t q=job.q0;
  for(std::uint64_t tick=0;tick<job.steps;++tick) {
   const Step next=transition(q,job);
   run.trace[static_cast<std::size_t>(job.offset+tick)]=next;q=next.after;
  }
 }
 run.kernel_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 return run;
}
}
namespace {
constexpr const char* input_header="trajectory_id,q0,drive,present,asa_mask,na_mask,boundary_mask,x_lut,j_lut,k_lut,steps";
std::uint64_t decimal(const std::string& text,std::uint64_t limit,const std::string& name) {
 if(text.empty())throw std::invalid_argument(name+": expected unsigned decimal integer");
 std::uint64_t value=0;
 for(char c:text) {
  if(c<'0'||c>'9')throw std::invalid_argument(name+": expected unsigned decimal integer");
  const auto digit=static_cast<std::uint64_t>(c-'0');
  if(value>limit/10||(value==limit/10&&digit>limit%10))throw std::invalid_argument(name+": integer out of range");
  value=value*10+digit;
 }
 return value;
}
std::vector<std::string> split(const std::string& line) {
 std::vector<std::string> fields;std::size_t start=0;
 for(;;) {
  const auto end=line.find(',',start);
  fields.push_back(line.substr(start,end==std::string::npos?end:end-start));
  if(end==std::string::npos)return fields;
  start=end+1;
 }
}
bool get_line(std::istream& input,std::string& line) {
 if(!std::getline(input,line))return false;
 if(!line.empty()&&line.back()=='\r')line.pop_back();
 return true;
}
struct Input {std::vector<selfref::Job> jobs;std::size_t trace_rows{};std::size_t allocation_bytes{};};
Input read_input(const std::filesystem::path& path) {
 std::ifstream file(path);if(!file)throw std::runtime_error("cannot open input CSV");
 std::string line;
 if(!get_line(file,line)||line!=input_header)throw std::invalid_argument("input CSV header must be: "+std::string(input_header));
 Input data;std::unordered_set<std::uint64_t> ids;std::size_t row=1;
 const auto maxword=std::numeric_limits<std::uint32_t>::max();
 const auto max64=std::numeric_limits<std::uint64_t>::max();
 const auto maxrows=std::vector<selfref::Step>().max_size();
 while(get_line(file,line)) {
  ++row;const auto fields=split(line);
  if(fields.size()!=11)throw std::invalid_argument("CSV row "+std::to_string(row)+": expected 11 fields");
  const std::string label="CSV row "+std::to_string(row)+" field ";
  selfref::Job job{};
  job.id=decimal(fields[0],max64,label+"trajectory_id");
  job.q0=static_cast<std::uint32_t>(decimal(fields[1],maxword,label+"q0"));
  job.drive=static_cast<std::uint32_t>(decimal(fields[2],maxword,label+"drive"));
  job.present=static_cast<std::uint32_t>(decimal(fields[3],maxword,label+"present"));
  job.asa_mask=static_cast<std::uint32_t>(decimal(fields[4],maxword,label+"asa_mask"));
  job.na_mask=static_cast<std::uint32_t>(decimal(fields[5],maxword,label+"na_mask"));
  job.boundary_mask=static_cast<std::uint32_t>(decimal(fields[6],maxword,label+"boundary_mask"));
  job.x_lut=static_cast<std::uint8_t>(decimal(fields[7],15,label+"x_lut"));
  job.j_lut=static_cast<std::uint8_t>(decimal(fields[8],255,label+"j_lut"));
  job.k_lut=static_cast<std::uint8_t>(decimal(fields[9],255,label+"k_lut"));
  job.steps=decimal(fields[10],max64,label+"steps");
  if(!job.steps)throw std::invalid_argument(label+"steps: must be nonzero");
  if((job.q0&~job.present)!=0)throw std::invalid_argument(label+"q0: state must be a subset of present");
  if(!ids.insert(job.id).second)throw std::invalid_argument(label+"trajectory_id: duplicate identifier");
  if(job.steps>maxrows-data.trace_rows)throw std::length_error("trace rows exceed addressable vector capacity");
  job.offset=static_cast<std::uint64_t>(data.trace_rows);
  data.trace_rows+=static_cast<std::size_t>(job.steps);data.jobs.push_back(job);
 }
 if(file.bad())throw std::runtime_error("error reading input CSV");
 if(data.jobs.empty())throw std::invalid_argument("input CSV has no trajectories");
 const auto maximum=std::numeric_limits<std::size_t>::max();
 const auto trace_bytes=data.trace_rows*sizeof(selfref::Step);
 if(data.jobs.size()>(maximum-trace_bytes)/sizeof(selfref::Job))throw std::length_error("combined trace/job allocation byte count overflow");
 data.allocation_bytes=trace_bytes+data.jobs.size()*sizeof(selfref::Job);
 return data;
}
std::string json_string(const std::string& value) {
 std::ostringstream out;out<<'"';
 for(unsigned char c:value) {
  if(c=='"'||c=='\\')out<<'\\'<<static_cast<char>(c);
  else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned>(c)<<std::dec;
  else out<<static_cast<char>(c);
 }
 out<<'"';return out.str();
}
std::ofstream output_file(const std::filesystem::path& path) {
 std::ofstream out;out.exceptions(std::ios::badbit|std::ios::failbit);out.open(path);return out;
}
void usage() {
 std::cout<<"aTOMos 3.6.1.6 / SRK-R1\n"
 <<"self_reference --input trajectories.csv --out NEW_DIRECTORY --backend cpu|cuda [--device N]\n"
 <<input_header<<'\n';
}
}
int main(int argc,char** argv) {
 try {
  std::string input_path,out_path,backend;int device=0;
  std::unordered_set<std::string> options;
  for(int i=1;i<argc;++i) {
   const std::string arg=argv[i];
   if(arg=="--help"){usage();return 0;}
   if(arg!="--input"&&arg!="--out"&&arg!="--backend"&&arg!="--device")throw std::invalid_argument("unknown argument: "+arg);
   if(!options.insert(arg).second)throw std::invalid_argument("duplicate option: "+arg);
   if(++i==argc)throw std::invalid_argument("missing value for "+arg);
   if(arg=="--input")input_path=argv[i];
   else if(arg=="--out")out_path=argv[i];
   else if(arg=="--backend")backend=argv[i];
   else device=static_cast<int>(decimal(argv[i],static_cast<std::uint64_t>(std::numeric_limits<int>::max()),"--device"));
  }
  if(input_path.empty()||out_path.empty()||(backend!="cpu"&&backend!="cuda"))throw std::invalid_argument("required: --input CSV --out NEW_DIRECTORY --backend cpu|cuda");
  if(std::filesystem::exists(out_path))throw std::invalid_argument("output directory already exists; choose a new directory");
#ifndef SATNAV_HAS_CUDA
  if(backend=="cuda") {
   std::cerr<<"self_reference: not_run: CUDA backend not built; configure SATNAV_ENABLE_CUDA=ON\n";
   return 3;
  }
#endif
  const auto begin=std::chrono::steady_clock::now();
  const Input input=read_input(input_path);
  selfref::Run run;
  if(backend=="cpu")run=selfref::cpu_run(input.jobs,input.trace_rows);
#ifdef SATNAV_HAS_CUDA
  else run=selfref::cuda_run(input.jobs,input.trace_rows,device);
#else
  (void)device;
#endif
  if(!std::filesystem::create_directory(out_path))throw std::runtime_error("could not create new output directory");
  auto trace=output_file(std::filesystem::path(out_path)/"trace.csv");
  trace<<"trajectory_id,step,before,drive,x,asa,na,hits,output,j,k,after\n";
  for(const auto& job:input.jobs)for(std::uint64_t tick=0;tick<job.steps;++tick) {
   const auto& r=run.trace[static_cast<std::size_t>(job.offset+tick)];
   trace<<job.id<<','<<tick<<','<<r.before<<','<<r.drive<<','<<r.x<<','<<r.asa<<','<<r.na<<','<<r.hits<<','<<r.output<<','<<r.j<<','<<r.k<<','<<r.after<<'\n';
  }
  trace.close();
  const double elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
  auto meta=output_file(std::filesystem::path(out_path)/"run.json");
  meta<<std::setprecision(17)<<"{\n  \"version\": \"3.6.1.6\",\n  \"profile\": \"SRK-R1\",\n  \"status\": \"completed\",\n  \"backend\": "<<json_string(run.backend)
   <<",\n  \"device\": "<<run.device_json<<",\n  \"kernel_ms\": "<<run.kernel_ms<<",\n  \"elapsed_ms\": "<<elapsed
   <<",\n  \"elapsed_scope\": \"input parsing through trace file close, excluding run.json\",\n  \"input\": "<<json_string(input_path)
   <<",\n  \"trajectories\": "<<input.jobs.size()<<",\n  \"trace_rows\": "<<input.trace_rows
   <<",\n  \"step_record_bytes\": "<<sizeof(selfref::Step)<<",\n  \"job_record_bytes\": "<<sizeof(selfref::Job)
   <<",\n  \"trace_and_job_bytes\": "<<input.allocation_bytes<<",\n  \"trace_lengths\": [";
  for(std::size_t i=0;i<input.jobs.size();++i) {
   const auto& job=input.jobs[i];
   if(i)meta<<',';
   meta<<"\n    {\"trajectory_id\": "<<job.id<<", \"steps\": "<<job.steps<<", \"offset\": "<<job.offset<<", \"final_state\": "<<run.trace[static_cast<std::size_t>(job.offset+job.steps-1)].after<<'}';
  }
  meta<<"\n  ]\n}\n";meta.close();
  std::cout<<"SRK-R1 "<<run.backend<<": "<<input.jobs.size()<<" trajectories, "<<input.trace_rows<<" transitions; kernel "<<run.kernel_ms<<" ms\n";
  return 0;
 }catch(const std::exception& error) {
  std::cerr<<"self_reference: "<<error.what()<<'\n';return 1;
 }
}
