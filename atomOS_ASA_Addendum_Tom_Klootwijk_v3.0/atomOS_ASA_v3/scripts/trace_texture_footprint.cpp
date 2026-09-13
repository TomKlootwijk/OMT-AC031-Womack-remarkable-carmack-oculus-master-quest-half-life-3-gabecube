// Read-only host model of ASA table requests. This is not a CUDA cache simulator.
#include "asa/io.hpp"
#include <array>
#include <set>

namespace {
using namespace asa;
constexpr u32 sector_bytes=32,block_size=512,sample_count=65536;
enum Table : std::size_t { Image=0,Matte=1,Lens=2 };

struct Requests {
    std::array<std::set<u64>,3> sectors;
    std::array<u64,3> accesses{};
    void record(Table table,u64 byte_offset) {
        sectors[table].insert(byte_offset/sector_bytes);
        ++accesses[table];
    }
    u64 bytes()const {
        u64 result=0;
        for(const auto& table:sectors)result+=table.size()*sector_bytes;
        return result;
    }
};

struct RecordingData {
    HostData source;
    Requests& global;
    Requests& block;
    void record(Table table,u64 byte_offset)const {
        global.record(table,byte_offset);block.record(table,byte_offset);
    }
    float value(u32 k)const {record(Image,u64(k)*sizeof(float));return source.value(k);}
    u32 maskword(u32 k)const {record(Matte,u64(k)*sizeof(u32));return source.maskword(k);}
    Warp lens(u32 k)const {record(Lens,u64(k)*sizeof(Warp));return source.lens(k);}
};

void write_requests(std::ostream& out,const Requests& requests) {
    out<<"{\"image_sectors\":"<<requests.sectors[Image].size()
       <<",\"matte_sectors\":"<<requests.sectors[Matte].size()
       <<",\"lens_sectors\":"<<requests.sectors[Lens].size()
       <<",\"total_sector_bytes\":"<<requests.bytes()
       <<",\"image_accesses\":"<<requests.accesses[Image]
       <<",\"matte_accesses\":"<<requests.accesses[Matte]
       <<",\"lens_accesses\":"<<requests.accesses[Lens]<<'}';
}

void check_empty_access(const Config& config,const Fixture& fixture) {
    const double nan=std::numeric_limits<double>::quiet_NaN();
    const double inf=std::numeric_limits<double>::infinity();
    for(Sample sample:std::array<Sample,4>{{{nan,0},{1,inf},{-inf,0},{1,nan}}}) {
        Requests global,block;
        const Result actual=evaluate(sample,config,RecordingData{fixture.access(),global,block});
        const Result expected=evaluate(sample,config,fixture.access());
        compare({actual},{expected},0.);
        if(actual.flags!=InputInvalid||global.bytes()||block.bytes())
            throw std::runtime_error("nonfinite input touched a table during host trace");
    }
}

void trace_case(std::ostream& out,Layout layout,bool locality) {
    Config config;config.layout=layout;
    const Fixture fixture(config);
    check_empty_access(config,fixture);
    const auto original=make_samples(sample_count,config);
    const auto expected=cpu_run(config,fixture,original);
    SampleSchedule schedule;
    if(locality)schedule=make_locality_schedule(original,config);
    const auto& samples=locality?schedule.ordered:original;
    Requests global;
    std::vector<Requests> blocks((samples.size()+block_size-1)/block_size);
    std::vector<Result> actual(samples.size());
    for(std::size_t i=0;i<samples.size();++i)
        actual[i]=evaluate(samples[i],config,RecordingData{fixture.access(),global,blocks[i/block_size]});
    if(locality)restore_sample_order(actual,schedule);
    compare(actual,expected,0.);
    // compare() checks numerical results, flags and keys. Check the reserved
    // members too so every declared Result member matches the ordinary host run.
    for(std::size_t i=0;i<actual.size();++i)
        if(actual[i].reserved!=expected[i].reserved||actual[i].pad!=expected[i].pad)
            throw std::runtime_error("reserved result member changed during host trace");

    std::vector<u64> footprint;
    for(const auto& block:blocks)footprint.push_back(block.bytes());
    std::sort(footprint.begin(),footprint.end());
    const std::size_t n=footprint.size();
    const double median=(double(footprint[(n-1)/2])+double(footprint[n/2]))*.5;
    const std::size_t p95_index=(95*n+99)/100-1; // nearest-rank percentile
    u64 sum=0,nonempty=0;
    for(u64 bytes:footprint){sum+=bytes;nonempty+=bytes!=0;}

    out<<"{\"layout\":"<<quoted(layout==Layout::Linear?"linear":"morton")
       <<",\"sample_order\":"<<quoted(locality?"locality":"natural")
       <<",\"samples\":"<<samples.size()<<",\"block_size\":"<<block_size
       <<",\"traced_outputs_match_cpu_exactly\":true,\"nonfinite_inputs_have_no_table_accesses\":true"
       <<",\"allocated_table_bytes\":{\"image\":"<<fixture.image.size()*sizeof(float)
       <<",\"matte\":"<<fixture.mask.size()*sizeof(u32)
       <<",\"lens\":"<<fixture.warp.size()*sizeof(Warp)
       <<",\"total\":"<<required_bytes(config,0)<<"},\"global_requests\":";
    write_requests(out,global);
    out<<",\"block_summary\":{\"blocks\":"<<n<<",\"nonempty_blocks\":"<<nonempty
       <<",\"min_sector_bytes\":"<<footprint.front()<<",\"median_sector_bytes\":"<<median
       <<",\"p95_sector_bytes\":"<<footprint[p95_index]<<",\"max_sector_bytes\":"<<footprint.back()
       <<",\"mean_sector_bytes\":"<<double(sum)/double(n)<<"},\"per_block_requests\":[";
    for(std::size_t i=0;i<blocks.size();++i){if(i)out<<',';write_requests(out,blocks[i]);}
    out<<"]}";
}
}

int main(int argc,char**) {try {
    if(argc!=1)throw std::invalid_argument("usage: trace_texture_footprint (JSON is written to stdout)");
    std::cout<<std::setprecision(17)
      <<"{\"schema\":\"atomOS.ASA.v3.modeled_texture_footprint\",\"sector_bytes\":32,"
      <<"\"method\":\"Host recording accessor around unchanged asa::evaluate; separate sector sets for image, matte and lens\","
      <<"\"assumptions\":\"Each allocation begins on a 32-byte boundary, as expected for the cudaMalloc table allocations; float and Warp requests do not cross a sector boundary\","
      <<"\"limitations\":\"Requested table address footprint only: not hardware cache occupancy, transaction or miss prediction. Blocks are consecutive groups of 512 scheduled samples, not observed SM assignments. Excludes input, output, instructions and other cache traffic. No performance claim.\","
      <<"\"cases\":[";
    bool first=true;
    for(Layout layout:{Layout::Linear,Layout::Morton8})for(bool locality:{false,true}) {
        if(!first)std::cout<<',';first=false;trace_case(std::cout,layout,locality);
    }
    std::cout<<"]}\n";
    return 0;
}catch(const std::exception& error){std::cerr<<"FAIL host texture footprint: "<<error.what()<<'\n';return 1;}}
