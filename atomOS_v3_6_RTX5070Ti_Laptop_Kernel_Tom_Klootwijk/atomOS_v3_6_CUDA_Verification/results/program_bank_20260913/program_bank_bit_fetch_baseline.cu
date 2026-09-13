// Tom Klootwijk atomOS: immutable seeded one-bit program LUTs in a VRAM bank.
// The fixed source-word NOR operator texture is reused through program switches.
#include "../cuda/kernel.cu"
#include "atomos/program_bank.hpp"
#include "atomos/sdf_nor.hpp"
#include "atomos/packed_atlas.hpp"
#include <charconv>
#include <iostream>

using namespace atomos;
namespace P=atomos::program_bank;
namespace fs=std::filesystem;
namespace program_detail {
struct SegmentView {cudaTextureObject_t texture=0;u64 first_slot=0,slots=0;};
struct Origin {u32 row=0,angle=0;};
struct Hop {u32 hop=0,program_id=0,version=0,input=0,output=0,next_slot=0,gate_evaluations=0,valid=0;u64 physical_slot=0,program_bit_reads=0;u32 page_sweep_checksum=0;};
struct BankResult {
 u32 hops=0,error=0,sm_before=0,sm_after=0,final_program_id=0,final_input=0;
 u64 program_bit_reads=0,operator_gate_reads=0,operator_sweep_reads=0,program_sweep_reads=0;
 uint4 operator_warm{},operator_reread{};u32 program_warm=0,program_reread=0;
};
static_assert(sizeof(Origin)==8&&sizeof(Hop)==56,"program bank native trace ABI");
__device__ inline u32 sm_id(){u32 value;asm volatile("mov.u32 %0, %%smid;":"=r"(value));return value;}
__device__ inline uint4 operator_sweep(cudaTextureObject_t texture){uint4 v=make_uint4(0,0,0,0);for(u32 i=0;i<64;++i){const auto x=tex1Dfetch<uint4>(texture,int(i));v.x^=x.x;v.y^=x.y;v.z^=x.z;v.w^=x.w;}return v;}
__device__ inline u32 pool_word(const SegmentView*segments,u64 slots_per_segment,u64 slot,u64 page_words,u32 word){
 const u32 segment=u32(slot/slots_per_segment);const auto view=segments[segment];return tex1Dfetch<u32>(view.texture,int((slot-view.first_slot)*page_words+word));
}
__device__ inline u32 page_field(const SegmentView*segments,u64 slots_per_segment,u64 slot,Shape shape,Layout layout,Origin origin,u32 offset,u32 bits,u64&reads){
 u32 value=0;for(u32 b=0;b<bits;++b){const u64 bit=u64(offset)+b;
  const auto pos=klein::canonical(std::int64_t(origin.row)+std::int64_t(bit/shape.angles),std::int64_t(origin.angle)+std::int64_t(bit%shape.angles),shape.rows,shape.angles);
  const u32 word=pool_word(segments,slots_per_segment,slot,u64(shape.padded_rows)*shape.padded_words,address(shape,pos.row,pos.angle/32,layout));
  value|=((word>>(pos.angle%32))&1u)<<b;++reads;
 }return value;
}
__device__ inline u32 pool_sweep(const SegmentView*segments,u32 segment_count,u64 page_words,u64&reads){
 u32 value=0;for(u32 s=0;s<segment_count;++s){const auto view=segments[s];for(u64 i=0;i<view.slots*page_words;++i){value^=tex1Dfetch<u32>(view.texture,int(i));++reads;}}return value;
}
__global__ void fill_program_pool(u32*destination,u64 destination_words,const u32*templates,u64 template_words,u64 first_word){
 for(u64 i=u64(blockIdx.x)*blockDim.x+threadIdx.x;i<destination_words;i+=u64(blockDim.x)*gridDim.x)destination[i]=templates[(first_word+i)%template_words];
}
__global__ void atomos_program_bank(const SegmentView*segments,u32 segment_count,u64 slots_per_segment,const Origin*origins,
 Shape page_shape,Layout layout,cudaTextureObject_t operators,u32 distinct,u64 pool_slots,u64 replica_stride,u32 initial_slot,u32 input_initial,u32 hops,u32 full_sweep,u32 inject,
 u32*wires,Hop*trace,BankResult*out){
 if(blockIdx.x||threadIdx.x)return;
 BankResult result{};result.sm_before=sm_id();result.operator_warm=operator_sweep(operators);result.operator_sweep_reads+=64;
 const u64 page_words=u64(page_shape.padded_rows)*page_shape.padded_words;
 if(full_sweep)result.program_warm=pool_sweep(segments,segment_count,page_words,result.program_sweep_reads);
 u32 current=initial_slot,input=input_initial;const u64 replicas=pool_slots/distinct;
 const Shape operator_shape{8,256,8,8,8};
 for(u32 hop=0;hop<hops;++hop){
  const u64 replica=(u64(hop)*(replica_stride%replicas))%replicas,slot=replica*distinct+current;
  Hop record{};record.hop=hop;record.program_id=current;record.physical_slot=slot;record.input=input;const Origin origin=origins[current];
  if(!full_sweep)for(u64 word=0;word<page_words;++word){record.page_sweep_checksum^=pool_word(segments,slots_per_segment,slot,page_words,u32(word));++result.program_sweep_reads;}
  u64 bit_reads=0;
  const u32 magic=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,0,32,bit_reads);
  const u32 schema=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,32,32,bit_reads);
  const u32 inputs=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,64,32,bit_reads);
  const u32 outputs=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,96,32,bit_reads);
  const u32 gates=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,128,32,bit_reads);
  const u32 width=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,160,32,bit_reads);
  const u32 length=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,192,32,bit_reads);
  const u32 id=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,224,32,bit_reads);
  record.version=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,256,32,bit_reads);
  record.next_slot=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,288,32,bit_reads);
  const u32 data_start=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,320,32,bit_reads);
  const u32 reserved=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,352,32,bit_reads);
  if(magic!=P::PAGE_MAGIC||schema!=1||inputs>32||!outputs||outputs>32||gates>P::MAX_WIRES||u64(inputs)+1+gates>P::MAX_WIRES||!width||width>10||
     length!=P::HEADER_BITS+(u64(gates)*2+outputs)*width||length>u64(page_shape.rows)*page_shape.angles||id!=current||!record.version||record.next_slot>=distinct||data_start!=P::HEADER_BITS||reserved){
   record.program_bit_reads=bit_reads;trace[hop]=record;result.program_bit_reads+=bit_reads;result.error=1;break;
  }
  for(u32 bit=0;bit<inputs;++bit)wires[bit]=(input>>bit)&1u;wires[inputs]=0;
  u32 offset=P::HEADER_BITS;bool valid=true;
  for(u32 gate=0;gate<gates;++gate){
   const u32 left=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,offset,width,bit_reads);
   const u32 right=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,offset+width,width,bit_reads);offset+=2*width;
   if(left>=inputs+1+gate||right>=inputs+1+gate){valid=false;result.error=2;break;}
   // Required reflected Klein seam: rotate through lifted negative/zero/positive winding.
   const u32 site=gate%64;const auto pos=klein::canonical(site/8,std::int64_t(site%8)*32+(std::int64_t(gate%3)-1)*256,8,256);
   const uint4 masks=tex1Dfetch<uint4>(operators,int(address(operator_shape,pos.row,pos.angle/32,layout)));
   wires[inputs+1+gate]=sdf_nor::source_gate(wires[left],wires[right],masks.x,masks.y,masks.z,masks.w);++record.gate_evaluations;
  }
  if(valid)for(u32 bit=0;bit<outputs;++bit){const u32 ref=page_field(segments,slots_per_segment,slot,page_shape,layout,origin,offset,width,bit_reads);offset+=width;
   if(ref>=inputs+1+gates){valid=false;result.error=3;break;}record.output|=wires[ref]<<bit;}
  if(valid&&inject==2&&hop==0)record.output^=1u;
  record.valid=valid?1u:0u;record.program_bit_reads=bit_reads;trace[hop]=record;result.program_bit_reads+=bit_reads;result.operator_gate_reads+=record.gate_evaluations;
  if(!valid)break;++result.hops;current=record.next_slot;input=record.output;
 }
 result.final_program_id=current;result.final_input=input;
 if(full_sweep)result.program_reread=pool_sweep(segments,segment_count,page_words,result.program_sweep_reads);
 result.operator_reread=operator_sweep(operators);result.operator_sweep_reads+=64;result.sm_after=sm_id();*out=result;
}
u64 add(u64 a,u64 b){if(b>UINT64_MAX-a)throw std::length_error("program memory sum overflow");return a+b;}
u64 mul(u64 a,u64 b){if(a&&b>UINT64_MAX/a)throw std::length_error("program memory product overflow");return a*b;}
u64 integer(const std::string&text){u64 value=0;const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size())throw std::invalid_argument("unsigned decimal required");return value;}
u32 integer32(const std::string&text){const u64 value=integer(text);if(value>UINT32_MAX)throw std::invalid_argument("uint32 limit");return u32(value);}
std::ofstream file(const fs::path&path){std::ofstream out;out.exceptions(std::ios::failbit|std::ios::badbit);out.open(path,std::ios::binary);return out;}
void write_text(const fs::path&path,const std::string&value){auto out=file(path);out<<value;}
bool checksum_equal(uint4 a,uint4 b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;}
std::string checksum(uint4 a){return "["+std::to_string(a.x)+","+std::to_string(a.y)+","+std::to_string(a.z)+","+std::to_string(a.w)+"]";}
struct PoolSegment {std::unique_ptr<Buffer<u32>> memory;std::unique_ptr<Texture> texture;u64 first_slot=0,slots=0;};
struct Options {fs::path bank,atlas,out;Layout layout=Layout::linear;std::string layout_name="linear",injection="none";u32 device=0,input=0,hops=8,initial_slot=0;u64 pool_mib=0,reserve_mib=1536,replica_stride=1,sweep_limit_mib=1;double fraction=0;};
Options options(int argc,char**argv){Options o;for(int i=1;i<argc;++i){const std::string key=argv[i];
 if(key=="--help"){std::cout<<"atomos_program_bank --bank FILE --atlas FILE --out NEW_DIR --layout linear|morton8 --input UINT32 --initial-slot N --hops N --pool-mib N --reserve-mib N --fill-free-fraction 0..0.90 --replica-stride N --sweep-limit-mib N --inject none|program|output\nImmutable packed NOR pages switch through their texture-read next_slot field. Pool replicas are allocation stress, not additional learned knowledge.\n";std::exit(0);}
 if(++i>=argc)throw std::invalid_argument("missing argument value");const std::string value=argv[i];
 if(key=="--bank")o.bank=value;else if(key=="--atlas")o.atlas=value;else if(key=="--out")o.out=value;else if(key=="--input")o.input=integer32(value);else if(key=="--hops")o.hops=integer32(value);
  else if(key=="--device")o.device=integer32(value);else if(key=="--pool-mib")o.pool_mib=integer(value);else if(key=="--reserve-mib")o.reserve_mib=integer(value);else if(key=="--replica-stride")o.replica_stride=integer(value);
 else if(key=="--initial-slot")o.initial_slot=integer32(value);else if(key=="--sweep-limit-mib")o.sweep_limit_mib=integer(value);
 else if(key=="--fill-free-fraction"){std::size_t used=0;o.fraction=std::stod(value,&used);if(used!=value.size()||!std::isfinite(o.fraction)||o.fraction<0||o.fraction>.90)throw std::invalid_argument("fraction must be 0..0.90");}
 else if(key=="--layout"){o.layout_name=value;if(value=="linear")o.layout=Layout::linear;else if(value=="morton8")o.layout=Layout::morton8;else throw std::invalid_argument("unknown layout");}
 else if(key=="--inject"){if(value!="none"&&value!="program"&&value!="output")throw std::invalid_argument("unknown injection");o.injection=value;}
 else throw std::invalid_argument("unknown option: "+key);
 }
 if(o.bank.empty()||o.atlas.empty()||o.out.empty()||!o.hops||o.hops>1048576)throw std::invalid_argument("bank/atlas/out and hops 1..1048576 required");return o;
}
} // program_detail

