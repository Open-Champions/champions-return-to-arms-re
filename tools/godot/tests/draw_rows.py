"""Strict schema 3 reader for rta_draw_timing diagnostics; no assumed clock identities.

This is a separate versioned reader. Frozen v1/v2 evidence is not accepted.
"""
import hashlib,re
TOP=('textures','graph','scene_begin','world_wait','traversal','scene_end','rest')
OLD_STAGE=('scene','batch','material','pack','learn','flat','copy','flush','pre','geometry','probe','upload','place','caster')
BEGIN_STAGE=('begin_sky','begin_models','begin_warm','begin_world','begin_fill')
STAGE=OLD_STAGE+BEGIN_STAGE
COUNTS=('scene_handled','batch_accepted','batch_zero','batch_fused','pack_corners','pack_bytes','material_hit','material_miss','material_fused','learn_calls','fill_calls','fill_attempts','sun_scans','sun_accepted','packet_prepared','raw_prepared','kept_hit','kept_updated','kept_created','tween_stopped')
BASE=set('v row complete boundary n submit_first submit_last native_first native_last sim_first sim_last submit_errors native_errors sim_decreases invalid capped total_ns clocks prior_emit_ns'.split())
PROFILE=BASE|{f'{p}_{t}_ns'for p in ('top','root')for t in TOP}|{f'{s}_{k}'for s in STAGE for k in ('n','inc_ns','exc_ns')}|{f'{p}_{s}_ns'for p in ('begin','traversal','end')for s in STAGE}|set(COUNTS)
CUT=set('v seq tag after_submit next_submit native sim enabled capped duplicate cut_cap previous_cut span_n span_submit_first span_submit_last span_native_first span_native_last span_submit_errors span_native_errors span_sim_decreases span_invalid'.split())
TAGS=('RSM_PERF_mission_START','RSM_PERF_mission_END','RSM_PERF_hub_START','RSM_PERF_hub_END')
class Invalid(ValueError):pass
def need(ok,message):
    if not ok:raise Invalid(message)
def parse(line):
    """Only unrelated lines return None. Reserved/malformed/ambiguous diagnostics raise."""
    text=line.rstrip('\r\n')
    hits=list(re.finditer('rta_draw_',text))
    if not hits:return None
    need(len(hits)==1,'ambiguous diagnostic markers')
    offset=hits[0].start();payload=text[offset:]
    need(payload.isascii(),'non-ASCII payload')
    bits=payload.split(' ');kind=bits[0]
    need(kind in ('rta_draw_profile','rta_draw_cut'),'reserved diagnostic error/malformed stem')
    fields={}
    for bit in bits[1:]:
        need(bool(re.fullmatch(r'[a-z_]+=[^=\s]+',bit)),'malformed key/value')
        key,value=bit.split('=');need(key not in fields,'duplicate key')
        if key!='tag':
            need(bool(re.fullmatch('[0-9]+',value)),'non-integer value')
            value=int(value);need(value<2**64,'integer overflow')
        fields[key]=value
    need(set(fields)==(PROFILE if kind=='rta_draw_profile'else CUT),'unknown/missing fields')
    need(fields['v']==3,'unsupported version')
    if kind=='rta_draw_profile':
        r=fields
        need(1<=r['row']<=64 and 1<=r['n']<=300,'row range')
        need((r['complete'],r['boundary'])==((1,0)if r['n']==300 else(0,1)),'complete/partial metadata')
        need(r['capped']==int(r['row']==64),'cap metadata')
        need(sum(r[f'top_{t}_ns']for t in TOP)==r['total_ns'],'top partition')
        need(all(r[f'root_{t}_ns']<=r[f'top_{t}_ns']for t in TOP),'root exceeds top')
        need(sum(r[f'root_{t}_ns']for t in TOP)==sum(r[f'{s}_exc_ns']for s in STAGE),'exclusive/root reconciliation')
        for s in STAGE:
            need(r[f'{s}_exc_ns']<=r[f'{s}_inc_ns'],'exclusive exceeds inclusive')
            need(sum(r[f'{p}_{s}_ns']for p in ('begin','traversal','end'))<=r[f'{s}_inc_ns'],'context exceeds inclusive')
            if not r[f'{s}_n']:
                need(not any(r[f'{s}_{k}']for k in ('inc_ns','exc_ns'))and not any(r[f'{p}_{s}_ns']for p in ('begin','traversal','end')),'time without calls')
        need(all(r[f'begin_{s}_ns']==0 for s in OLD_STAGE),'old stage in scene begin')
        for s in BEGIN_STAGE:
            need(r[f'{s}_inc_ns']==r[f'{s}_exc_ns']==r[f'begin_{s}_ns'],'coarse begin nesting/context mismatch')
            need(r[f'traversal_{s}_ns']==r[f'end_{s}_ns']==0,'coarse begin outside scene begin')
            need(r[f'{s}_n']<=r['n'],'too many coarse begin calls')
        need(sum(r[f'{s}_inc_ns']for s in BEGIN_STAGE)==r['root_scene_begin_ns'],'coarse begin/root reconciliation')
        need(r['material_n']==r['material_hit']+r['material_miss'],'material count')
        need(r['material_fused']<=r['material_n']and r['batch_accepted']<=r['batch_n']and r['batch_zero']<=r['batch_accepted'],'admission count')
        need(r['batch_fused']<=r['batch_accepted']and r['fill_attempts']<=r['fill_calls']and r['sun_accepted']<=r['sun_scans']<=r['learn_calls'],'learning counts')
        need(r['learn_n']==r['learn_calls'],'learning scope/call mismatch')
        need(r['pre_n']==r['scene_n'],'scene preamble/call mismatch')
        need(r['packet_prepared']+r['raw_prepared']==r['geometry_n'],'geometry branch/call mismatch')
        need(r['probe_n']<=r['packet_prepared']and r['kept_hit']<=r['probe_n'],'kept probe/hit count')
        need(r['upload_n']<=r['geometry_n']and r['place_n']==r['upload_n']and r['caster_n']<=r['place_n'],'geometry upload/place/caster count')
        need(r['kept_updated']+r['kept_created']<=r['upload_n']and r['tween_stopped']<=r['kept_hit'],'kept upload/tween count')
        need(r['probe_inc_ns']<=r['geometry_inc_ns']and r['caster_inc_ns']<=r['place_inc_ns'],'nested scene timing')
        need(r['clocks']==8*r['n']+2*sum(r[f'{s}_n']for s in STAGE),'clock accounting')
    else:
        r=fields
        need(r['tag']in TAGS,'unknown tag')
        need(1<=r['seq']<=16 and r['previous_cut']==r['seq']-1,'cut sequence')
        need(r['next_submit']==r['after_submit']+1,'next submit')
        need(all(r[k]in(0,1)for k in ('enabled','capped','duplicate','cut_cap')),'cut boolean')
        need(r['cut_cap']==int(r['seq']==16),'cut cap')
        if not r['span_n']:need(all(r[k]==0 for k in ('span_submit_first','span_submit_last','span_native_first','span_native_last')),'stale empty span identity')
        else:need(r['span_submit_last']==r['after_submit']and r['span_native_last']==r['native'],'cut span tail')
    return {'kind':kind,'fields':fields,'prefix':text[:offset],'payload_offset':offset,'raw':line,'raw_sha256':hashlib.sha256(line.encode()).hexdigest()}
