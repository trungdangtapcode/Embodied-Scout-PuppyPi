"""Read-only diagnostic of recorded predictions; no product behavior change."""
import os,json,sys,hashlib,math
from pathlib import Path
import numpy as np,cv2
os.environ['CUDA_VISIBLE_DEVICES']='-1'
os.environ['YOLO_AUTOINSTALL']='false'
os.environ['YOLO_CONFIG_DIR']=str(Path('runs/diagnosis-2026-11-02/yoloe-config').resolve())
from teach_and_find.config import Settings
from teach_and_find.model_artifacts import verified_checkout,verified_weights
from teach_and_find.storage import EvidenceStore
from teach_and_find.sim.world3d import SimulatedLabWorld,PlacedObject,build_object_catalog
from teach_and_find.planner import TopologicalGraph,StationNode
from scripts.research_vision_eval import iou
cfg=Settings();v=cfg.vision
verified_checkout(v.upstream_path,v.upstream_revision,'YOLOE')
verified_checkout(v.descriptor_source,v.descriptor_revision,'DINOV2')
verified_weights(v.checkpoint,v.checkpoint_sha256,'YOLOE')
verified_weights(v.descriptor_checkpoint,v.descriptor_sha256,'DINOV2')
b=Path('runs/dual-vision-app-2026-11-01-final');runs=json.loads((b/'app-runs.json').read_text())
truth=json.loads((b/'truth.json').read_text());lookup={r['frame_id']:r for r in map(json.loads,(b/'capture-truth.jsonl').read_text().splitlines())}
# Compare visible-identical alias fixture with the genuine target under identical camera parameters.
g=TopologicalGraph();g.add_node(StationNode('station',1,(0.,2.25)));world=SimulatedLabWorld(g,cfg.camera)
world.place_station_objects([PlacedObject(build_object_catalog()['secret_box_1'],'station',(0.,2.),-90.)])
image=world.render_camera(0.,1.15,90.,pitch_rad=np.deg2rad(-10),noise_std=0,lighting_scale=1.)
alias=cv2.imread(str(b/'indistinguishable_front-0.png'))
pixel={'same_shape':image.shape==alias.shape,'identical_pixels':bool(np.array_equal(image,alias)), 'max_absolute_channel_difference':int(np.abs(image.astype(int)-alias.astype(int)).max())}
print('PIXEL',pixel,flush=True)
# Independently invoke original DINOv2 model/transform; do not use comparator.embed/compare.
import torch
from PIL import Image
torch.set_num_threads(2);torch.hub.set_dir(str(Path('runs/diagnosis-2026-11-02/dino-cache').resolve()))
sys.path.insert(0,str(Path(v.descriptor_source).resolve()))
from dinov2.data.transforms import make_classification_eval_transform
pre=make_classification_eval_transform()
model=torch.hub.load(str(Path(v.descriptor_source).resolve()),'dinov2_vits14',source='local',pretrained=True,weights=str(Path(v.descriptor_checkpoint).resolve())).eval()
@torch.inference_mode()
def original_forward(images):
 batch=torch.stack([pre(Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB))) for im in images])
 return torch.nn.functional.normalize(model(batch),dim=-1)
checks=[]
with EvidenceStore(b/'state') as store:
 refs=runs[0]['job']['result']['references']
 ref_vectors=[original_forward([store.load_image(s) for s in r['image_shas']]) for r in refs]
 for scene in ['moving','novel_angle','indistinguishable_front']:
  run=next(r for r in runs if r['scene']==scene)
  chosen=None
  for f in run['job']['result']['frames']:
   for d in f['detections']:
    if scene=='indistinguishable_front':
     if d['reference_comparison']['decision']=='supported_candidate':chosen=d;break
    elif d['reference_comparison']['reason']=='insufficient_reference_similarity':chosen=d;break
   if chosen:break
  query=original_forward([store.load_image(chosen['crop_image_sha'])])
  expected={c['object_id']:c for c in chosen['reference_comparison']['classes']}
  differences=[]
  for ref,vec in zip(refs,ref_vectors):
   independent=(query@vec.T).flatten().tolist()
   recorded=[r['cosine'] for r in expected[ref['object_id']]['per_reference']]
   differences += [abs(a-z) for a,z in zip(independent,recorded)]
  result={'scene':scene,'prompt':chosen['prompt_name'],'max_absolute_cosine_difference':max(differences),'recorded_reason':chosen['reference_comparison']['reason']}
  checks.append(result);print('DINO',result,flush=True)
# Replay actual upstream ByteTrack on the same recorded boxes with/without the custom gate.
sys.path.insert(0,str(Path(v.upstream_path).resolve()))
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.engine.results import Boxes
from types import SimpleNamespace
tracking=[]
for scene in ['moving','novel_angle']:
 run=next(r for r in runs if r['scene']==scene);result=run['job']['result'];ids=[r['object_id'] for r in result['references']];names=[r['name'] for r in result['references']]
 for policy in ['raw','recorded_dinov2_gate']:
  tracker=BYTETracker(SimpleNamespace(**{k:getattr(v,k) for k in ['track_high_thresh','track_low_thresh','new_track_thresh','track_buffer','match_thresh','fuse_score']}),frame_rate=result['provenance']['tracking_assumed_fps'])
  correct=false=total=0
  for f in result['frames']:
   dets=[d for d in f['detections'] if policy=='raw' or d['reference_comparison']['decision']=='supported_candidate']
   rows=np.asarray([[*d['xyxy'],d['model_score'],ids.index(d['prompt_object_id'])] for d in dets],dtype=np.float32).reshape(-1,6)
   tracks=tracker.update(Boxes(rows,(f['height'],f['width'])))
   cap=lookup[f['frame_id']];expected=truth['scenes'][scene][cap['index']];total+=len(expected);matched=set()
   for t in tracks:
    possibilities=[(iou(t[:4],gt['xyxy']),j) for j,gt in enumerate(expected) if j not in matched and gt['key']==names[int(t[6])]]
    ov,j=max(possibilities,default=(0.,-1))
    if ov>=.5:correct+=1;matched.add(j)
    else:false+=1
  entry={'scene':scene,'input_policy':policy,'correct_tracked_observations':correct,'false_tracked_observations':false,'ground_truth_observations':total}
  tracking.append(entry);print('TRACK',entry,flush=True)
Path('runs/diagnosis-2026-11-02/result.json').write_text(json.dumps({'scope':'read_only_diagnostic_not_a_product_change_or_general_model_benchmark','alias_pixels':pixel,'independent_dinov2':checks,'bytetrack_replay':tracking},indent=2))