int main(int argc,char**argv){using namespace program_detail;fs::path staging;try{
 const Options o=options(argc,argv);if(fs::exists(o.out))throw std::invalid_argument("output directory exists");
 const P::Bank bank=P::load(o.bank);const Shape s=bank.shape;const u32 distinct=u32(bank.capsules.size());if(o.initial_slot>=distinct)throw std::invalid_argument("initial slot outside semantic bank");const u64 page_words=stored(s),page_bytes=mul(page_words,4),template_words=mul(page_words,distinct),template_bytes=mul(template_words,4);
 std::vector<u32> templates;templates.reserve(std::size_t(template_words));std::vector<Origin> origins;origins.reserve(distinct);
 for(const auto&capsule:bank.capsules){const auto words=P::physical_words(capsule,s,o.layout);templates.insert(templates.end(),words.begin(),words.end());origins.push_back({capsule.origin_row,capsule.origin_angle});}
 Fixture fixture(Config{shape(8,256),o.layout,Producer::provided,1},130,"mixed");load_packed_atlas(o.atlas,fixture);
 std::vector<uint4> operator_words(64);uint4 operator_checksum=make_uint4(0,0,0,0);
 for(u32 i=0;i<64;++i){const uint4 value=make_uint4(fixture.masks[0][i],fixture.masks[1][i],fixture.masks[2][i],fixture.masks[3][i]);
  if(value.x!=7||value.y!=7||value.z!=6||value.w!=7)throw std::invalid_argument("required dense 1 KiB NOR-site SDF operator atlas");operator_words[i]=value;operator_checksum.x^=value.x;operator_checksum.y^=value.y;operator_checksum.z^=value.z;operator_checksum.w^=value.w;}
 const auto device=inspect(int(o.device));const u64 reserve=mul(o.reserve_mib,1ull<<20),margin=32ull<<20;
 if(device.free<=reserve)throw std::runtime_error("resource_refused: current free VRAM below reserve");
 u64 admitted=std::min(u64(device.free)-reserve,o.fraction>0?u64(double(device.free)*o.fraction):u64(device.free));
 const u64 segment_max_bytes=std::min({128ull<<20,mul(u64(device.prop.maxTexture1DLinear),4),mul(u64(INT_MAX),4)}),slots_per_segment=segment_max_bytes/page_bytes;
 if(!slots_per_segment||page_words>u64(device.prop.maxTexture1DLinear)||page_words>u64(INT_MAX))throw std::length_error("program page exceeds actual texture addressing capacity");
 const u64 trace_bytes=mul(o.hops,sizeof(Hop));u64 fixed=add(template_bytes,add(mul(distinct,sizeof(Origin)),add(1024,add(trace_bytes,add(sizeof(BankResult),P::MAX_WIRES*4)))));
 const u64 max_segments=(admitted/page_bytes+slots_per_segment-1)/slots_per_segment;
 const u64 preliminary=add(fixed,add(margin,mul(max_segments,sizeof(SegmentView))));
 if(admitted<=preliminary)throw std::runtime_error("resource_refused: fixed resources and planning margin exceed admission");
 const u64 pool_budget=admitted-preliminary;
 const u64 requested=o.pool_mib?mul(o.pool_mib,1ull<<20):(o.fraction>0?pool_budget:template_bytes);
 if(requested>pool_budget)throw std::runtime_error("resource_refused: requested pool exceeds current free VRAM admission");
 const u64 replicas=requested/template_bytes;if(!replicas)throw std::runtime_error("resource_refused: pool cannot hold complete distinct program bank");
 const u64 pool_slots=mul(replicas,distinct),pool_bytes=mul(pool_slots,page_bytes),segment_count64=(pool_slots+slots_per_segment-1)/slots_per_segment;
 if(segment_count64>UINT32_MAX)throw std::length_error("segment directory index overflow");const u32 segment_count=u32(segment_count64);
 const u64 actual_bytes=add(fixed,add(pool_bytes,mul(segment_count,sizeof(SegmentView))));
 if(add(actual_bytes,margin)>admitted)throw std::runtime_error("resource_refused: exact segmented allocation exceeds admission");
 Buffer<u32> template_buffer(templates.size());template_buffer.upload(templates.data());Buffer<Origin> origin_buffer(origins.size());origin_buffer.upload(origins.data());
 Buffer<uint4> operator_buffer(operator_words.size());operator_buffer.upload(operator_words.data());Texture operator_texture(operator_buffer.get(),operator_words.size());
 Buffer<u32> wire_buffer(P::MAX_WIRES);Buffer<Hop> trace_buffer(o.hops);Buffer<BankResult> result_buffer(1);
 std::vector<PoolSegment> pool;pool.reserve(segment_count);std::vector<SegmentView> views;views.reserve(segment_count);
 for(u32 index=0;index<segment_count;++index){PoolSegment segment;segment.first_slot=u64(index)*slots_per_segment;segment.slots=std::min(slots_per_segment,pool_slots-segment.first_slot);
  const u64 words=mul(segment.slots,page_words);segment.memory=std::make_unique<Buffer<u32>>(std::size_t(words));segment.texture=std::make_unique<Texture>(segment.memory->get(),std::size_t(words));
  views.push_back({segment.texture->get(),segment.first_slot,segment.slots});pool.push_back(std::move(segment));}
 Buffer<SegmentView> segment_buffer(views.size());segment_buffer.upload(views.data());
 for(auto&segment:pool){const u64 words=segment.slots*page_words;fill_program_pool<<<256,256>>>(segment.memory->get(),words,template_buffer.get(),template_words,segment.first_slot*page_words);AO_CUDA(cudaGetLastError());}
 AO_CUDA(cudaDeviceSynchronize());std::size_t free_after=0,total_after=0;AO_CUDA(cudaMemGetInfo(&free_after,&total_after));
 if(free_after<reserve)throw std::runtime_error("resource_refused: reserve not retained after actual allocations");
 // Full exact readback of all admitted pool words, using a bounded host buffer.
 const u64 audit_chunk_words=1ull<<20;std::vector<u32> audit(std::size_t(std::min(audit_chunk_words,pool_bytes/4)));u64 audited=0;
 for(const auto&segment:pool)for(u64 offset=0;offset<segment.slots*page_words;offset+=audit_chunk_words){const u64 count=std::min(audit_chunk_words,segment.slots*page_words-offset);
  AO_CUDA(cudaMemcpy(audit.data(),segment.memory->get()+offset,std::size_t(count*4),cudaMemcpyDeviceToHost));
  const u64 first=segment.first_slot*page_words+offset;for(u64 i=0;i<count;++i)if(audit[std::size_t(i)]!=templates[std::size_t((first+i)%template_words)])throw std::runtime_error("pool initialization audit mismatch");audited+=count*4;}
 // Intentional regression injection completes before any reading kernel starts.
 if(o.injection=="program"){const auto&c=bank.capsules[o.initial_slot];const u32 physical=address(s,c.origin_row,c.origin_angle/32,o.layout),bit=c.origin_angle%32;
  const u64 word=u64(o.initial_slot)*page_words+physical,segment=o.initial_slot/slots_per_segment,local=word-pool[std::size_t(segment)].first_slot*page_words;
  const u32 changed=templates[std::size_t(word)]^(1u<<bit);AO_CUDA(cudaMemcpy(pool[std::size_t(segment)].memory->get()+local,&changed,4,cudaMemcpyHostToDevice));}
 AO_CUDA(cudaMemset(trace_buffer.get(),0,std::size_t(trace_bytes)));AO_CUDA(cudaMemset(result_buffer.get(),0,sizeof(BankResult)));
 AO_CUDA(cudaFuncSetAttribute(atomos_program_bank,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,atomos_program_bank));
 const bool full_sweep=pool_bytes<=mul(o.sweep_limit_mib,1ull<<20);Event start,stop;AO_CUDA(cudaEventRecord(start.get()));
 atomos_program_bank<<<1,32>>>(segment_buffer.get(),segment_count,slots_per_segment,origin_buffer.get(),s,o.layout,operator_texture.get(),distinct,pool_slots,o.replica_stride,o.initial_slot,o.input,o.hops,full_sweep?1:0,o.injection=="output"?2:0,wire_buffer.get(),trace_buffer.get(),result_buffer.get());
 AO_CUDA(cudaGetLastError());AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));float kernel_ms=0;AO_CUDA(cudaEventElapsedTime(&kernel_ms,start.get(),stop.get()));
 BankResult result{};result_buffer.download(&result);std::vector<Hop> traces(o.hops);trace_buffer.download(traces.data());
 bool verified=result.hops==o.hops&&!result.error&&result.sm_before==result.sm_after&&checksum_equal(result.operator_warm,operator_checksum)&&checksum_equal(result.operator_reread,operator_checksum);
 u32 expected_program=o.initial_slot,expected_input=o.input;u64 expected_reads=0,expected_gates=0;std::string reason;std::vector<u64> visited_slots;
 for(u32 hop=0;hop<o.hops;++hop){const auto&c=bank.capsules[expected_program];const auto&actual=traces[hop];const u32 output=P::evaluate(c,expected_input);
  const u64 physical=((u64(hop)*(o.replica_stride%replicas))%replicas)*distinct+expected_program,reads=384+(u64(c.gates.size())*2+c.output_bits)*c.ref_bits;
  visited_slots.push_back(physical);u32 page_checksum=0;if(!full_sweep)for(u64 word=0;word<page_words;++word)page_checksum^=templates[std::size_t(u64(expected_program)*page_words+word)];
  if(actual.hop!=hop||actual.program_id!=expected_program||actual.version!=c.version||actual.physical_slot!=physical||actual.input!=expected_input||actual.output!=output||actual.next_slot!=c.next_slot||actual.gate_evaluations!=c.gates.size()||actual.program_bit_reads!=reads||actual.valid!=1)verified=false;
  if(actual.page_sweep_checksum!=page_checksum)verified=false;
  expected_reads+=reads;expected_gates+=c.gates.size();expected_program=c.next_slot;expected_input=output;
 }
 if(result.final_program_id!=expected_program||result.final_input!=expected_input||result.program_bit_reads!=expected_reads||result.operator_gate_reads!=expected_gates||result.operator_sweep_reads!=128)verified=false;
 u32 pool_checksum=0;for(u32 word:templates)pool_checksum^=word;if(!(replicas&1u))pool_checksum=0;
 if(full_sweep&&(result.program_warm!=pool_checksum||result.program_reread!=pool_checksum||result.program_sweep_reads!=pool_bytes/2))verified=false;
 if(!full_sweep&&(result.program_warm||result.program_reread||result.program_sweep_reads!=mul(o.hops,page_words)))verified=false;
 std::sort(visited_slots.begin(),visited_slots.end());visited_slots.erase(std::unique(visited_slots.begin(),visited_slots.end()),visited_slots.end());const u64 swept_bytes=full_sweep?pool_bytes:mul(visited_slots.size(),page_bytes);
 if(!verified)reason="independent Boolean/chain/texture verification rejected complete proposal";
 staging=o.out;staging+=std::string(".partial_")+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());if(!fs::create_directories(staging))throw std::runtime_error("staging directory exists");
 fs::copy_file(o.bank,staging/"bank.bin");fs::copy_file(o.atlas,staging/"operators.atlas");
 {auto out=file(staging/"trace.csv");out<<"hop,program_id,version,physical_slot,input,output,next_slot,gate_evaluations,program_bit_reads,valid,page_sweep_checksum\n";
  for(const auto&r:traces)out<<r.hop<<','<<r.program_id<<','<<r.version<<','<<r.physical_slot<<','<<r.input<<','<<r.output<<','<<r.next_slot<<','<<r.gate_evaluations<<','<<r.program_bit_reads<<','<<r.valid<<','<<r.page_sweep_checksum<<'\n';}
 std::ostringstream report;report<<std::setprecision(17)<<"{\"schema\":\"atomOS-program-bank-runtime-v1\",\"concept_author\":\"Tom Klootwijk\",\"status\":"<<json_string(verified?"passed":"rejected_verification")<<",\"accepted\":"<<(verified?"true":"false")<<",\"committed\":"<<(verified?"true":"false")
  <<",\"reason\":"<<json_string(reason)<<",\"encoding\":"<<json_string(P::ENCODING)<<",\"layout\":"<<json_string(o.layout_name)<<",\"topology\":\"klein_m1_angular_twist\",\"coordinate_chart\":\"rho=log(r), angular nodes\",\"injection\":"<<json_string(o.injection)
  <<",\"hops\":"<<o.hops<<",\"hops_executed\":"<<result.hops<<",\"input_initial\":"<<o.input<<",\"initial_slot\":"<<o.initial_slot<<",\"final_program_id\":"<<result.final_program_id<<",\"final_input\":"<<result.final_input
  <<",\"committed_program_id\":"<<(verified?result.final_program_id:o.initial_slot)<<",\"committed_input\":"<<(verified?result.final_input:o.input)<<",\"device\":"<<device_record(device)
  <<",\"distinct_programs\":"<<distinct<<",\"pool_slots\":"<<pool_slots<<",\"pool_bytes\":"<<pool_bytes<<",\"program_page_bytes\":"<<page_bytes<<",\"logical_program_page_bytes\":"<<logical(s)*4<<",\"operator_texture_bytes\":1024"
  <<",\"rows\":"<<s.rows<<",\"angles\":"<<s.angles<<",\"replicas_per_program\":"<<replicas<<",\"replica_stride\":"<<o.replica_stride<<",\"segment_count\":"<<segment_count<<",\"slots_per_segment\":"<<slots_per_segment
  <<",\"sm_before\":"<<result.sm_before<<",\"sm_after\":"<<result.sm_after<<",\"texture_sweep\":"<<json_string(full_sweep?"full_pool":"visited_pages_per_hop")<<",\"program_texture_swept_bytes\":"<<swept_bytes<<",\"unique_texture_footprint_bytes\":"<<1024+swept_bytes<<",\"unique_texture_sector_floor\":"<<(1024+swept_bytes)/32<<",\"program_field_bit_reads\":"<<result.program_bit_reads<<",\"operator_gate_reads\":"<<result.operator_gate_reads
  <<",\"program_sweep_reads\":"<<result.program_sweep_reads<<",\"operator_sweep_reads\":"<<result.operator_sweep_reads<<",\"operator_warm\":"<<checksum(result.operator_warm)<<",\"operator_reread\":"<<checksum(result.operator_reread)<<",\"program_warm\":"<<result.program_warm<<",\"program_reread\":"<<result.program_reread
  <<",\"kernel_error\":"<<result.error<<",\"kernel_ms\":"<<kernel_ms<<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"static_shared_bytes_per_block\":"<<attributes.sharedSizeBytes<<",\"threads_per_block\":32,\"active_evaluator_threads\":1"
  <<",\"reserve_bytes\":"<<reserve<<",\"free_bytes_after_allocation\":"<<free_after<<",\"planning_margin_bytes\":"<<margin<<",\"actual_allocated_bytes\":"<<actual_bytes<<",\"admission_budget_bytes\":"<<admitted<<",\"pool_initialized_bytes\":"<<pool_bytes<<",\"pool_verified_bytes\":"<<audited<<",\"pool_upload_mode\":\"GPU replication of validated distinct bank\""
  <<",\"sha256_enforcement\":\"external_python_manifest_verifier_required\",\"content_hashes_checked_natively\":false,\"seed_origins_checked_natively\":true,\"structural_program_validation\":true,\"independent_boolean_chain_verification\":"<<(verified?"true":"false")
  <<",\"cache_pinning\":false,\"permanent_engine_residency\":\"not_claimed\",\"pool_allocation_is_distinct_knowledge\":false,\"native_executor_changed_during_run\":false,\"texture_inputs_mutated_during_launch\":false,\"master_seed\":"<<json_string(P::hex_digest(bank.master_seed))<<"}\n";
 write_text(staging/"summary.json",report.str());write_text(staging/(verified?"COMMITTED":"REJECTED"),verified?"Complete proposed chain accepted after independent host Boolean and resource verification.\n":"No proposed chain committed; initial program and input retained.\n");fs::rename(staging,o.out);staging.clear();std::cout<<report.str();return verified?0:2;
 }catch(const std::exception&error){std::cerr<<"atomos_program_bank: "<<error.what()<<'\n';if(!staging.empty())std::cerr<<"unpublished staging: "<<staging.string()<<'\n';return 1;}
}
