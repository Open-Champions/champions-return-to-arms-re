// Authored packets only. Exercises Gs::gif(), frame boundaries and public FrameList.
// No private members, proprietary bytes, external runtime, or GPU.
// CLD2 loads on TEX0 write; CLD4/5 are conditional (no emulator code copied):
// https://github.com/PCSX2/pcsx2/blob/5b6e6e23eba403b589495c1abf8266eb1309a5b1/pcsx2/GS/GSClut.cpp#L164
#include "gs.h"
#include <cstdio>
#include <cstring>
#include <memory>
#include <unordered_map>
using namespace render;
static unsigned checks=0,failures=0;
static void check(bool b,const char*n){++checks;if(!b){++failures;fprintf(stderr,"FAIL %s\n",n);}}
static constexpr uint32_t TBP=0x3c00,CBP=0x3b00,A=0x8000ffff,B=0x80442211;
static uint64_t tex(uint32_t cbp=CBP){return TBP|(19ull<<20)|(1ull<<34)|(3ull<<35)|(uint64_t(cbp)<<37)|(2ull<<61);}
static void ad(Gs&g,std::initializer_list<std::pair<uint32_t,uint64_t>> r){
 std::vector<uint32_t>w={uint32_t(r.size())|0x8000,1u<<28,14,0};
 for(auto p:r)w.insert(w.end(),{uint32_t(p.second),uint32_t(p.second>>32),p.first,0});
 g.gif(2,w.data(),w.size()/4);
}
static std::vector<uint8_t> colors(uint32_t c){std::vector<uint8_t>b(1024);for(unsigned i=0;i<256;++i)memcpy(b.data()+4*i,&c,4);return b;}
static void start(Gs&g,uint32_t bp,uint32_t psm,uint32_t bw,int x,int y,int w,int h){
 ad(g,{{0x50,uint64_t(bp)<<32|uint64_t(bw)<<48|uint64_t(psm)<<56},{0x51,uint64_t(x)<<32|uint64_t(y)<<48},{0x52,uint64_t(w)|uint64_t(h)<<32},{0x53,0}});
}
static void image(Gs&g,const std::vector<uint8_t>&b){
 uint32_t q=uint32_t((b.size()+15)/16);std::vector<uint32_t>w(4+q*4);
 w[0]=q|0x8000;w[1]=2u<<26;if(!b.empty())memcpy(w.data()+4,b.data(),b.size());g.gif(2,w.data(),w.size()/4);
}
static void upload(Gs&g,uint32_t bp,uint32_t psm,int w,int h,const std::vector<uint8_t>&b){start(g,bp,psm,1,0,0,w,h);image(g,b);}
struct Fixture{
 std::unique_ptr<Gs> g=std::make_unique<Gs>();
 std::unordered_map<uint32_t,TextureData> textures;
 uint64_t frame=0;
 Fixture(){g->begin_frame();upload(*g,CBP,0,16,16,colors(A));}
 DrawCmd draw(uint64_t t=tex(),bool load=true,unsigned ctxt=0){
  uint64_t attr=0x15c|(uint64_t(ctxt)<<9);
  ad(*g,{{0x1a,1},{0x00,attr},{0x4c + ctxt,0x2140000},{0x4e + ctxt,0x200008c},
   {0x40 + ctxt,1279ull<<16|447ull<<48},{0x47 + ctxt,0x507f5},{0x01,0}});
  if(load)ad(*g,{{0x06 + ctxt,t}});
  ad(*g,{{0x03,0},{0x05,0x1000ull<<32},{0x05,512ull|0x1000ull<<32},{0x05,512ull<<16|0x1000ull<<32}});
  g->end_frame(frame++);
  for(auto&v:g->frame.textures)textures[v.id]=v;
  DrawCmd out;bool found=false;
  for(auto&v:g->frame.commands)if(v.kind==CMD_DRAW&&v.count){out=v;found=true;}
  check(found,"GIF emits completed draw");g->begin_frame();return out;
 }
 uint32_t rgba(const DrawCmd&c){auto it=textures.find(c.texture);if(it==textures.end()||it->second.rgba.size()<4)return 0;uint32_t v;memcpy(&v,it->second.rgba.data(),4);return v;}
 void resolved(const DrawCmd&c,uint32_t rgba_expected,const char*n){
  check(c.texture&&!c.tex_is_target&&!c.tex_missing,n);check(c.tex_size[0]==1&&c.tex_size[1]==1,"resolved texture is 1x1");check(rgba(c)==rgba_expected,"resolved exact RGBA");
 }
 void rejected(const DrawCmd&c,const char*n){check(!c.texture&&c.tex_missing==TBP+1,n);}
};
int main(){
 {Fixture f;auto a=f.draw();f.resolved(a,A,"supported uniform palette resolves");
  check(a.tfx==3&&a.tcc&&a.alpha_test&&a.atst==2&&a.aref==127&&a.afail==0,"alpha-rejection material preserved");
  auto again=f.draw();check(again.texture==a.texture,"content cache reuses uniform texture");
  upload(*f.g,CBP+1,0,1,1,std::vector<uint8_t>(4,7));f.rejected(f.draw(),"interior overwrite invalidates cached eligibility");
  upload(*f.g,CBP,0,16,16,colors(B));f.resolved(f.draw(),B,"fresh full upload plus TEX0 renews");
 }
 {Fixture f;upload(*f.g,CBP+2,0,1,1,std::vector<uint8_t>(4,7));f.rejected(f.draw(),"interior alias before first lookup rejects");}
 {Fixture f;upload(*f.g,CBP+4,0,1,1,std::vector<uint8_t>(4,7));f.resolved(f.draw(),A,"adjacent nonoverlap block preserved");}
 {Fixture f;auto b=colors(A);memcpy(b.data()+16*4,&B,4);
  // Replace the initial set only after a valid lookup marks it consumed.
  f.draw();upload(*f.g,CBP,0,16,16,b);upload(*f.g,TBP,19,1,1,std::vector<uint8_t>{8});
  f.resolved(f.draw(),B,"ordinary image and CSM1 index8 keep priority");
 }
 {Fixture f;f.draw();upload(*f.g,CBP,0,16,16,colors(B));
  f.rejected(f.draw(tex(),false),"VRAM replacement without TEX0 reload cannot renew CLUT proof");
  f.resolved(f.draw(),B,"same-value TEX0 write performs fresh supported load");
 }
 for(unsigned addr:{0x16u,0x17u}){
  Fixture f;f.draw();ad(*f.g,{{addr,tex()}});
  f.rejected(f.draw(tex(),false),"TEX2 from either context invalidates loaded proof");
  f.resolved(f.draw(),A,"TEX0 reload recovers after TEX2");
 }
 {Fixture f;f.draw();ad(*f.g,{{0x07,0ull}});
  f.rejected(f.draw(tex(),false),"other-context TEX0 invalidates old global CLUT proof");
  f.resolved(f.draw(),A,"context0 supported reload recovers");
 }
 {Fixture f;f.draw();ad(*f.g,{{0x07,tex()}});
  f.resolved(f.draw(tex(),false),A,"same supported load from context1 is safe globally");
 }
 for(unsigned cld:{0u,1u,3u,4u,5u,6u,7u}){
  Fixture f;f.rejected(f.draw((tex()&~(7ull<<61))|uint64_t(cld)<<61),"unsupported CLD remains missing");
 }
 {Fixture f;f.draw();start(*f.g,CBP+1,0,1,0,0,1,1);f.rejected(f.draw(),"incomplete overlapping transfer fails closed");}
 {Fixture f;f.draw();
  ad(*f.g,{{0x50,uint64_t(CBP+1)<<32|1ull<<48},{0x51,0},{0x52,1ull|1ull<<32},{0x53,2}});
  f.rejected(f.draw(),"local-copy interior destination invalidates");
 }
 {Fixture f;f.draw();
  ad(*f.g,{{0x50,uint64_t(CBP+1)<<32|8ull<<48},{0x51,0},{0x52,512ull|16ull<<32},{0x53,2}});
  upload(*f.g,CBP,0,16,16,colors(A));f.resolved(f.draw(),A,"fresh palette restored beside known surface");
  start(*f.g,CBP+1,0,8,0,0,1,1);f.rejected(f.draw(),"surface-upload early return invalidates interior alias");
 }

 // Continue actual XYZ writes without PRIM or other state changes.
 {Fixture f;
  ad(*f.g,{{0x00,0x15c},{0x4c,0x2140000},{0x4e,0x200008c},{0x40,1279ull<<16|447ull<<48},{0x47,0x507f5},{0x06,tex()}});
  auto xyz=[&](){ad(*f.g,{{0x05,0x1000ull<<32},{0x05,512ull|0x1000ull<<32},{0x05,512ull<<16|0x1000ull<<32}});};
  xyz();upload(*f.g,CBP,0,16,16,colors(B));xyz();ad(*f.g,{{0x06,tex()}});xyz();f.g->end_frame(0);
  std::vector<DrawCmd>draws;for(auto&c:f.g->frame.commands)if(c.kind==CMD_DRAW&&c.count)draws.push_back(c);
  for(auto&t:f.g->frame.textures)f.textures[t.id]=t;
  check(draws.size()==3,"no-PRIM continuation separates A, missing and reloaded B");
  DrawCmd empty;f.resolved(draws.empty()?empty:draws[0],A,"initial A actual XYZ draw");f.rejected(draws.size()<2?empty:draws[1],"B upload without TEX0 keeps fallback unsupported");f.resolved(draws.size()<3?empty:draws[2],B,"same-value TEX0 recovers with only subsequent XYZ");
 }
 {Fixture f;f.draw(); // consumes the initial palette upload
  ad(*f.g,{{0x00,3},{0x4c,uint64_t(CBP>>5)|1ull<<16},{0x4e,1ull<<32},{0x40,15ull<<16|15ull<<48},{0x47,0x30000}});
  auto xyz=[&](){ad(*f.g,{{0x05,0x1000ull<<32},{0x05,256ull|0x1000ull<<32},{0x05,256ull<<16|0x1000ull<<32}});};
  xyz();upload(*f.g,CBP,0,16,16,colors(B));xyz();
  f.rejected(f.draw(),"ordinary XYZ continuation cannot leave renewed overlapping palette eligible");
 }
 printf("{\"checks\":%u,\"failures\":%u,\"public_interface_only\":true,\"authored_packets_only\":true,\"gpu\":false}\n",checks,failures);
 return failures?1:0;
}
