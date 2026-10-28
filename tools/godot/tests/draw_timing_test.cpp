// Portable clock/sink controls for the exact production helper; no Godot or game.
#include "../extension/src/rta_draw_timing.h"
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include <sstream>
#include <iostream>
#include <fstream>

struct FakeClock { static uint64_t time, calls; static uint64_t now(){calls++;return ++time;} static void work(uint64_t n){time+=n;} };
uint64_t FakeClock::time=0;uint64_t FakeClock::calls=0;
struct Capture { static std::vector<std::string> lines;static void write(const char*s,size_t n){lines.emplace_back(s,n);} };
std::vector<std::string> Capture::lines;
using P=rta_draw_timing::Profile<FakeClock,Capture>;
using namespace rta_draw_timing;
static void need(bool b,const char*m){if(!b)throw std::runtime_error(m);}
static std::map<std::string,std::string> fields(const std::string& line){
    std::istringstream s(line);std::string word;s>>word;std::map<std::string,std::string> out;
    while(s>>word){auto p=word.find('=');need(p!=std::string::npos,"field without equals");need(out.emplace(word.substr(0,p),word.substr(p+1)).second,"duplicate field");}return out;
}
static uint64_t num(const std::map<std::string,std::string>&r,const char*k){return std::stoull(r.at(k));}
static void reset(){Capture::lines.clear();FakeClock::time=FakeClock::calls=0;}
static void one(P&p,uint64_t n,const char* command=nullptr,uint64_t native=0,uint32_t sim=100){
    const char* words[]={command};P::Frame f(p,n,native?native:n,sim,command?words:nullptr,command?1:0);
    FakeClock::work(10);p.mark(Graph);FakeClock::work(10);p.mark(SceneBegin);FakeClock::work(10);
    {P::Scope sky(p,BeginSky);FakeClock::work(2);}
    {P::Scope models(p,BeginModels);FakeClock::work(3);}
    {P::Scope warm(p,BeginWarm);FakeClock::work(4);}
    {P::Scope world(p,BeginWorld);FakeClock::work(5);}
    {P::Scope fill(p,BeginFill);FakeClock::work(6);}
    p.mark(WorldWait);
    FakeClock::work(10);p.mark(Traversal);
    {P::Scope scene(p,SceneTake);{P::Scope pre(p,ScenePre);FakeClock::work(2);}
      FakeClock::work(20);{P::Scope batch(p,BatchTake);FakeClock::work(10);
      {P::Scope material(p,Material);FakeClock::work(15);p.add(MaterialHit);}
      {P::Scope pack(p,BatchPack);FakeClock::work(25);pack.seal();pack.seal();}
      {P::Scope learn(p,Learn);FakeClock::work(5);p.add(LearnCalls);p.add(FillCalls);}
      p.add(BatchAccepted);p.add(PackCorners,3);p.add(PackBytes,132);}
      {P::Scope geometry(p,Geometry);p.add(PacketPrepared);FakeClock::work(9);
       {P::Scope probe(p,KeptProbe);FakeClock::work(6);p.add(KeptHit);}FakeClock::work(4);}
      {P::Scope upload(p,MeshUpload);FakeClock::work(13);}
      {P::Scope place(p,Placement);{P::Scope material(p,Material);FakeClock::work(7);p.add(MaterialHit);}
       {P::Scope caster(p,Caster);FakeClock::work(11);{P::Scope material(p,Material);FakeClock::work(3);p.add(MaterialHit);}}}}
    {P::Scope copy(p,Copy);FakeClock::work(12);{P::Scope material(p,Material);FakeClock::work(6);p.add(MaterialMiss);}}
    {P::Scope flat(p,FlatDirect);FakeClock::work(11);}
    p.mark(SceneEnd);{P::Scope flush(p,BatchFlush);FakeClock::work(8);}
    {P::Scope material(p,Material);FakeClock::work(4);p.add(MaterialHit);}
    p.mark(Rest);FakeClock::work(10);f.seal();f.seal();
}
static void disabled(){reset();P p(false);for(uint64_t i=1;i<=600;i++)one(p,i,"mark RSM_PERF_mission_START");need(FakeClock::calls==0&&Capture::lines.empty(),"disabled work observed");}
static void accounting(){reset();P p(true);one(p,1,"mark RSM_PERF_mission_START");need(Capture::lines.size()==2,"partial/cut expected");auto r=fields(Capture::lines[0]);
    need(num(r,"n")==1&&num(r,"complete")==0&&num(r,"boundary")==1&&num(r,"invalid")==0,"partial metadata");
    uint64_t top=0;for(auto k:{"textures","graph","scene_begin","world_wait","traversal","scene_end","rest"})top+=std::stoull(r.at(std::string("top_")+k+"_ns"));
    need(top==num(r,"total_ns"),"top partition");
    need(num(r,"v")==3,"schema3 output");
    uint64_t begin_sum=0;
    const char* begin_names[]={"begin_sky","begin_models","begin_warm","begin_world","begin_fill"};
    for(unsigned i=0;i<5;i++){const std::string name=begin_names[i];const uint64_t duration=i+3;
      need(std::stoull(r.at(name+"_n"))==1&&std::stoull(r.at(name+"_inc_ns"))==duration&&std::stoull(r.at(name+"_exc_ns"))==duration,"exact coarse duration/count");
      need(std::stoull(r.at("begin_"+name+"_ns"))==duration&&std::stoull(r.at("traversal_"+name+"_ns"))==0&&std::stoull(r.at("end_"+name+"_ns"))==0,"coarse context");begin_sum+=duration;}
    need(num(r,"root_scene_begin_ns")==begin_sum&&num(r,"top_scene_begin_ns")>begin_sum,"coarse root/residual");
    need(num(r,"scene_inc_ns")>num(r,"scene_exc_ns"),"nested scene");
    // Each child includes its explicit fake work plus the one tick at scope end.
    need(num(r,"material_inc_ns")==16+8+4+7+5,"material exact mock durations");
    need(num(r,"pack_inc_ns")==26&&num(r,"learn_inc_ns")==6,"pack/learn exact mock durations");
    need(num(r,"batch_inc_ns")-num(r,"batch_exc_ns")==16+26+6,"batch direct children");
    need(num(r,"pack_n")==1,"scope double seal");
    need(num(r,"root_traversal_ns")==num(r,"scene_inc_ns")+num(r,"copy_inc_ns")+num(r,"flat_inc_ns"),"root traversal overlaps");
    need(num(r,"material_n")==5&&num(r,"traversal_material_ns")<num(r,"material_inc_ns")&&num(r,"end_material_ns")>0,"global material context");
    need(num(r,"material_hit")==4&&num(r,"material_miss")==1,"hit/miss counts");
    need(num(r,"pre_inc_ns")==3&&num(r,"geometry_inc_ns")==22&&num(r,"probe_inc_ns")==7&&num(r,"geometry_exc_ns")==15,"geometry/probe exact nested mock costs");
    need(num(r,"upload_inc_ns")==14&&num(r,"place_inc_ns")==28&&num(r,"place_exc_ns")==3&&num(r,"caster_inc_ns")==17&&num(r,"caster_exc_ns")==13,"upload/placement/caster exact mock costs");
    need(num(r,"packet_prepared")==1&&num(r,"raw_prepared")==0&&num(r,"kept_hit")==1,"new branch counts");
}
static void cuts(){reset();P p(true);for(uint64_t n=1;n<=1402;n++){
    const char* cmd=n==1?"mark RSM_PERF_mission_START":n==601?"mark RSM_PERF_mission_END":n==802?"mark RSM_PERF_hub_START":n==1402?"mark RSM_PERF_hub_END":nullptr;
    one(p,n+10000,cmd,n,(uint32_t)(n<802?n:n-801));}
    unsigned full=0,cut=0;for(auto&line:Capture::lines){auto r=fields(line);if(line.find("rta_draw_cut ")==0){cut++;if(num(r,"seq")==2||num(r,"seq")==4)need(num(r,"span_n")==600&&num(r,"span_native_errors")==0&&num(r,"span_sim_decreases")==0&&num(r,"span_invalid")==0,"600 span");}
      else if(num(r,"complete")){full++;need(num(r,"n")==300&&num(r,"invalid")==0,"whole row");}}
    need(cut==4&&full==4,"two whole rows per phase");
}
static void cap(){reset();P p(true);for(uint64_t n=1;n<=19200;n++)one(p,n);auto calls=FakeClock::calls;one(p,19201,"mark RSM_PERF_hub_END");need(FakeClock::calls==calls&&Capture::lines.size()==64,"cap stops observation");need(num(fields(Capture::lines.back()),"capped")==1,"cap flag");}
static void invalid_tag(){reset();P p(true);one(p,1,"mark RSM_PERF_unknown_START");need(Capture::lines.size()==1&&Capture::lines[0].find("invalid_cut_tag")!=std::string::npos,"invalid tag failure");}
static void duplicate(){reset();P p(true);one(p,1,"mark RSM_PERF_mission_START");one(p,2,"mark RSM_PERF_mission_START");need(num(fields(Capture::lines.back()),"duplicate")==1,"duplicate labelled");}
static void native_gap(){reset();P p(true);one(p,1,"mark RSM_PERF_mission_START",1);for(uint64_t n=2;n<=601;n++)one(p,n,n==601?"mark RSM_PERF_mission_END":nullptr,n==300?299:n);
    auto r=fields(Capture::lines.back());need(num(r,"span_native_last")-1==600&&num(r,"span_native_errors")==2,"interior duplicate/gap proof");}
