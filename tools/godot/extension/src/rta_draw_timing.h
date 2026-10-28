// Opt-in submission timings. Fixed storage; no game data or Godot dependency.
#pragma once
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace rta_draw_timing {
struct Clock {
    static uint64_t now() { return (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
};
struct Sink {
    static void write(const char* text, size_t n) { std::fwrite(text, 1, n, stderr); std::fflush(stderr); }
};
enum Top { Textures, Graph, SceneBegin, WorldWait, Traversal, SceneEnd, Rest, TopCount };
enum Stage { SceneTake, BatchTake, Material, BatchPack, Learn, FlatDirect, Copy, BatchFlush, ScenePre, Geometry, KeptProbe, MeshUpload, Placement, Caster, StageCount };
enum Count { SceneHandled, BatchAccepted, BatchZero, BatchFused, PackCorners, PackBytes, MaterialHit, MaterialMiss,
             MaterialFused, LearnCalls, FillCalls, FillAttempts, SunScans, SunAccepted, PacketPrepared, RawPrepared, KeptHit, KeptUpdated, KeptCreated, TweenStopped, CountCount };

template<class C = Clock, class S = Sink> class Profile {
  public:
    static constexpr uint64_t Batch = 300, MaxRows = 64, MaxCuts = 16, MaxCommands = 256;
    struct Scope;
    struct Values {
        uint64_t total = 0, top[TopCount] = {}, inc[StageCount] = {}, exc[StageCount] = {}, calls[StageCount] = {};
        uint64_t by_top[TopCount][StageCount] = {}, roots[TopCount] = {}, count[CountCount] = {};
        uint64_t clocks = 0, invalid = 0;
    } frame, row;

    struct Scope {
        Profile* p = nullptr; Scope* parent = nullptr; Stage stage; Top phase = Textures;
        uint64_t start = 0, children = 0;
        Scope(Profile& owner, Stage what) : stage(what) {
            if (!owner.active()) return;
            p = &owner; parent = p->stack; phase = p->phase; start = p->tick(); p->stack = this;
        }
        Scope(const Scope&) = delete; Scope& operator=(const Scope&) = delete;
        void seal() {
            if (!p) return;
            const uint64_t end = p->tick();
            if (p->stack != this || p->phase != phase || end < start || end - start < children) p->frame.invalid++;
            const uint64_t elapsed = end >= start ? end - start : 0;
            p->frame.inc[stage] += elapsed; p->frame.exc[stage] += elapsed >= children ? elapsed - children : 0;
            p->frame.calls[stage]++; p->frame.by_top[phase][stage] += elapsed;
            if (parent) parent->children += elapsed; else p->frame.roots[phase] += elapsed;
            p->stack = parent;
            p = nullptr;
        }
        ~Scope() { seal(); }
    };

    class Frame {
        Profile* p = nullptr;
      public:
        Frame(Profile& owner, uint64_t submit, uint64_t native, uint32_t sim, const char* const* commands, uint32_t n) {
            if (owner.begin(submit, native, sim, commands, n)) p = &owner;
        }
        Frame(const Frame&) = delete; Frame& operator=(const Frame&) = delete;
        void seal() { if (p) { p->finish(false); p = nullptr; } }
        ~Frame() { if (p) p->finish(true); }
    };

    explicit Profile(bool enable) : enabled(enable) {}
    Profile() { const char* e = std::getenv("RTA_DRAW_PROFILE"); enabled = e && std::strcmp(e, "1") == 0; }
    bool active() const { return enabled && open; }
    void add(Count what, uint64_t n = 1) { if (active()) frame.count[what] += n; }
    void mark(Top next) {
        if (!active()) return;
        const uint64_t now = tick();
        if (now < cursor) frame.invalid++; else frame.top[phase] += now - cursor;
        if (stack) frame.invalid++;
        cursor = now; phase = next;
    }

  private:
    bool enabled = false, open = false, have_previous = false, cut_failed = false;
    Top phase = Textures;
    Scope* stack = nullptr;
    uint64_t start = 0, cursor = 0, submit = 0, native = 0, previous_submit = 0, previous_native = 0;
    uint32_t sim = 0, previous_sim = 0;
    const char* const* commands = nullptr; uint32_t command_count = 0;
    uint64_t rows = 0, row_n = 0, first_submit = 0, first_native = 0, row_native_errors = 0, row_sim_decreases = 0, row_submit_errors = 0;
    uint32_t first_sim = 0;
    uint64_t cut_rows = 0, cut_count = 0, cut_first_submit = 0, cut_first_native = 0, cut_submit_errors = 0, cut_native_errors = 0, cut_sim_decreases = 0, cut_invalid = 0;
    unsigned cut_seen = 0;
    uint64_t prior_emit_ns = 0;

    uint64_t tick() { frame.clocks++; return C::now(); }
    static void merge(Values& a, const Values& b) {
        a.total += b.total; a.clocks += b.clocks; a.invalid += b.invalid;
        for (unsigned t = 0; t < TopCount; t++) {
            a.top[t] += b.top[t]; a.roots[t] += b.roots[t];
            for (unsigned s = 0; s < StageCount; s++) a.by_top[t][s] += b.by_top[t][s];
        }
        for (unsigned s = 0; s < StageCount; s++) { a.inc[s] += b.inc[s]; a.exc[s] += b.exc[s]; a.calls[s] += b.calls[s]; }
        for (unsigned c = 0; c < CountCount; c++) a.count[c] += b.count[c];
    }
    bool begin(uint64_t ordinal, uint64_t number, uint32_t simulation, const char* const* words, uint32_t n) {
        if (!enabled) return false;
        if (open) { error("nested_frame"); return false; }
        frame = Values(); open = true; phase = Textures; stack = nullptr;
        submit = ordinal; native = number; sim = simulation; commands = words; command_count = n;
        start = cursor = tick(); return true;
    }
    void finish(bool aborted) {
        const uint64_t end = tick();
        if (end < cursor || stack || aborted) frame.invalid++;
        else frame.top[phase] += end - cursor;
        frame.total = end >= start ? end - start : 0;
        uint64_t sum = 0;
        for (unsigned t = 0; t < TopCount; t++) { sum += frame.top[t]; if (frame.roots[t] > frame.top[t]) frame.invalid++; }
        if (sum != frame.total) frame.invalid++;
        if (!row_n) { first_submit = submit; first_native = native; first_sim = sim; }
        if (have_previous) {
            if (submit != previous_submit + 1) { row_submit_errors++; cut_submit_errors++; }
            if (native != previous_native + 1) { row_native_errors++; cut_native_errors++; }
            if (sim < previous_sim) { row_sim_decreases++; cut_sim_decreases++; }
        }
        if (!cut_count) { cut_first_submit = submit; cut_first_native = native; }
        cut_count++; cut_invalid += frame.invalid;
        previous_submit = submit; previous_native = native; previous_sim = sim; have_previous = true;
        merge(row, frame); row_n++; open = false;
        if (row_n == Batch) emit(true, 0);
        // main._take_frame handles these immutable commands before calling submit.
        // Cuts flush an explicitly partial row: the following 300-submission rows begin AFTER the marker.
        observe_cuts();
    }
    void error(const char* why) {
        char line[160]; const int n = std::snprintf(line, sizeof line, "rta_draw_profile_error %s\n", why);
        if (n > 0 && (size_t)n < sizeof line) S::write(line, (size_t)n);
        enabled = false;
    }
    struct Buffer {
        char text[8192]; size_t used = 0; bool ok = true;
        template<class... A> void put(const char* fmt, A... args) {
            if (!ok) return;
            const int n = std::snprintf(text + used, sizeof text - used, fmt, args...);
            if (n < 0 || (size_t)n >= sizeof text - used) ok = false; else used += (size_t)n;
        }
    };
    void emit(bool complete, unsigned boundary) {
        if (!row_n) return;
        const uint64_t emit_start = C::now();
        using U = unsigned long long;
        Buffer b;
        b.put("rta_draw_profile v=2 row=%llu complete=%u boundary=%u n=%llu submit_first=%llu submit_last=%llu native_first=%llu native_last=%llu sim_first=%u sim_last=%u submit_errors=%llu native_errors=%llu sim_decreases=%llu invalid=%llu capped=%u total_ns=%llu clocks=%llu prior_emit_ns=%llu",
              (U)(rows+1), complete?1u:0u, boundary, (U)row_n, (U)first_submit, (U)submit, (U)first_native, (U)native,
              first_sim, sim, (U)row_submit_errors, (U)row_native_errors, (U)row_sim_decreases, (U)row.invalid,
              rows+1==MaxRows?1u:0u, (U)row.total, (U)row.clocks, (U)prior_emit_ns);
        const char* top_names[] = {"textures","graph","scene_begin","world_wait","traversal","scene_end","rest"};
        const char* names[] = {"scene","batch","material","pack","learn","flat","copy","flush","pre","geometry","probe","upload","place","caster"};
        const char* counts[] = {"scene_handled","batch_accepted","batch_zero","batch_fused","pack_corners","pack_bytes","material_hit","material_miss","material_fused","learn_calls","fill_calls","fill_attempts","sun_scans","sun_accepted","packet_prepared","raw_prepared","kept_hit","kept_updated","kept_created","tween_stopped"};
        for (unsigned t=0;t<TopCount;t++) b.put(" top_%s_ns=%llu root_%s_ns=%llu",top_names[t],(U)row.top[t],top_names[t],(U)row.roots[t]);
        for (unsigned s=0;s<StageCount;s++) b.put(" %s_n=%llu %s_inc_ns=%llu %s_exc_ns=%llu traversal_%s_ns=%llu end_%s_ns=%llu", names[s],(U)row.calls[s],names[s],(U)row.inc[s],names[s],(U)row.exc[s],names[s],(U)row.by_top[Traversal][s],names[s],(U)row.by_top[SceneEnd][s]);
        for (unsigned c=0;c<CountCount;c++) b.put(" %s=%llu",counts[c],(U)row.count[c]);
        b.put("%s", "\n");
        if (b.ok) S::write(b.text,b.used); else error("buffer_overflow");
        rows++; if(rows==MaxRows) enabled=false;
        row=Values(); row_n=0; row_submit_errors=row_native_errors=row_sim_decreases=0;
        prior_emit_ns = C::now()-emit_start;
    }
    void observe_cuts() {
        if (cut_failed || !command_count) return;
        if (!commands || command_count>MaxCommands) { error("command_limit"); cut_failed=true; return; }
        const char* words[]={"mark RSM_PERF_mission_START","mark RSM_PERF_mission_END","mark RSM_PERF_hub_START","mark RSM_PERF_hub_END"};
        for (uint32_t i=0;i<command_count;i++) {
            const char* word=commands[i]; if(!word) { error("null_command");cut_failed=true;return; }
            if(std::strncmp(word,"mark RSM_PERF_",14)!=0) continue;
            int kind=-1;for(int k=0;k<4;k++)if(std::strcmp(word,words[k])==0){kind=k;break;}
            if(kind<0){error("invalid_cut_tag");cut_failed=true;return;}
            if(row_n) emit(false,1);
            using U=unsigned long long; Buffer b;
            b.put("rta_draw_cut v=2 seq=%llu tag=%s after_submit=%llu next_submit=%llu native=%llu sim=%u enabled=%u capped=%u duplicate=%u cut_cap=%u previous_cut=%llu span_n=%llu span_submit_first=%llu span_submit_last=%llu span_native_first=%llu span_native_last=%llu span_submit_errors=%llu span_native_errors=%llu span_sim_decreases=%llu span_invalid=%llu\n",
                  (U)(cut_rows+1),words[kind]+5,(U)submit,(U)(submit+1),(U)native,sim,enabled?1u:0u,rows==MaxRows?1u:0u,(cut_seen&(1u<<kind))?1u:0u,cut_rows+1==MaxCuts?1u:0u,(U)cut_rows,
                  (U)cut_count,(U)(cut_count?cut_first_submit:0),(U)(cut_count?submit:0),(U)(cut_count?cut_first_native:0),(U)(cut_count?native:0),(U)cut_submit_errors,(U)cut_native_errors,(U)cut_sim_decreases,(U)cut_invalid);
            if(b.ok)S::write(b.text,b.used);else error("cut_buffer_overflow");
            cut_rows++;cut_seen|=1u<<kind;
            cut_count=cut_submit_errors=cut_native_errors=cut_sim_decreases=cut_invalid=0;
            if(cut_rows==MaxCuts){cut_failed=true;return;}
        }
    }
};
} // namespace rta_draw_timing
