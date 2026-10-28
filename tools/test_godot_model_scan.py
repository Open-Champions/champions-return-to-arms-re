"""Authored model/contact capture and mocked CLI controls; never starts native tools."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_spec=importlib.util.spec_from_file_location('model_scan_runner_under_test',Path(__file__).parent/'godot/tests/run_retained_base.py')
runner=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)
PHASES=('empty','near_shared_normals','repeat','move_recolour','grow20','empty_after_grow','small_after_grow','hidden','far','return_near','smooth1_control','zero_contact_texture_control','restore')
MODELS=(0,2,2,2,40,0,2,0,2,2,2,2,2)
CURVED=(0,2,2,2,40,0,2,0,0,2,0,2,2)

def digest(data): return hashlib.sha256(data).hexdigest()

def png_header(width=256,height=256):
    # Artifact header only: actual image decoding/rendering requires the GPU fixture.
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR'+width.to_bytes(4,'big')+height.to_bytes(4,'big')+b'\x08\x06\x00\x00\x00'+b'\0'*4

def contacts(index):
    if index in (0,5):return []
    if index==4:return [x for n in range(16) for x in (float(n%5*60-120),float(n//5*60-90),0.0,12.0)]
    return [60.0 if index==3 else 0.0,1200.0 if index==8 else 0.0,0.0,20.0]

class ModelScanCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='model-scan-artifacts-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.out=self.root/'captures';self.out.mkdir()
        self.report={'passed':True,'near_repeat_and_restores_full_bytes_equal':True,'empty_after_growth_full_bytes_equal':True,'curved_model_path_positive':True,
                     'requested_samples':4,'performance_qualified':False,'driver':'vulkan','cases':[],
                     'smooth1_control_differing_bytes':1,'zero_contact_texture_control_differing_bytes':1}
        models=curved=hidden=0
        for index,phase in enumerate(PHASES):
            raw=bytearray(bytes((128,128,128,255))*(256*256))
            body=index not in (0,5,7,8)
            if body:raw[:64*4]=bytes((40,210,240,255))*64
            if index==10:raw[0]=41
            if index==11:raw[128*4]=127
            data=bytes(raw)
            (self.out/(phase+'.rgba')).write_bytes(data)
            (self.out/(phase+'.png')).write_bytes(png_header())
            expected=contacts(index);models+=MODELS[index];curved+=CURVED[index];hidden+=2 if index==7 else 0
            self.report['cases'].append({'phase':phase,'frame':index+1,'passed':True,'ordered_contact_float_bytes_equal':True,'per_phase_model_curved_hidden_counts_valid':True,
                'contact_float_bytes_hex':struct.pack('<'+'f'*len(expected),*expected).hex(),'contacts':expected,'expected_contacts':expected,
                'model_smooth':1 if index==10 else 2,'model_look':True,'contacts_enabled':True,'contact_texture_intentionally_zero':index==11,
                'hidden_object101':index==7,'far_contact_only_pixel_coverage':index==8,'expected_phase_models':MODELS[index],'expected_phase_curved':CURVED[index],
                'inferred_even_model_total':models,'inferred_even_curved_total':curved,'hidden_draws_cumulative':hidden,
                'generated_curved_corners_per_list_rounded':0.0 if index==0 else 6.0,'raw_saved':True,'png_exit':0,'rgba_bytes':len(data),'raw_sha256':digest(data),
                'visible_pixels':256*256,'model_coloured_pixels':64 if body else 0})

    def rejected(self,report=None):
        valid,captures=runner.model_scan_captures(self.out,self.report if report is None else report)
        self.assertIs(valid,False);self.assertIsInstance(captures,dict)

    def test_complete_thirteen_phase_artifacts_return_all_actual_hashes(self):
        self.assertEqual(runner.MODEL_SCAN_PHASES,PHASES)
        valid,captures=runner.model_scan_captures(self.out,self.report)
        self.assertIs(valid,True)
        self.assertEqual(captures,{phase+suffix:digest((self.out/(phase+suffix)).read_bytes())for phase in PHASES for suffix in ('.png','.rgba')})
        self.assertEqual(len(captures),26)

    def test_contact_oracle_retains_first_sixteen_and_far_hidden_positions(self):
        self.assertEqual(runner.model_scan_contacts(4),contacts(4))
        self.assertEqual(len(runner.model_scan_contacts(4)),64)
        self.assertEqual(runner.model_scan_contacts(7),[0,0,0,20])
        self.assertEqual(runner.model_scan_contacts(8),[0,1200,0,20])
        self.assertEqual(runner.model_scan_contacts(5),[])

    def test_missing_reordered_duplicate_extra_or_malformed_phase_rejected(self):
        for change in ('missing','reordered','duplicate','extra','nondict'):
            report=copy.deepcopy(self.report)
            if change=='missing':report['cases'].pop()
            elif change=='reordered':report['cases'][0],report['cases'][1]=report['cases'][1],report['cases'][0]
            elif change=='duplicate':report['cases'][-1]=report['cases'][-2]
            elif change=='extra':report['cases'].append(report['cases'][-1])
            else:report['cases'][0]=None
            with self.subTest(change=change):self.rejected(report)
        for report in ([],{},'report',{'passed':True,'cases':None}):self.rejected(report)

    def test_report_and_row_flags_require_exact_booleans(self):
        report_flags=('passed','near_repeat_and_restores_full_bytes_equal','empty_after_growth_full_bytes_equal','curved_model_path_positive')
        row_flags=('passed','ordered_contact_float_bytes_equal','per_phase_model_curved_hidden_counts_valid','raw_saved','model_look','contacts_enabled')
        for names,row_index in ((report_flags,None),(row_flags,0)):
            for name in names:
                for value in (False,1,'true',None):
                    report=copy.deepcopy(self.report);target=report if row_index is None else report['cases'][row_index];target[name]=value
                    with self.subTest(name=name,value=value):self.rejected(report)
        for name in ('contact_texture_intentionally_zero','hidden_object101','far_contact_only_pixel_coverage'):
            report=copy.deepcopy(self.report);report['cases'][0][name]=0;self.rejected(report)

    def test_counter_history_frame_control_and_integer_exit_are_not_just_pass_flags(self):
        for name in ('frame','model_smooth','png_exit','rgba_bytes','expected_phase_models','expected_phase_curved','inferred_even_model_total','inferred_even_curved_total','hidden_draws_cumulative'):
            for value in (False,True,0.0,'0',None,-1):
                report=copy.deepcopy(self.report);report['cases'][7][name]=value
                with self.subTest(name=name,value=value):self.rejected(report)
        for name,value in (('generated_curved_corners_per_list_rounded',0),('model_smooth',1)):
            report=copy.deepcopy(self.report);report['cases'][1][name]=value;self.rejected(report)
        for value in (float('nan'),float('inf'),-1):
            report=copy.deepcopy(self.report);report['cases'][2]['generated_curved_corners_per_list_rounded']=value;self.rejected(report)

    def test_contact_float_bytes_and_numeric_values_checked_against_independent_oracle(self):
        for index in (4,5,7,8):
            for name,value in (('contact_float_bytes_hex','00'),('contacts',[0,0,0,20]),('expected_contacts',[True,0,0,20])):
                report=copy.deepcopy(self.report);report['cases'][index][name]=value
                if name=='contacts' and index==7:value=[0,0,0,19];report['cases'][index][name]=value
                with self.subTest(index=index,name=name):self.rejected(report)

    def test_repeat_restoration_and_empty_raw_equality_rechecked_even_with_updated_hash(self):
        for index in (2,5,6,9,12):
            path=self.out/(PHASES[index]+'.rgba');original=path.read_bytes();changed=bytes((original[0]^1,))+original[1:]
            path.write_bytes(changed);report=copy.deepcopy(self.report);report['cases'][index]['raw_sha256']=digest(changed)
            with self.subTest(index=index):self.rejected(report)
            path.write_bytes(original)

    def test_pixel_controls_require_actual_difference_and_exact_reported_byte_count(self):
        for index,key in ((10,'smooth1_control_differing_bytes'),(11,'zero_contact_texture_control_differing_bytes')):
            for value in (False,0,2,'1',None):
                report=copy.deepcopy(self.report);report[key]=value;self.rejected(report)
            path=self.out/(PHASES[index]+'.rgba');original=path.read_bytes();same=(self.out/(PHASES[1]+'.rgba')).read_bytes()
            path.write_bytes(same);report=copy.deepcopy(self.report);report['cases'][index]['raw_sha256']=digest(same);report[key]=0
            self.rejected(report);path.write_bytes(original)

    def test_visibility_is_recomputed_from_raw_pixels_and_requires_hidden_far_absence(self):
        for index in (0,1,7,8):
            report=copy.deepcopy(self.report);report['cases'][index]['model_coloured_pixels']=25;self.rejected(report)
        for index in (0,1):
            path=self.out/(PHASES[index]+'.rgba');original=path.read_bytes();black=bytes((0,0,0,255))*(256*256)
            path.write_bytes(black);report=copy.deepcopy(self.report);report['cases'][index].update(raw_sha256=digest(black),visible_pixels=0,model_coloured_pixels=0)
            self.rejected(report);path.write_bytes(original)

    def test_missing_truncated_changed_raw_and_bad_png_dimensions_rejected(self):
        for suffix in ('.png','.rgba'):
            path=self.out/(PHASES[2]+suffix);original=path.read_bytes();path.unlink();self.rejected();path.write_bytes(original)
        path=self.out/(PHASES[2]+'.rgba');original=path.read_bytes()
        for data in (b'',original[:-1],original+b'\0'):
            path.write_bytes(data);report=copy.deepcopy(self.report);report['cases'][2].update(raw_sha256=digest(data),rgba_bytes=len(data));self.rejected(report)
        path.write_bytes(original)
        path=self.out/(PHASES[2]+'.png');original=path.read_bytes()
        for data in (b'',original[:23],b'not PNG!'+original[8:],png_header(255,256),png_header(256,257)):
            path.write_bytes(data);self.rejected()
        path.write_bytes(original)

    def execute_case(self,name,report=None,import_error=False,gpu_timeout=False):
        case=self.root/name;capture=case/'captures';shutil.copytree(self.out,capture)
        (capture/'model-scan-result.json').write_text(json.dumps(self.report if report is None else report))
        spec={'fixture':'model_scan','pinned_sha256':{},'driver':'vulkan','import_command':['mock-editor-import'],'command':['mock-gpu']}
        (case/'run-result.json').write_text(json.dumps(spec))
        def owned(command,env,deadline,log):
            is_import=command==spec['import_command'];log.write_text('ERROR: rejected import\n' if is_import and import_error else 'mock actual log\n')
            return {'exit':0,'timeout':gpu_timeout and not is_import,'pid':123,'cleanup':None,'error':None,'log':str(log)}
        with patch.object(runner,'run_big_owned',side_effect=owned)as mock,contextlib.redirect_stdout(io.StringIO()):result=runner.execute(case)
        return result,json.loads((case/'run-result.json').read_text()),mock.call_count

    def test_mocked_execute_admits_complete_owned_import_gpu_and_capture_contract(self):
        code,result,calls=self.execute_case('execute-good')
        self.assertEqual((code,calls),(0,2));self.assertTrue(result['passed']);self.assertTrue(result['captures_valid']);self.assertEqual(len(result['capture_sha256']),26)

    def test_mocked_execute_declines_import_error_driver_mismatch_timeout_and_bad_contacts(self):
        code,result,calls=self.execute_case('import-error',import_error=True)
        self.assertEqual((code,calls),(1,1));self.assertFalse(result['passed'])
        bad_driver=copy.deepcopy(self.report);bad_driver['driver']='d3d12'
        bad_contacts=copy.deepcopy(self.report);bad_contacts['cases'][7]['contact_float_bytes_hex']=''
        for name,report,timeout in (('driver',bad_driver,False),('contacts',bad_contacts,False),('timeout',self.report,True)):
            code,result,calls=self.execute_case(name,report=report,gpu_timeout=timeout)
            with self.subTest(name=name):self.assertEqual((code,calls),(1,2));self.assertFalse(result['passed'])

class ModelScanPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='model-scan-cli-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.here=self.root/'repo/tools/godot/tests';self.here.mkdir(parents=True)
        self.fake_runner=self.here/'run_retained_base.py';self.fake_runner.write_text('mock runner source')
        for name in ('model_scan_frame_library.cpp','model_scan_test.gd','retained_base_frame_library.cpp'):(self.here/name).write_text('authored mock source')
        for name in ('lib/rtag.h','project/dev/retained_base_test.gd','project/shaders/gs_draw.gdshaderinc','project/shaders/atmosphere.gdshaderinc','project/shaders/er_world.gdshaderinc'):
            path=self.here.parent/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('authored mock dependency')
        self.project=self.root/'project';(self.project/'bin').mkdir(parents=True)
        for name in ('project.godot','rta_godot.gdextension'):(self.project/name).write_text('authored mock descriptor')
        (self.project/'shaders').mkdir();(self.project/'shaders/gs_draw.gdshaderinc').write_text('authored mock staged shader')
        self.engine=self.root/'mock-editor.exe';self.engine.write_bytes(b'authored mock engine')

    def prepare(self,fixture):
        out=self.root/('out-'+(fixture or 'default'))
        argv=['run','--godot',str(self.engine),'--project',str(self.project),'--cxx','mock-cxx','--out',str(out),'--prepare-only']
        if fixture is not None:argv+=['--fixture',fixture]
        def compile_only(command,**kwargs):
            self.assertEqual(command[0],'mock-cxx');Path(command[command.index('-o')+1]).write_bytes(b'authored mock ABI')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch.object(runner,'__file__',str(self.fake_runner)),patch.object(runner.sys,'argv',argv),patch.object(runner.subprocess,'run',side_effect=compile_only)as native,contextlib.redirect_stdout(io.StringIO()):
            result=runner.main()
        return result,json.loads((out/'run-result.json').read_text()),native.call_count,out

    def test_model_scan_cli_prepares_owned_bounded_import_and_empty_capture_directory(self):
        result,spec,calls,out=self.prepare('model_scan')
        self.assertEqual((result,calls),(0,1));self.assertEqual(spec['fixture'],'model_scan')
        self.assertEqual(spec['import_command'][-5:],['--editor','--quit-after','120','--frame-delay','50'])
        self.assertIn('res://dev/model_scan_test.gd',spec['command']);self.assertEqual(spec['command'][-1],str(out/'captures'))
        self.assertTrue((out/'captures').is_dir());self.assertEqual(list((out/'captures').iterdir()),[])
        self.assertIn(str(self.here/'model_scan_test.gd'),spec['pinned_sha256'])
        self.assertIn(str(self.project/'shaders/atmosphere.gdshaderinc'),spec['pinned_sha256'])

    def test_default_fixture_stays_retained_and_other_choices_remain(self):
        result,spec,calls,_=self.prepare(None)
        self.assertEqual((result,calls),(0,1));self.assertNotIn('fixture',spec)
        self.assertIn('res://dev/retained_base_test.gd',spec['command'])
        self.assertEqual(set(runner.FIXTURES),{'retained','big_raw','retained_shadow','model_scan'})

    def test_private_game_library_refused_before_any_compiler_call(self):
        (self.project/'bin/librta_game.dll').write_bytes(b'mock forbidden input')
        with self.assertRaises(SystemExit),patch.object(runner.subprocess,'run')as native,contextlib.redirect_stderr(io.StringIO()):self.prepare('model_scan')
        native.assert_not_called()

if __name__=='__main__':unittest.main()