def phase_windows(lines):
    records=[r for line in lines if(r:=parse(line))is not None]
    rows=[r['fields']for r in records if r['kind']=='rta_draw_profile']
    cuts=[r['fields']for r in records if r['kind']=='rta_draw_cut']
    need([r['row']for r in rows]==list(range(1,len(rows)+1)),'row stream gap/duplicate')
    need([c['tag']for c in cuts]==list(TAGS)and[c['seq']for c in cuts]==[1,2,3,4],'four unique ordered cuts required')
    need(all(c['enabled']==1 and not any(c[k]for k in ('capped','duplicate','cut_cap'))for c in cuts),'unqualified cut')
    out={}
    for name,start,end in [('mission',cuts[0],cuts[1]),('hub',cuts[2],cuts[3])]:
        need(end['span_n']==600,'600 submitted lists required')
        need(all(end[k]==0 for k in ('span_submit_errors','span_native_errors','span_sim_decreases','span_invalid')),'interior span discontinuity')
        need(end['after_submit']-start['after_submit']==600 and end['native']-start['native']==600,'endpoint count')
        need(end['span_submit_first']==start['after_submit']+1 and end['span_native_first']==start['native']+1,'post-marker membership')
        chosen=[r for r in rows if r['submit_first']>start['after_submit']and r['submit_last']<=end['after_submit']]
        need(len(chosen)==2 and all(r['complete']==1 and r['n']==300 for r in chosen),'two full contained rows required')
        cursor=start['after_submit']+1;native_cursor=start['native']+1
        for r in chosen:
            need(not any(r[k]for k in ('submit_errors','native_errors','sim_decreases','invalid','capped')),'unqualified row')
            need(r['submit_first']==cursor and r['submit_last']==cursor+299,'submit row membership')
            need(r['native_first']==native_cursor and r['native_last']==native_cursor+299,'native row membership')
            cursor+=300;native_cursor+=300
        need(cursor==end['after_submit']+1 and native_cursor==end['native']+1,'complete coverage')
        sums={k:sum(r[k]for r in chosen)for k in PROFILE if k not in BASE}
        begin_total=sum(sums[f'{s}_inc_ns']for s in BEGIN_STAGE)
        begin_residual=sums['top_scene_begin_ns']-begin_total
        need(begin_residual>=0,'negative scene begin residual')
        out[name]={'submissions':600,'coverage':1.0,'submit_interval':[start['after_submit']+1,end['after_submit']+1],
                   'native_interval':[start['native']+1,end['native']+1],'rows':[r['row']for r in chosen],
                   'total_us_per_submission':sum(r['total_ns']for r in chosen)/600000,
                   'top_us_per_submission':{t:sums[f'top_{t}_ns']/600000 for t in TOP},
                   'begin_coarse':{'inclusive_ns':{s:sums[f'{s}_inc_ns']for s in BEGIN_STAGE},
                                   'calls':{s:sums[f'{s}_n']for s in BEGIN_STAGE},
                                   'inclusive_ns_per_submission':{s:sums[f'{s}_inc_ns']/600 for s in BEGIN_STAGE},
                                   'inclusive_us_per_submission':{s:sums[f'{s}_inc_ns']/600000 for s in BEGIN_STAGE},
                                   'calls_per_submission':{s:sums[f'{s}_n']/600 for s in BEGIN_STAGE},
                                   'residual_ns':begin_residual,'residual_ns_per_submission':begin_residual/600,
                                   'residual_us_per_submission':begin_residual/600000},
                   'sums':sums}
    return {'phases':out,'profile_rows':len(rows),'cuts':len(cuts),'prefixed_records':sum(bool(r['prefix'])for r in records)}
