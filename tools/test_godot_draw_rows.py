from pathlib import Path
import re
import unittest
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'draw_rows_under_test', Path(__file__).parent / 'godot/tests/draw_rows.py')
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)
FIX=Path(__file__).parent / 'godot/tests/data/draw_timing'
# These are authored Python arithmetic controls derived from frozen v2 fixtures.
# They are deliberately not represented as output from a schema3 native emitter.
def synthetic_v3(line):
    line=line.replace(' v=2 ', ' v=3 ')
    if not line.startswith('rta_draw_profile '):return line
    fields=dict(bit.split('=',1)for bit in line.split()[1:])
    n=int(fields['n']);fields['root_scene_begin_ns']=str(7*n)
    fields['clocks']=str(int(fields['clocks'])+10*n)
    for s in d.OLD_STAGE:fields[f'begin_{s}_ns']='0'
    for s,cost in zip(d.BEGIN_STAGE,(1,2,1,2,1)):
        fields.update({f'{s}_n':str(n),f'{s}_inc_ns':str(cost*n),f'{s}_exc_ns':str(cost*n),
                       f'begin_{s}_ns':str(cost*n),f'traversal_{s}_ns':'0',f'end_{s}_ns':'0'})
    return 'rta_draw_profile '+' '.join(f'{key}={value}'for key,value in fields.items())+'\n'
def fixture(name):return [synthetic_v3(s)for s in(FIX/name).read_text().splitlines(True)]
LINES=fixture('cuts.rows')
ROW=next(s for s in LINES if 'complete=1 'in s)
def alter(s,key,value):
    return re.sub(r'(?<![a-z_])'+key+r'=[^\s]+',key+'='+str(value),s)
def change(s,**fields):
    for key,value in fields.items():s=alter(s,key,value)
    return s
