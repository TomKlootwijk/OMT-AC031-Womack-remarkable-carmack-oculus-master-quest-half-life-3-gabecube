import json,math,random,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from reference import bit_core,producer,observe,bank,wrap,address,canonical,U32,verify_run,verify_execution_metadata,verify_memory_metadata
from provenance import identity,seal_run,verify_seal,FILES
from tools.validate import find_compute_sanitizer
class ReferenceTests(unittest.TestCase):
 def a(self,**extra):return dict(dr=1.,dp=1.,alpha=0.,interval=.125,profile=0,axis_known=1,frame_known=1,increment_known=1,**extra)
 def test_morton_tile(self):self.assertEqual({address(r,w,8,'morton8') for r in range(8) for w in range(8)},set(range(64)))
 def test_morton_order(self):self.assertEqual(address(1,0,8,'morton8'),1);self.assertEqual(address(0,1,8,'morton8'),2)
 def test_absorb_not_clear(self):self.assertEqual(bit_core(255,U32,U32,128,U32,U32),(255,255,1,0))
 def test_zero(self):self.assertEqual(bit_core(0,U32,U32,U32,U32,U32),(0,0,0,0))
 def test_fringe_nonmonotone(self):self.assertEqual(bit_core(3,3,3,2,3,3)[3],0);self.assertEqual(bit_core(3,3,3,2,3,1)[3],1)
 def test_source_ratio(self):self.assertEqual(observe(self.a())['beta'],math.pi/4)
 def test_axis_unavailable(self):a=self.a();a['axis_known']=0;o=observe(a);self.assertEqual(o['status'],5);self.assertIsNone(o['raw']);self.assertIsNotNone(o['beta'])
 def test_completion_explicit(self):a=self.a();a['dr']=0;self.assertEqual(observe(a)['status'],2);a['profile']=1;self.assertEqual(observe(a)['beta'],math.pi/2)
 def test_zero_motion(self):a=self.a();a.update(dr=0,dp=0);self.assertEqual(observe(a)['status'],1)
 def test_raw_residual(self):a=self.a();a['alpha']=4;o=observe(a);self.assertLess(o['raw'],-math.pi);self.assertGreater(o['principal'],0)
 def test_bank_default(self):a=self.a();self.assertEqual([x['state'] for x in bank(a,observe(a))],[0]*6)
 def test_bank_bad_interval(self):a=self.a();a['interval']=0;self.assertEqual([x['state'] for x in bank(a,observe(a))],[0,2,0,0,0,0])
 def test_wrap_seam(self):self.assertAlmostEqual(wrap(math.radians(1-359)),math.radians(2));self.assertEqual(wrap(math.pi),-math.pi)
 def test_producer_variants(self):l={'initial_word':17,'jitter':0};self.assertEqual(producer(5,l,'shift-xor'),8);self.assertEqual(producer(5,l,'shift-or'),10);l['jitter']=U32;self.assertEqual(producer(0,l,'shift-xor'),0)
 def test_bitset_random_contraction(self):
  g=random.Random(36)
  for _ in range(500):
   x,a,n,b,v,f=[g.getrandbits(32) for _ in range(6)]
   result=bit_core(x,a,n,b,v,f)
   self.assertEqual(result[3]&~x,0)
   self.assertEqual(bit_core(result[3],a,n,b,v,f)[3],result[3])
 def test_identity_order_and_width(self):self.assertEqual(identity(['b','a']),identity(['a','b','a']));self.assertEqual(len(identity(['a'])['digest256']),64)
 def test_unicode_normalization(self):self.assertEqual(identity(['cafe\u0301']),identity(['café']))
 def test_canonical_finite(self):
  with self.assertRaises(ValueError):canonical({'x':math.nan})
 def test_seal_detects_changes(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   for n in FILES:(p/n).write_bytes(b'fixture\n')
   seal_run(p,['synthetic']);self.assertTrue(verify_seal(p));(p/'trace.csv').write_bytes(b'changed\n');self.assertFalse(verify_seal(p))
 def test_seal_refuses_replacement(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   for n in FILES:(p/n).write_bytes(b'fixture\n')
   seal_run(p,['synthetic'])
   with self.assertRaises(ValueError):seal_run(p,['synthetic'])

class ExecutionMetadataTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.run=Path(self.temp.name)/'run'
  source=Path(__file__).resolve().parents[1]/'results/cpu_matrix_evidence/1_1_provided_off_linear_texture'
  shutil.copytree(source,self.run)
 def replace_summary(self,**changes):
  path=self.run/'summary.json';s=json.loads(path.read_text());s.update(changes);path.write_text(json.dumps(s))
 def cuda_device(self):
  # Synthetic metadata for schema tests; never recorded as execution evidence.
  return dict(name='Synthetic metadata test',cc_major=12,cc_minor=0,total_bytes=12*2**30,
              free_bytes_at_start=8*2**30,runtime=12080,driver=12080,max_texture_1d_linear=2**27)
 def test_unchanged_cpu_run_matches_expected_context(self):
  self.assertEqual(verify_run(self.run,expected_backend='cpu',expected_read='host')['status'],'passed')
 def test_failed_candidate_verification_is_rejected(self):
  self.replace_summary(candidate_verification='failed')
  with self.assertRaisesRegex(ValueError,'candidate verification'):verify_run(self.run)
 def test_cpu_cannot_be_relabelled_cuda(self):
  self.replace_summary(backend='cuda')
  with self.assertRaisesRegex(ValueError,'CUDA execution metadata'):verify_run(self.run)
 def test_invalid_read_or_cpu_device_is_rejected(self):
  for patch in ({'read':'fabricated'},{'read':'host','device':{'name':'invented GPU'}}):
   with self.subTest(patch=patch):
    self.replace_summary(**patch)
    with self.assertRaisesRegex(ValueError,'CPU execution'):verify_run(self.run)
 def test_runner_context_rejects_consistent_backend_relabel(self):
  self.replace_summary(backend='cuda',read='texture',device=self.cuda_device())
  with self.assertRaisesRegex(ValueError,'requested backend'):verify_run(self.run,expected_backend='cpu',expected_read='host')
 def test_cuda_read_paths_and_optional_device_fields(self):
  device=self.cuda_device();device['optional_future_field']=17
  probe=dict(device,free_bytes_at_start=7*2**30)
  for read in ('texture','texture-packed','global'):
   with self.subTest(read=read):
    verify_execution_metadata(dict(backend='cuda',read=read,device=device,candidate_verification='passed'),
                              expected_backend='cuda',expected_read=read,expected_device=probe)
 def test_requested_read_and_probed_device_must_match(self):
  device=self.cuda_device();s=dict(backend='cuda',read='texture',device=device,candidate_verification='passed')
  with self.assertRaisesRegex(ValueError,'requested read path'):verify_execution_metadata(s,expected_read='texture-packed')
  with self.assertRaisesRegex(ValueError,'probed device'):verify_execution_metadata(s,expected_device=dict(device,name='Different device'))
 def test_cuda_device_integer_types_and_bounds(self):
  for patch in ({'cc_major':True},{'total_bytes':12.0},{'free_bytes_at_start':-1},{'runtime':0},{'name':''}):
   with self.subTest(patch=patch):
    s=dict(backend='cuda',read='texture',device=dict(self.cuda_device(),**patch),candidate_verification='passed')
    with self.assertRaises(ValueError):verify_execution_metadata(s)

class BulkMemoryMetadataTests(unittest.TestCase):
 """Synthetic schema records only: these tests are never GPU execution evidence."""
 def setUp(self):
  device=dict(name='Synthetic bulk metadata',cc_major=12,cc_minor=0)
  self.summary=dict(rows=17,angles=257,words=9,padded_rows=24,padded_words=16,epochs=1,seed=130,
                    layout='morton8',mode='recurrent',fringe=True,profile='mixed',device=device,
                    backend='cuda',read='texture-packed',execution_profile='bulk-warm-work-probe-v1',
                    allocation_layout='bulk-padded-row-major-v1',compute_ms=[0.125],
                    payload_bytes=859584,planned_bytes=67968448)
  # 384 physical records,153 logical records,46 blocks,755136 diagnostic bytes.
  self.receipt=dict(status='passed',scope='experimental_bulk_io_warm_work_retention_probe',device=device,
      rows=17,angles=257,epochs=1,seed=130,layout='morton8',mode='recurrent',fringe=True,profile='mixed',
      io='native_cp_async_bulk_1d',barrier='grid',phase_order_scope='whole_cooperative_grid',
      padding_and_tails_supported=True,device_records='padded_row_major',results='canonical_row_major',
      padded_rows=24,padded_words=16,block_size=512,tile_texels=64,grid_blocks=46,multiprocessors=46,
      active_blocks_per_sm_limit=1,shared_union_bytes=10752,input_tile_bytes=5632,result_tile_bytes=10752,
      bulk_barrier_bytes=8,max_l1_requested=True,stored_texels=384,logical_texels=153,padding_texels=231,
      chunk_texels=64,maximum_assigned_mask_bytes=1024,warm_texel_reads_per_epoch=384,
      work_texel_reads_per_epoch=153,post_texel_reads_per_epoch=384,expected_total_texel_reads_per_epoch=921,
      tiles_per_epoch=6,bulk_input_bytes_per_epoch=33792,bulk_result_bytes_per_epoch=64512,
      bulk_diagnostic_bytes_per_epoch=755136,mask_bytes=6144,payload_bytes=859584,diagnostic_bytes=755136,
      planned_bytes=67968448,verified_lane_epochs=153,candidate_verification='passed',
      checksum_scheme='per_thread_componentwise_xor',checksum_components=4,checksum_disagreements=0,
      sm_mapping_verified=True,setup_launches=1,setup_launch_verified=True,setup_checksum_verified=True,
      host_tile_coverage_verified=True,padding_output_verified_zero=True,
      timing_scope='entire_warm_bulk_io_work_probe_kernel_including_barriers_and_diagnostics',
      compute_ms=[0.125],registers_per_thread=107,local_bytes_per_thread=0,static_shared_bytes=10760,
      binary_version=120,preferred_shared_carveout=0,
      sm_mappings=[dict(launch=i,setup=i==0,before=list(range(46)),after=list(range(46))) for i in range(2)])
  self.summary['bulk_receipt']=self.receipt
 def test_padded_bulk_accounting_is_accepted(self):verify_memory_metadata(self.summary)
 def test_logical_only_payload_cannot_hide_padded_allocations(self):
  self.summary['payload_bytes']=16*384+256*153
  self.summary['planned_bytes']=self.summary['payload_bytes']+64*2**20
  with self.assertRaisesRegex(ValueError,'memory summary'):verify_memory_metadata(self.summary)
 def test_bulk_metadata_cannot_be_omitted_or_relabelled(self):
  for key,value in (('allocation_layout',None),('allocation_layout','unknown'),('execution_profile','streaming'),
                    ('backend','cpu'),('read','global')):
   with self.subTest(key=key,value=value):
    summary=dict(self.summary);summary[key]=value
    with self.assertRaises(ValueError):verify_memory_metadata(summary)
 def test_bulk_byte_counts_and_padding_claim_must_match(self):
  for key,value in (('bulk_input_bytes_per_epoch',13464),('bulk_result_bytes_per_epoch',25704),
                    ('diagnostic_bytes',754032),('padding_output_verified_zero',False),
                    ('work_texel_reads_per_epoch',384),('rows',18)):
   with self.subTest(key=key):
    summary=dict(self.summary,bulk_receipt=dict(self.receipt,**{key:value}))
    with self.assertRaisesRegex(ValueError,'bulk receipt'):verify_memory_metadata(summary)
 def test_grid_count_bool_and_duplicate_sm_ids_are_rejected(self):
  for grid in (True,0,-1):
   with self.subTest(grid=grid):
    with self.assertRaisesRegex(ValueError,'bulk grid'):verify_memory_metadata(dict(self.summary,bulk_receipt=dict(self.receipt,grid_blocks=grid)))
  self.receipt['sm_mappings'][1]['before']=[0]*46;self.receipt['sm_mappings'][1]['after']=[0]*46
  with self.assertRaisesRegex(ValueError,'SM mapping identity'):verify_memory_metadata(self.summary)
 def test_kernel_timing_scope_cannot_drop_probe_cost(self):
  self.receipt['timing_scope']='work_only'
  with self.assertRaisesRegex(ValueError,'timing_scope'):verify_memory_metadata(self.summary)

class SanitizerDiscoveryTests(unittest.TestCase):
 def test_windows_path_wrapper_resolves_native_executable(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);wrapper=root/'bin'/'compute-sanitizer.bat';native=root/'compute-sanitizer'/'compute-sanitizer.exe'
   wrapper.parent.mkdir();native.parent.mkdir();wrapper.write_text('@echo off\n');native.write_bytes(b'synthetic discovery fixture')
   with patch('tools.validate.shutil.which',return_value=str(wrapper)):
    self.assertEqual(find_compute_sanitizer(),native.resolve())
 def test_explicit_native_executable_and_missing_wrapper_target(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);native=root/'compute-sanitizer.exe';native.write_bytes(b'synthetic discovery fixture')
   self.assertEqual(find_compute_sanitizer(native),native.resolve())
   wrapper=root/'bin'/'compute-sanitizer.bat';wrapper.parent.mkdir();wrapper.write_text('@echo off\n')
   self.assertIsNone(find_compute_sanitizer(wrapper))
 def test_missing_tool_stays_unavailable(self):
  with patch('tools.validate.shutil.which',return_value=None):self.assertIsNone(find_compute_sanitizer())
if __name__=='__main__':unittest.main()
