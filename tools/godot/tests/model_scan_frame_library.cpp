// Independently authored ABI geometry only; no game data or translated code.
// One Scene stays alive over all phases. Z is up; X/Y are the floor.
#include "rtag.h"
#include <cstring>

namespace {
enum { EMPTY, NEAR, REPEAT, MOVE, GROW, EMPTY_AFTER_GROW, SMALL_AFTER_GROW,
       HIDDEN, FAR, RETURN_NEAR, SMOOTH1_CONTROL, ZERO_CONTACT_CONTROL, RESTORE, PHASES };
int next_phase=0, emitted=0;
bool running=false;
rtag_frame frame{};
rtag_target target{1,1280,1280,1};
rtag_vertex vertices[512]{};
rtag_scene_vertex scene_vertices[512]{};
rtag_scene_full full[512]{};
float normals[512*3]{};
rtag_scene_piece pieces[64]{};
rtag_draw draws[64]{};
rtag_scene scene{};

rtag_draw& command(unsigned first,unsigned count) {
    auto& d=draws[frame.draw_count++]; d={};
    d.kind=RTAG_DRAW;d.prim=RTAG_TRIANGLES;d.target=1;d.first=first;d.count=count;
    d.scissor[2]=target.width;d.scissor[3]=target.height;d.ztst=1;d.scene_first=-1;
    return d;
}
void flat_clear() {
    const float xy[6][2]={{0,0},{1,0},{0,1},{0,1},{1,0},{1,1}};
    for(const auto& p:xy){auto& v=vertices[frame.vertex_count++];v={};v.x=p[0]*target.width;v.y=p[1]*target.height;v.z=.5f;v.q=1;v.a=128;v.fog=255;}
    command(0,6).made_by=2;
}
struct Point {float x,y,z,nx,ny,nz;};
void packet(const Point* points,unsigned count,uint32_t object,uint8_t kind,uint8_t flags,
            unsigned char r,unsigned char g,unsigned char b,uint64_t mesh) {
    const unsigned list_first=frame.vertex_count, full_first=scene.full_count;
    for(unsigned n=0;n<count;++n){
        const auto& p=points[n];const unsigned index=scene.full_count++;
        auto& f=full[index];f={};f.x=p.x;f.y=p.y;f.z=p.z;f.nx=p.nx;f.ny=p.ny;f.nz=p.nz;f.r=r;f.g=g;f.b=b;f.a=128;
        const float depth=(p.y+160.f)*.8f-(p.z-120.f)*.6f;
        const float screen_up=(p.y+160.f)*.6f+(p.z-120.f)*.8f;
        scene_vertices[index]={p.x,p.y,p.z,depth};
        normals[index*3]=p.nx;normals[index*3+1]=p.ny;normals[index*3+2]=p.nz;
        auto& v=vertices[frame.vertex_count++];v={};
        v.x=(.5f+p.x/(2.f*depth*.5773502691896257f))*target.width;
        v.y=(.5f-screen_up/(2.f*depth*.5773502691896257f))*target.height;
        v.z=.5f;v.q=1;v.r=r;v.g=g;v.b=b;v.a=128;v.fog=255;
    }
    auto& p=pieces[scene.piece_count++];p={};p.mesh=mesh;p.object=object;p.kind=kind;p.flags=flags;
    p.first=full_first;p.count=count;p.full_first=full_first;p.full_count=count;p.command=int(frame.draw_count);
    auto& d=command(list_first,count);d.made_by=1;d.scene_kind=RTAG_SCENE_EXACT;d.scene_first=int(full_first);
    d.scene_piece_first=scene.piece_count-1;d.scene_piece_count=1;d.depth_test=1;d.depth_write=1;d.ztst=2;
}
void ground() {
    const Point p[6]={{-160,-120,0,0,0,1},{160,-120,0,0,0,1},{-160,160,0,0,0,1},
                      {-160,160,0,0,0,1},{160,-120,0,0,0,1},{160,160,0,0,0,1}};
    packet(p,6,9000,1,0,205,205,205,0xF100);
}
void figure(float x,float y,float width,float height,uint32_t object,bool green=false) {
    // Shared positions have different normals in the two adjacent packets. The
    // complete frame weld must combine them before either PN patch is emitted.
    const float lo=x-width*.5f,hi=x+width*.5f;
    const Point a[3]={{lo,y,0,-.6f,-.8f,0},{hi,y,0,.6f,-.8f,0},{lo,y,height,-.3f,-.8f,.519615242f}};
    const Point b[3]={{lo,y,height,-.5f,-.8f,.331662479f},{hi,y,0,.3f,-.953939201f,0},{hi,y,height,.5f,-.8f,.331662479f}};
    packet(a,3,object,2,4,green?64:40,green?230:210,240,0xA110);
    packet(b,3,object,2,4,green?64:40,green?230:210,240,0xA111);
}
void make_frame(int phase) {
    frame={};scene={};frame.number=++emitted;frame.sim_tick=emitted;frame.aspect=1;
    frame.vertices=vertices;frame.draws=draws;frame.targets=&target;frame.target_count=1;
    frame.show_target=1;frame.show_rect[2]=target.width;frame.show_rect[3]=target.height;frame.scene=&scene;
    scene.valid=1;scene.vertices=scene_vertices;scene.normals=normals;scene.pieces=pieces;scene.full=full;
    scene.fov_y_degrees=60;scene.near_plane=.1f;scene.far_plane=2000;
    scene.camera_position[1]=-160;scene.camera_position[2]=120;
    scene.world_to_view[0]=1;scene.world_to_view[5]=-.6f;scene.world_to_view[6]=-.8f;
    scene.world_to_view[9]=.8f;scene.world_to_view[10]=-.6f;scene.world_to_view[15]=1;
    flat_clear();ground();
    if(phase==GROW){for(unsigned n=0;n<20;++n)figure(float(int(n%5)*60-120),float(int(n/5)*60-90),20,30,200+n);}
    else if(phase!=EMPTY&&phase!=EMPTY_AFTER_GROW)figure(phase==MOVE?60.f:0.f,phase==FAR?1200.f:0.f,40,50,101,phase==MOVE);
    scene.vertex_count=scene.full_count;
}
}
extern "C" {
int rtag_api_version(void){return RTAG_API_VERSION;}
int rtag_has(const char*){return 0;}
int rtag_start(const rtag_config* c){if(!c||c->struct_size!=sizeof(rtag_config))return-1;next_phase=emitted=0;running=true;return 0;}
void rtag_set_pad(int,const rtag_pad*){}
int rtag_step(const rtag_pad*,int,const rtag_frame** out){if(!out||!running||next_phase>=PHASES)return-1;make_frame(next_phase++);*out=&frame;return 1;}
int rtag_poll(int wait,const rtag_frame** out){return rtag_step(nullptr,wait,out);}
void rtag_run(double){}
void rtag_audio_pull(int16_t* out,int n){if(out&&n>0)std::memset(out,0,size_t(n)*2*sizeof(int16_t));}
const uint8_t* rtag_memory(void){return nullptr;}
uint64_t rtag_fields(void){return uint64_t(emitted);}
const char* rtag_info(void){return "authored model-scan13phase skinned/ground fixture; no game data";}
int rtag_ended(void){return !running||next_phase>=PHASES;}
int rtag_exit_code(void){return 0;}
void rtag_stop(void){running=false;}
int rtag_set_option(const char*,const char*){return 0;}
}
