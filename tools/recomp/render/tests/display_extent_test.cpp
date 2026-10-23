// Authored public-interface GIF/privileged-register fixtures; no game data/GPU.
// A GS framebuffer is addressed by FRAME/scissor. Prior DISPLAY naming is not a
// command to shrink a wider offscreen render surface. No emulator code copied.
#include "gs.h"
#include <cstdio>
#include <memory>
using namespace render;
static unsigned checks=0,failures=0;
static void check(bool ok,const char*name){++checks;if(!ok){++failures;fprintf(stderr,"FAIL %s\n",name);}}
static void ad(Gs&g,std::initializer_list<std::pair<uint32_t,uint64_t>>regs){std::vector<uint32_t>w={uint32_t(regs.size())|0x8000,1u<<28,14,0};for(auto r:regs)w.insert(w.end(),{uint32_t(r.second),uint32_t(r.second>>32),r.first,0});g.gif(2,w.data(),w.size()/4);}
static void display(Gs&g,uint32_t bp,bool film=false){g.privileged(0x12000000,2);g.privileged(0x12000020,film?1:3);g.privileged(0x12000090,(bp>>5)|(10ull<<9));g.privileged(0x120000a0,639ull<<32|447ull<<44);}
static void draw(Gs&g,uint32_t bp,int bw,int w,int h){
 ad(g,{{0x1a,1},{0x00,6},{0x4c,uint64_t(bp>>5)|uint64_t(bw)<<16|2ull<<24},{0x4e,1ull<<32},
 {0x40,uint64_t(w-1)<<16|uint64_t(h-1)<<48},{0x47,0x30000},{0x18,0},{0x01,0x3f80000080808080ull},
 {0x05,0},{0x05,uint64_t(w*16)|uint64_t(h*16)<<16}});
}
static void present(Gs&g,uint32_t tbp,int screen_x){
 uint64_t tex=tbp|(20ull<<14)|(2ull<<20)|(10ull<<26)|(10ull<<30)|(2ull<<35)|(1ull<<61);
 ad(g,{{0x00,0x116},{0x4c,0x118ull|10ull<<16},{0x4e,1ull<<32},{0x40,639ull<<16|223ull<<48},{0x47,0x31001},{0x18,0},{0x06,tex},{0x14,0x61},{0x01,0x3f80000000999999ull},
 {0x03,0},{0x05,uint64_t(screen_x*16)},{0x03,640ull*16|(448ull*16)<<16},{0x05,uint64_t((screen_x+320)*16)|(224ull*16)<<16}});
}
static TargetInfo target(const Gs&g,uint32_t id){TargetInfo out;for(auto&t:g.frame.targets)if(t.id==id)out=t;return out;}
static std::vector<DrawCmd> commands(const Gs&g){std::vector<DrawCmd>v;for(auto&c:g.frame.commands)if(c.kind==CMD_DRAW&&c.count)v.push_back(c);return v;}
int main(){
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,20,1280,448);present(*g,0,0);present(*g,320,320);g->end_frame(1);
  auto a=target(*g,1),b=target(*g,2);auto c=commands(*g);
  check(a.width==1280&&a.height==448,"historic name does not shrink explicit wider framebuffer");
  check(b.width==640&&b.height==224&&b.screen,"current display keeps640x224");
  check(c.size()==3,"wide clear and two present commands retained");
  DrawCmd left=c.size()>1?c[1]:DrawCmd{},right=c.size()>2?c[2]:DrawCmd{};
  check(left.tex_is_target&&left.texture==1&&!left.tex_missing,"left present samples original surface");
  check(right.tex_is_target&&right.texture==1&&!right.tex_missing,"right present samples same wider surface");
  check(right.tex_offset[0]==640&&right.tex_offset[1]==0,"page10 preserves640-column source offset");
  check(right.tex_size[0]==1280&&right.tex_size[1]==448,"right present normalizes to full surface");
  check(g->frame.show_target==2&&g->frame.show_rect[2]==640&&g->frame.show_rect[3]==224,"shown rectangle remains actual display extent");
  check(g->frame.dead_targets.empty()&&g->frame.dead_textures.empty(),"no resource deletions invented");
  check(g->stats.texture_missing==0,"historic wider present has no missing texture");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,20,1280,448);draw(*g,0,20,320,112);present(*g,320,320);g->end_frame(1);
  auto a=target(*g,1);auto c=commands(*g);auto right=c.empty()?DrawCmd{}:c.back();
  check(a.width==1280&&a.height==448,"narrow later scissor does not re-shrink wider history target");
  check(right.tex_is_target&&right.texture==1&&!right.tex_missing,"right source remains valid after narrow draw");
  unsigned announcements=0;for(auto&t:g->frame.targets)if(t.id==1)announcements++;
  check(announcements==1,"wider target announced once without resize oscillation");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);draw(*g,0,20,1280,448);g->end_frame(1);auto a=target(*g,1);
  check(a.width==640&&a.height==224,"current display naming retains established clamp");
  check(g->frame.show_target==1&&g->frame.show_rect[2]==640&&g->frame.show_rect[3]==224,"current display show rectangle preserved");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,8960);display(*g,11200);draw(*g,8960,10,640,448);draw(*g,11200,10,640,448);g->end_frame(1);
  auto old=target(*g,1),cur=target(*g,2);
  check(old.width==640&&old.height==224,"historic true alternating display retains field height");
  check(cur.width==640&&cur.height==224,"current alternating display retains field height");
  check(g->frame.show_target==2&&g->frame.show_rect[2]==640&&g->frame.show_rect[3]==224,"alternating show target preserved");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,8960,true);display(*g,11200,true);draw(*g,8960,10,640,224);draw(*g,11200,10,640,224);g->end_frame(1);
  auto old=target(*g,1),cur=target(*g,2);
  check(old.width==640&&old.height==448,"historic film retains448-line display");
  check(cur.width==640&&cur.height==448,"current film retains448-line display");
  check(g->frame.show_rect[2]==640&&g->frame.show_rect[3]==448,"film show rectangle preserved");
  g->begin_frame();display(*g,11200,false);draw(*g,11200,10,640,448);g->end_frame(2);auto field=target(*g,2);
  check(field.width==640&&field.height==224,"film-to-field current display resizes normally");
  check(g->frame.show_rect[3]==224,"film-to-field show rectangle updates");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,10,640,448);g->end_frame(1);auto a=target(*g,1);
  check(a.width==640&&a.height==224,"no wider metadata preserves historic display dimensions");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);for(unsigned i=0;i<121;++i){g->end_frame(i);g->begin_frame();}draw(*g,0,20,1280,448);present(*g,320,320);g->end_frame(122);
  auto a=target(*g,1);auto c=commands(*g);auto right=c.empty()?DrawCmd{}:c.back();
  check(a.width==1280&&a.height==448,"expired display history retains existing wider behavior");
  check(right.tex_is_target&&right.texture==1&&!right.tex_missing,"expired history right source still resolves");
 }

 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,20,1280,448);draw(*g,0,10,640,448);g->end_frame(1);
  auto a=target(*g,1);check(a.width==640&&a.height==224,"actual FRAME stride reset restores historical display size");
  unsigned announcements=0;for(auto&x:g->frame.targets)if(x.id==1)announcements++;check(announcements==2,"stride reset emits legitimate resize");
  g->begin_frame();draw(*g,0,20,1280,448);present(*g,320,320);g->end_frame(2);auto b=target(*g,1);auto cmd=commands(*g);auto right=cmd.empty()?DrawCmd{}:cmd.back();
  check(b.width==1280&&b.height==448,"actual wider stride can return after historical display reuse");
  check(right.tex_is_target&&right.texture==1&&!right.tex_missing,"right source recovers after stride returns wide");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,20,1280,448);draw(*g,8960,10,640,224);
  ad(*g,{{0x50,8960ull|(10ull<<16)|(2ull<<24)|(10ull<<48)|(2ull<<56)},{0x51,0},{0x52,640ull|224ull<<32},{0x53,2}});g->end_frame(1);
  auto a=target(*g,1);check(a.width==640&&a.height==224,"actual copy DBW reset restores historical display size");
  check(g->stats.copies==1,"copy path and command retained");
 }
 {auto g=std::make_unique<Gs>();g->begin_frame();display(*g,0);display(*g,8960);draw(*g,0,20,1280,448);draw(*g,0,0,320,112);g->end_frame(1);auto a=target(*g,1);
  check(a.width==1280&&a.height==448,"unknown stride does not erase proved wider extent");
 }
 printf("{\"checks\":%u,\"failures\":%u,\"authored_packets\":true,\"public_interface_only\":true,\"gpu\":false}\n",checks,failures);return failures?1:0;
}
