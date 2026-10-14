"""Generate Monster #4's head mesh from Collin's renders with Hunyuan3D-2 multi-view (turbo) on the Apple GPU.
Inputs: refs/monster4/mv/{front,right,back}.png (RGBA). Output: monster4_hy3d.glb / .stl (unit box, unscaled).
Usage: hy3d_run.py [steps=5] [octree=256] [seed=1234]"""
import os, sys, time
os.environ.setdefault("HY3DGEN_MODELS", os.path.expanduser("~/Dev/hy3d_weights"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
sys.path.insert(0, os.path.expanduser("~/Dev/Hunyuan3D-2"))
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
steps = int(sys.argv[1]) if len(sys.argv) > 1 else 5
octree = int(sys.argv[2]) if len(sys.argv) > 2 else 256
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1234
views = sys.argv[4].split(",") if len(sys.argv) > 4 else ["front", "right", "back"]
dev = "mps" if torch.backends.mps.is_available() else "cpu"
imgs = {k: Image.open(f"refs/monster4/mv/{k}.png").convert("RGBA") for k in views}
t0 = time.time()
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2mv", subfolder="hunyuan3d-dit-v2-mv-turbo", variant="fp16", device=dev, dtype=torch.float16)
print(f"pipeline loaded on {dev} in {time.time()-t0:.0f}s", flush=True)
t1 = time.time()
mesh = pipe(image=imgs, num_inference_steps=steps, octree_resolution=octree, num_chunks=8000, mc_algo="mc",
            generator=torch.manual_seed(seed), output_type="trimesh")[0]
print(f"generated in {time.time()-t1:.0f}s: {len(mesh.faces):,} faces, extents {mesh.extents}", flush=True)
tag = f"s{steps}_o{octree}_seed{seed}_{'-'.join(views)}"
mesh.export(f"monster4_hy3d_{tag}.glb"); mesh.export(f"monster4_hy3d_{tag}.stl"); print("wrote", tag)