static void unwind(){reset();P p(true);const char* words[]={"mark RSM_PERF_mission_END"};try{P::Frame f(p,1,1,100,words,1);p.mark(Traversal);P::Scope scope(p,SceneTake);throw std::runtime_error("authored");}catch(const std::runtime_error&){}
    need(num(fields(Capture::lines[0]),"invalid")>0&&num(fields(Capture::lines.back()),"span_invalid")>0,"unwind unqualified");}
static void same_frame(){reset();P p(true);const char* words[]={"mark RSM_PERF_mission_START","mark RSM_PERF_mission_END"};{P::Frame f(p,1,1,100,words,2);f.seal();}
    auto r=fields(Capture::lines.back());need(num(r,"span_n")==0&&num(r,"span_submit_first")==0&&num(r,"span_native_first")==0,"empty cut span stale identity");}
static void set_profile_env(const char* value){
#ifdef _WIN32
    _putenv_s("RTA_DRAW_PROFILE",value);
#else
    setenv("RTA_DRAW_PROFILE",value,1);
#endif
}
static void env_gate(){
    const char* old=std::getenv("RTA_DRAW_PROFILE");const std::string saved=old?old:"";
    for(const char* value:{"","0","true","01","1 ","1"}){
        set_profile_env(value);reset();P p;one(p,1,"mark RSM_PERF_mission_START");
        need((FakeClock::calls>0)==(std::string(value)=="1"),"default environment exact gate");
    }set_profile_env(saved.c_str());
}
static void command_limit(){reset();P p(true);{P::Frame f(p,1,1,100,nullptr,257);f.seal();}need(Capture::lines.size()==1&&Capture::lines[0].find("command_limit")!=std::string::npos,"oversize commands");}
static void null_command(){reset();P p(true);const char* words[]={nullptr};{P::Frame f(p,1,1,100,words,1);f.seal();}need(Capture::lines.size()==1&&Capture::lines[0].find("null_command")!=std::string::npos,"null command");}
static void submit_gap(){reset();P p(true);one(p,1,"mark RSM_PERF_mission_START",1);one(p,3,"mark RSM_PERF_mission_END",2);need(num(fields(Capture::lines.back()),"span_submit_errors")==1,"submit gap proof");}
static void sim_reset(){reset();P p(true);one(p,1,"mark RSM_PERF_mission_START",1,100);one(p,2,"mark RSM_PERF_mission_END",2,99);need(num(fields(Capture::lines.back()),"span_sim_decreases")==1,"sim reset proof");}
static void outside_frame(){reset();P p(true);{P::Scope scope(p,Material);p.add(MaterialHit);p.mark(Graph);}need(FakeClock::calls==0&&Capture::lines.empty(),"outside frame observed");}
static void cut_cap(){reset();P p(true);for(uint64_t n=1;n<=20;n++)one(p,n,"mark RSM_PERF_mission_START");unsigned cuts=0;for(const auto& line:Capture::lines)if(line.find("rta_draw_cut ")==0){cuts++;if(cuts==16)need(num(fields(line),"cut_cap")==1,"last cut cap flag");}need(cuts==16,"cut cap bounded");}
int main(int argc,char**argv){struct Test{const char*name;void(*f)();};Test tests[]={{"disabled",disabled},{"accounting",accounting},{"cuts",cuts},{"cap",cap},{"invalid_tag",invalid_tag},{"duplicate",duplicate},{"native_gap",native_gap},{"unwind",unwind},{"same_frame",same_frame},{"env_gate",env_gate},{"command_limit",command_limit},{"null_command",null_command},{"submit_gap",submit_gap},{"sim_reset",sim_reset},{"outside_frame",outside_frame},{"cut_cap",cut_cap}};
    unsigned passed=0;for(auto&t:tests){try{t.f();passed++;std::cout<<"PASS "<<t.name<<'\n';if(argc==2){std::ofstream out(std::string(argv[1])+"/"+t.name+".rows",std::ios::binary);for(const auto&line:Capture::lines)out<<line;need(out.good(),"write emitter fixture");}}catch(const std::exception&e){std::cerr<<"FAIL "<<t.name<<": "<<e.what()<<'\n';return 1;}}
    std::cout<<"CONTROLS "<<passed<<"/"<<sizeof(tests)/sizeof(tests[0])<<"\n";return 0;}
