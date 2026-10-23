// Independent fixtures: authored GIF A+D register packets, no game bytes.
// Empty-rectangle expectation is independently supported by PCSX2 GSState::Move
// (nested w/h-bounded pixel-copy loops), checked 2026-10-21. No emulator code copied.
// https://github.com/PCSX2/pcsx2/blob/5b6e6e23eba403b589495c1abf8266eb1309a5b1/pcsx2/GS/GSState.cpp#L3057
// This tests diagnostic classification, not heat-haze or picture fidelity.
#include "gs.h"
#include <array>
#include <cstdio>
#include <cstdlib>
using namespace render;
static int checks=0, failures=0;
static void check(bool ok,const char* label){++checks;if(!ok){++failures;printf("FAIL %s\n",label);}}
static void reg(Gs&g,unsigned addr,uint64_t val){
 uint32_t q[8]={0x8001,0x10000000,0xe,0,(uint32_t)val,(uint32_t)(val>>32),addr,0};g.gif(2,q,2);
}
static void surface(Gs&g){
 g.begin_frame();
 reg(g,0x1a,1);reg(g,0x4c,(20ull<<16)|(2ull<<24));
 reg(g,0x40,(1279ull<<16)|(447ull<<48));reg(g,0x18,0);
 reg(g,0,6);reg(g,1,0x80808080);reg(g,5,0);reg(g,5,160ull|(160ull<<16)|(1ull<<32));
 g.end_frame(0);check(!g.frame.targets.empty(),"fixture creates source target");g.begin_frame();
}
static void copy(Gs&g,unsigned sbp,unsigned dbp,unsigned w,unsigned h){
 reg(g,0x50,sbp|(20ull<<16)|(2ull<<24)|((uint64_t)dbp<<32)|(2ull<<48)|(2ull<<56));
 reg(g,0x51,5ull|(7ull<<16)|(3ull<<32)|(4ull<<48));
 reg(g,0x52,(uint64_t)w|((uint64_t)h<<32));reg(g,0x53,2);
}
static unsigned copies(Gs&g){unsigned n=0;for(auto&c:g.frame.commands)if(c.kind==CMD_COPY)++n;return n;}
int main(){
 // Hand authored canary grid independently defines the expected empty pixel region.
 for(auto wh:std::array<std::array<int,2>,3>{{{0,0},{0,8},{8,0}}}){
  std::array<unsigned,64>dest;dest.fill(0xa5c39e17);const auto before=dest;
  for(int y=0;y<wh[1];++y)for(int x=0;x<wh[0];++x)dest[y*8+x]=0x12345678;
  check(dest==before,"independent empty rectangle touches no pixels");
  for(bool known:{false,true}){
   Gs g;if(known)surface(g);else g.begin_frame();
   auto target_count=g.frame.targets.size();auto tex_count=g.frame.textures.size();auto command_count=g.frame.commands.size();
   copy(g,known?0:1024,14943,wh[0],wh[1]);
   check(g.frame.targets.size()==target_count,"empty copy creates no target");
   check(g.frame.textures.size()==tex_count,"empty copy creates no texture");
   check(g.frame.commands.size()==command_count&&copies(g)==0,"empty copy emits no command");
   check(g.stats.copies==0,"empty copy not counted as copied");
   check(g.stats.copies_skipped==0,"empty copy not counted as unsupported");
  }
 }
 {Gs g;surface(g);copy(g,0,14943,12,6);check(copies(g)==1,"nonempty source copy emitted");check(g.stats.copies==1&&g.stats.copies_skipped==0,"nonempty copy counters");const DrawCmd&c=g.frame.commands.back();check(c.copy_src[0]==5&&c.copy_src[1]==7&&c.copy_src[2]==12&&c.copy_src[3]==6,"nonempty source region unchanged");check(c.copy_dst[0]==3&&c.copy_dst[1]==4&&c.copy_dst[2]==12&&c.copy_dst[3]==6,"nonempty destination region unchanged");}
 {Gs g;g.begin_frame();copy(g,1024,14943,12,6);check(copies(g)==0&&g.stats.copies_skipped==1,"real missing source still counted");}
 {Gs g;surface(g);copy(g,0,0,12,6);check(copies(g)==0&&g.stats.copies_skipped==1,"nonempty self copy remains unsupported");}
 // A pending host-to-surface upload must still flush at a zero-area local copy.
 // Its pre-existing ordering is observable even though the local copy moves no pixels.
 {Gs g;surface(g);
  reg(g,0x50,20ull<<48);reg(g,0x51,(2ull<<32)|(3ull<<48));
  reg(g,0x52,2ull|(1ull<<32));reg(g,0x53,0);
  uint32_t image[8]={0x8001,0x08000000,0,0,0x80112233,0x80445566,0,0};g.gif(2,image,2);
  check(g.stats.surface_uploads==1,"fixture queues host-to-surface upload");
  check(g.frame.commands.empty()&&g.frame.textures.empty(),"upload is pending before empty copy");
  copy(g,0,14943,0,0);
  check(g.frame.textures.size()==1,"empty copy preserves pending-upload flush");
  check(g.frame.commands.size()==1&&copies(g)==0,"pending upload emits draw and no copy");
  check(g.frame.vertices.size()==6,"pending upload retains six vertices");
  if(g.frame.textures.size()==1){
   const auto&t=g.frame.textures[0];
   check(t.width==2&&t.height==1,"pending upload retains dimensions");
   check(t.rgba==std::vector<uint8_t>({0x33,0x22,0x11,0x80,0x66,0x55,0x44,0x80}),"pending upload retains authored RGBA");
  }else{check(false,"pending upload retains dimensions");check(false,"pending upload retains authored RGBA");}
  g.end_frame(1);check(g.frame.commands.size()==1&&g.frame.textures.size()==1,"frame end does not duplicate flushed upload");
  check(g.stats.copies==0&&g.stats.copies_skipped==0,"pending-upload flush does not change empty-copy accounting");
 }
 printf("RESULT checks=%d failures=%d\n",checks,failures);return failures?1:0;
}