def remove(s,key):return re.sub(r' '+key+r'=[^\s]+','',s)
class Tests(unittest.TestCase):
    def test_actual_four_cuts(self):
        r=d.phase_windows(LINES);self.assertEqual(r['phases']['mission']['submit_interval'],[10002,10602]);self.assertEqual(r['phases']['mission']['native_interval'],[2,602]);self.assertEqual(r['phases']['hub']['coverage'],1)
    def test_prefix(self):
        r=d.parse('[frame 2613] u'+ROW);self.assertEqual(r['prefix'],'[frame 2613] u');self.assertEqual(r['raw'],'[frame 2613] u'+ROW)
    def test_unrelated(self):self.assertIsNone(d.parse('ordinary log\n'))
    def test_missing(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.replace('v=3 ',''))
    def test_unknown(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.rstrip()+' extra=1\n')
    def test_duplicate(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.rstrip()+' v=3\n')
    def test_bad_separator(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.replace('v=3','v:3'))
    def test_two_markers(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.rstrip()+' '+ROW)
    def test_error(self):
        with self.assertRaises(d.Invalid):d.parse('noise rta_draw_profile_error bad\n')
    def test_malformed_reserved(self):
        with self.assertRaises(d.Invalid):d.parse('rta_draw_profileX v=1\n')
    def test_numeric(self):
        for value in ('-1','1.0','nan',2**64):
            with self.subTest(value=value),self.assertRaises(d.Invalid):d.parse(alter(ROW,'n',value))
    def test_partition(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'total_ns',1))
    def test_exclusive(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'batch_exc_ns',0))
    def test_complete(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'n',299))
    def test_counts(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'material_hit',0))
    def test_clocks(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'clocks',0))
    def test_missing_cut(self):
        with self.assertRaises(d.Invalid):d.phase_windows([s for s in LINES if 'tag=RSM_PERF_hub_END 'not in s])
    def test_duplicate_cut(self):
        with self.assertRaises(d.Invalid):d.phase_windows(LINES+[s for s in LINES if 'tag=RSM_PERF_hub_END 'in s][0:1])
    def test_row_gap(self):
        with self.assertRaises(d.Invalid):d.phase_windows([s for s in LINES if 'row=2 'not in s])
    def test_interior_native_gap(self):
        with self.assertRaises(d.Invalid):d.phase_windows([alter(s,'span_native_errors',2)if 'tag=RSM_PERF_mission_END 'in s else s for s in LINES])
    def test_interior_submit_gap(self):
        with self.assertRaises(d.Invalid):d.phase_windows([alter(s,'span_submit_errors',2)if 'tag=RSM_PERF_mission_END 'in s else s for s in LINES])
    def test_sim_reset(self):
        with self.assertRaises(d.Invalid):d.phase_windows([alter(s,'span_sim_decreases',1)if 'tag=RSM_PERF_mission_END 'in s else s for s in LINES])
    def test_before_marker(self):
        with self.assertRaises(d.Invalid):d.phase_windows([alter(s,'span_submit_first',10001)if 'tag=RSM_PERF_mission_END 'in s else s for s in LINES])
    def test_zero_span(self):
        rows=fixture('same_frame.rows');r=d.parse(rows[-1]);self.assertEqual(r['fields']['span_n'],0)
        with self.assertRaises(d.Invalid):d.parse(alter(rows[-1],'span_submit_first',1))
    def test_capped_stream(self):
        for s in fixture('cap.rows'):d.parse(s)
    def test_actual_failures(self):
        for case in ('invalid_tag','command_limit','null_command','unwind'):
            with self.subTest(case=case),self.assertRaises(d.Invalid):
                for s in fixture(case+'.rows'):d.parse(s)
    def test_old_version_record(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'v',1))
    def test_old_version_cut(self):
        cut=next(s for s in LINES if s.startswith('rta_draw_cut '))
        with self.assertRaises(d.Invalid):d.parse(alter(cut,'v',1))
    def test_mixed_version_stream(self):
        with self.assertRaises(d.Invalid):d.phase_windows([alter(s,'v',1)if 'row=2 'in s else s for s in LINES])
    def test_old_schema_version_three_rejected(self):
        old=(FIX/'legacy-schema1-first.rows').read_text().splitlines(True)[0]
        with self.assertRaises(d.Invalid):d.parse(alter(old,'v',3))
    def test_exact_new_nested_costs(self):
        r=d.parse(fixture('accounting.rows')[0])['fields']
        self.assertEqual((r['geometry_inc_ns'],r['geometry_exc_ns'],r['probe_inc_ns']),(22,15,7))
        self.assertEqual((r['place_inc_ns'],r['place_exc_ns'],r['caster_inc_ns'],r['caster_exc_ns']),(28,3,17,13))
        self.assertEqual(r['place_inc_ns']-r['place_exc_ns']-r['caster_inc_ns'],8)
    def test_geometry_branch_counter(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'raw_prepared',1))
    def test_probe_counter(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'kept_hit',301))
    def test_upload_counter(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'kept_created',301))
    def test_tween_counter(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'tween_stopped',301))
    def test_new_scope_unknown_field(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.rstrip()+' hash_n=1\n')
    def test_new_scope_missing_field(self):
        import re
        with self.assertRaises(d.Invalid):d.parse(re.sub(r' probe_exc_ns=[0-9]+','',ROW))
    def test_zero_calls_cannot_have_time(self):
        with self.assertRaises(d.Invalid):d.parse(alter(ROW,'probe_n',0))
    def test_non_ascii_corruption(self):
        with self.assertRaises(d.Invalid):d.parse(ROW.rstrip()+'\u00a0\n')
    def test_reserved_prefix_ambiguity(self):
        with self.assertRaises(d.Invalid):d.parse('rta_draw_broken '+ROW)
    def test_schema2_profile_rejected(self):
        with self.assertRaisesRegex(d.Invalid,'unsupported version'):d.parse(alter(ROW,'v',2))
        old=next(s for s in(FIX/'cuts.rows').read_text().splitlines(True)if 'complete=1 'in s)
        with self.assertRaises(d.Invalid):d.parse(old)
    def test_schema2_cut_rejected(self):
        cut=next(s for s in LINES if s.startswith('rta_draw_cut '))
        with self.assertRaisesRegex(d.Invalid,'unsupported version'):d.parse(alter(cut,'v',2))
    def test_missing_begin_context(self):
        for s in d.STAGE:
            with self.subTest(stage=s),self.assertRaises(d.Invalid):d.parse(remove(ROW,f'begin_{s}_ns'))
    def test_missing_coarse_stage_field(self):
        for s in d.BEGIN_STAGE:
            for suffix in ('n','inc_ns','exc_ns'):
                with self.subTest(stage=s,field=suffix),self.assertRaises(d.Invalid):d.parse(remove(ROW,f'{s}_{suffix}'))
    def test_duplicate_begin_field(self):
        with self.assertRaisesRegex(d.Invalid,'duplicate key'):d.parse(ROW.rstrip()+' begin_begin_sky_ns=1\n')
    def test_noninteger_begin_context(self):
        for value in ('-1','1.0','nan',2**64):
            with self.subTest(value=value),self.assertRaises(d.Invalid):d.parse(alter(ROW,'begin_begin_sky_ns',value))
    def test_old_stage_begin_forbidden(self):
        for s in d.OLD_STAGE:
            with self.subTest(stage=s),self.assertRaises(d.Invalid):d.parse(alter(ROW,f'begin_{s}_ns',1))
    def test_context_sum_exceeds_inclusive(self):
        with self.assertRaisesRegex(d.Invalid,'context exceeds inclusive'):d.parse(change(ROW,traversal_material_ns=12000,end_material_ns=1))
    def test_coarse_context_mismatch(self):
        with self.assertRaisesRegex(d.Invalid,'coarse begin nesting/context mismatch'):d.parse(alter(ROW,'begin_begin_sky_ns',299))
    def test_coarse_nesting_rejected(self):
        # Preserve total exclusive/root accounting so this reaches the coarse guard.
        with self.assertRaisesRegex(d.Invalid,'coarse begin nesting/context mismatch'):d.parse(change(ROW,begin_sky_exc_ns=299,scene_exc_ns=7801))
    def test_coarse_traversal_forbidden(self):
        with self.assertRaises(d.Invalid):d.parse(change(ROW,traversal_begin_sky_ns=1,begin_begin_sky_ns=299))
    def test_coarse_end_forbidden(self):
        with self.assertRaises(d.Invalid):d.parse(change(ROW,end_begin_sky_ns=1,begin_begin_sky_ns=299))
    def test_coarse_wrong_root(self):
        with self.assertRaisesRegex(d.Invalid,'coarse begin/root reconciliation'):d.parse(change(ROW,root_scene_begin_ns=2101,scene_exc_ns=7801))
    def test_coarse_exceeds_scene_begin(self):
        with self.assertRaisesRegex(d.Invalid,'root exceeds top'):d.parse(change(ROW,top_scene_begin_ns=2099,total_ns=77999))
    def test_too_many_coarse_calls(self):
        for s in d.BEGIN_STAGE:
            with self.subTest(stage=s),self.assertRaisesRegex(d.Invalid,'too many coarse begin calls'):d.parse(change(ROW,**{f'{s}_n':301,'clocks':16202}))
    def test_zero_coarse_calls_cannot_have_time(self):
        with self.assertRaisesRegex(d.Invalid,'time without calls'):d.parse(alter(ROW,'begin_sky_n',0))
    def test_early_invalid_camera_zero_calls_allowed(self):
        # Generic rows may stop before the five calls; do not require calls == n.
        r=d.parse(ROW)['fields'];r=dict(r)
        for s in d.BEGIN_STAGE:
            for key in (f'{s}_n',f'{s}_inc_ns',f'{s}_exc_ns',f'begin_{s}_ns'):r[key]=0
        r.update(root_scene_begin_ns=0,clocks=13200,invalid=1)
        parsed=d.parse('rta_draw_profile '+' '.join(f'{key}={value}'for key,value in r.items())+'\n')['fields']
        self.assertEqual(sum(parsed[f'{s}_n']for s in d.BEGIN_STAGE),0)
    def test_some_coarse_calls_allowed(self):
        r=d.parse(ROW)['fields'];r=dict(r)
        for s,cost in zip(d.BEGIN_STAGE,(1,2,1,2,1)):
            r.update({f'{s}_n':150,f'{s}_inc_ns':cost*150,f'{s}_exc_ns':cost*150,f'begin_{s}_ns':cost*150})
        r.update(root_scene_begin_ns=1050,clocks=14700)
        self.assertEqual(d.parse('rta_draw_profile '+' '.join(f'{key}={value}'for key,value in r.items())+'\n')['fields']['begin_sky_n'],150)
    def test_all_coarse_calls_allowed(self):
        r=d.parse(ROW)['fields'];self.assertTrue(all(r[f'{s}_n']==r['n']for s in d.BEGIN_STAGE))
    def test_coarse_summary_and_residual(self):
        coarse=d.phase_windows(LINES)['phases']['mission']['begin_coarse']
        self.assertEqual(coarse['inclusive_ns'],dict(zip(d.BEGIN_STAGE,(600,1200,600,1200,600))))
        self.assertEqual(coarse['calls'],dict.fromkeys(d.BEGIN_STAGE,600))
        self.assertEqual(coarse['inclusive_ns_per_submission'],dict(zip(d.BEGIN_STAGE,(1,2,1,2,1))))
        self.assertEqual(coarse['calls_per_submission'],dict.fromkeys(d.BEGIN_STAGE,1))
        self.assertEqual(coarse['residual_ns'],2400)
        self.assertEqual(coarse['residual_ns_per_submission'],4)
        self.assertEqual(coarse['residual_us_per_submission'],0.004)
    def test_zero_residual_allowed(self):
        rows=[change(s,top_scene_begin_ns=2100,total_ns=78000)if 'complete=1 'in s else s for s in LINES]
        self.assertEqual(d.phase_windows(rows)['phases']['mission']['begin_coarse']['residual_ns'],0)
    def test_negative_residual_rejected(self):
        rows=[change(s,top_scene_begin_ns=2099,total_ns=77999)if 'complete=1 'in s else s for s in LINES]
        with self.assertRaises(d.Invalid):d.phase_windows(rows)
    def test_partial_phase_rejected(self):
        partial=change(ROW,n=299,complete=0,boundary=1,clocks=16182,
                       **{f'{s}_n':299 for s in d.BEGIN_STAGE})
        self.assertEqual(d.parse(partial)['fields']['n'],299)
        rows=[partial if 'row=2 'in s else s for s in LINES]
        with self.assertRaisesRegex(d.Invalid,'two full contained rows required'):d.phase_windows(rows)
if __name__=='__main__':unittest.main()
