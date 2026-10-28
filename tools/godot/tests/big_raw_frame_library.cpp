// Independently authored RTAG ABI input. No game, disc, assets or translation.
#include "rtag.h"
#include <algorithm>
#include <cstring>
#include <vector>
#ifdef RAW_FIXTURE_SELF_TEST
#include <iostream>
#endif

namespace {
constexpr unsigned PHASES = 8;
constexpr unsigned counts[PHASES] = {98307,98307,147459,110001,0,48,98307,294912};
constexpr float offsets[PHASES][2] = {{-.025f,-.02f},{.025f,.02f},{-.02f,.025f},{.02f,-.025f},{0,0},{-.025f,.025f},{0,0},{-.015f,.015f}};
constexpr unsigned char colours[7][3] = {{255,0,0},{0,255,0},{0,0,255},{255,255,0},{0,255,255},{255,0,255},{255,255,255}};
std::vector<rtag_vertex> vertices;
std::vector<rtag_scene_vertex> world;
rtag_draw draws[2]{};
rtag_target target{1,1280,1280,1};
rtag_scene scene{};
rtag_frame frame{};
unsigned phase = 0;
bool running = false;

void vertex(float x,float y,const unsigned char* colour) {
    rtag_vertex v{}; v.x=x*target.width; v.y=y*target.height; v.z=.5f; v.q=1;
    v.r=colour[0];v.g=colour[1];v.b=colour[2];v.a=128;v.fog=255;
    vertices.push_back(v);
}
void draw(unsigned at,unsigned count,bool raw) {
    auto& d=draws[frame.draw_count++];d={};
    d.kind=RTAG_DRAW;d.prim=RTAG_TRIANGLES;d.target=1;d.first=at;d.count=count;
    d.scissor[2]=target.width;d.scissor[3]=target.height;
    d.scene_first=raw?0:-1;d.scene_kind=raw?RTAG_SCENE_DEPTH:RTAG_SCENE_NONE;
    d.made_by=raw?1:2;d.ztst=raw?2:1;d.depth_test=raw?1:0;d.depth_write=raw?1:0;
}
void make(unsigned index) {
    frame={};scene={};vertices.clear();world.clear();
    frame.number=index+1;frame.sim_tick=index+1;frame.aspect=1;
    frame.targets=&target;frame.target_count=1;frame.show_target=1;
    frame.show_rect[2]=target.width;frame.show_rect[3]=target.height;
    static const unsigned char black[3]={0,0,0};
    const float clear[6][2]={{0,0},{1,0},{0,1},{0,1},{1,0},{1,1}};
    for(const auto& p:clear)vertex(p[0],p[1],black);
    draw(0,6,false);
    const bool flat=index==5;
    const unsigned triangles=counts[index]/3;
    const float quad[6][2]={{-1,-1},{1,-1},{-1,1},{-1,1},{1,-1},{1,1}};
    for(unsigned triangle=0;triangle<triangles;++triangle){
        // Eight contiguous spatial/colour regions expose stale or missing fill ranges.
        // A production chunk boundary may split a triangle; the complete ABI remains valid.
        const unsigned tile=flat?triangle/2:std::min(7u,(triangle*8)/triangles);
        const auto* colour=colours[(tile+index*2)%7];
        const float cx=.18f+.2133333333f*(tile%4)+offsets[index][0];
        const float cy=(tile<4?.30f:.70f)+offsets[index][1];
        for(unsigned corner=0;corner<3;++corner){
            const unsigned at=(triangle%2)*3+corner;
            const float x=cx+quad[at][0]*.07f,y=cy+quad[at][1]*.11f;
            vertex(x,y,colour);
            // Same camera/projection as the established retained ABI fixture: y is depth, z up.
            world.push_back({(x-.5f)*6,3,(.5f-y)*6,3});
        }
    }
    draw(6,counts[index],!flat);
    frame.vertices=vertices.data();frame.vertex_count=static_cast<unsigned>(vertices.size());
    frame.draws=draws;frame.scene=&scene;
    scene.valid=1;scene.vertices=world.data();scene.vertex_count=static_cast<unsigned>(world.size());
    // No normals, packets or full geometry: the production raw path is mandatory.
    scene.fov_y_degrees=90;scene.near_plane=.1f;scene.far_plane=30;
    scene.world_to_view[0]=1;scene.world_to_view[6]=-1;scene.world_to_view[9]=1;scene.world_to_view[15]=1;
}
}
extern "C" {
int rtag_api_version(void){return RTAG_API_VERSION;}
int rtag_has(const char*){return 0;}
int rtag_start(const rtag_config* c){if(!c||c->struct_size!=sizeof(rtag_config))return -1;phase=0;running=true;return 0;}
void rtag_set_pad(int,const rtag_pad*){}
int rtag_step(const rtag_pad*,int,const rtag_frame** out){if(!out||!running||phase>=PHASES)return -1;make(phase++);*out=&frame;return 1;}
int rtag_poll(int wait,const rtag_frame** out){return rtag_step(nullptr,wait,out);}
void rtag_run(double){}
void rtag_audio_pull(int16_t* out,int n){if(out&&n>0)std::memset(out,0,static_cast<size_t>(n)*2*sizeof(int16_t));}
const uint8_t* rtag_memory(void){return nullptr;}
uint64_t rtag_fields(void){return phase;}
const char* rtag_info(void){return "authored eight-phase BIG raw ABI fixture; no game data";}
int rtag_ended(void){return !running||phase>=PHASES;}
int rtag_exit_code(void){return 0;}
void rtag_stop(void){running=false;}
int rtag_set_option(const char*,const char*){return 0;}
}
#ifdef RAW_FIXTURE_SELF_TEST
int main(){
    rtag_config config{};config.struct_size=sizeof(config);
    if(rtag_api_version()!=RTAG_API_VERSION||rtag_start(&config))return 1;
    for(unsigned i=0;i<PHASES;++i){
        const rtag_frame* f=nullptr;
        if(rtag_step(nullptr,-1,&f)!=1||!f||f->number!=i+1||f->draw_count!=2||f->vertex_count!=counts[i]+6)return 2;
        const auto& d=f->draws[1];
        if(d.count!=counts[i]||d.first!=6||f->scene->normals||f->scene->piece_count||f->scene->full_count)return 3;
        if(i!=5&&d.scene_kind!=RTAG_SCENE_DEPTH)return 4;
        unsigned tiles[8]{};
        const unsigned triangles=counts[i]/3;
        for(unsigned n=0;n<triangles;++n)++tiles[i==5?n/2:std::min(7u,n*8/triangles)];
        if(counts[i])for(unsigned n:tiles)if(n<2)return 5;
        std::cout<<"ABI phase="<<i<<" corners="<<d.count<<" eight_regions="<<(counts[i]?1:0)<<" no_normals_packets=1\n";
    }
    const rtag_frame* f=nullptr;if(rtag_step(nullptr,0,&f)!=-1)return 6;
    rtag_stop();std::cout<<"PASS authored ABI shape/sequence only; no production renderer executed\n";return 0;
}
#endif
