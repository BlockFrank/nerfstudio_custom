import argparse
import math
import sys
from pathlib import Path

import torch

# Nerfstudio / Tetra-NeRF imports
from tetranerf.nerfstudio.registration import tetranerf_config
from tetranerf.utils.extension import TetrahedraTracer, triangulate


def qstats(x: torch.Tensor, name: str) -> None:
    x = x.detach().reshape(-1).float().cpu()
    finite = torch.isfinite(x)
    x = x[finite]
    if x.numel() == 0:
        print(f"[{name}] no finite values")
        return
    qs = torch.tensor([0.0, 0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999, 1.0])
    vals = torch.quantile(x, qs)
    print(f"\n[{name}]")
    for q, v in zip(qs.tolist(), vals.tolist()):
        print(f"  q={q:>6.3f}: {v:.8g}")
    print(f"  mean   : {x.mean().item():.8g}")
    print(f"  std    : {x.std().item():.8g}")
    print(f"  count  : {x.numel()}")

def inspect_model_tetra_vertices(pipeline):
    print("\n=== MODEL TETRA VERTICES ===")
    verts = pipeline.model.tetrahedra_vertices.detach().cpu()
    bbox_stats(verts, "model_tetrahedra_vertices")
    
def bbox_stats(points: torch.Tensor, name: str) -> None:
    pts = points.detach().reshape(-1, 3).float().cpu()
    finite = torch.isfinite(pts).all(dim=-1)
    pts = pts[finite]
    if pts.numel() == 0:
        print(f"[{name}] no finite points")
        return
    mins = pts.min(dim=0).values
    maxs = pts.max(dim=0).values
    ctr = pts.mean(dim=0)
    ext = maxs - mins
    print(f"\n[{name}]")
    print(f"  min    : {mins.tolist()}")
    print(f"  max    : {maxs.tolist()}")
    print(f"  center : {ctr.tolist()}")
    print(f"  extent : {ext.tolist()}")
    qstats(torch.linalg.norm(pts - ctr, dim=-1), f"{name}/distance_from_mean")


def apply_transform_and_scale(points: torch.Tensor, dataparser_transform: torch.Tensor, dataparser_scale: float) -> torch.Tensor:
    """
    points: [N,3]
    dataparser_transform: expected [3,4] or [4,4]
    """
    pts = points.float()
    tf = dataparser_transform.float().cpu()

    if tf.shape == (3, 4):
        R = tf[:, :3]
        t = tf[:, 3]
    elif tf.shape == (4, 4):
        R = tf[:3, :3]
        t = tf[:3, 3]
    else:
        raise ValueError(f"Unexpected dataparser_transform shape: {tuple(tf.shape)}")

    out = (pts @ R.T) + t
    out = out * float(dataparser_scale)
    return out


def camera_centers_from_c2w(camera_to_worlds: torch.Tensor) -> torch.Tensor:
    """
    camera_to_worlds: [N,3,4] or [N,4,4]
    """
    c2w = camera_to_worlds.float().cpu()
    if c2w.shape[-2:] == (3, 4):
        return c2w[..., :3, 3]
    if c2w.shape[-2:] == (4, 4):
        return c2w[..., :3, 3]
    raise ValueError(f"Unexpected camera_to_worlds shape: {tuple(c2w.shape)}")


def tetra_volumes(vertices: torch.Tensor, cells: torch.Tensor) -> torch.Tensor:
    """
    vertices: [V,3]
    cells: [T,4]
    returns [T]
    """
    v = vertices[cells.long()]  # [T,4,3]
    a = v[:, 1] - v[:, 0]
    b = v[:, 2] - v[:, 0]
    c = v[:, 3] - v[:, 0]
    vol6 = torch.abs(torch.sum(torch.cross(a, b, dim=-1) * c, dim=-1))
    return vol6 / 6.0


def build_pipeline(data_path: str, device: str):
    cfg = tetranerf_config

    # Clone-ish behavior without mutating global registration permanently
    import copy
    cfg = copy.deepcopy(cfg)

    cfg.machine.device_type = "cuda"
    cfg.pipeline.datamanager.data = Path(data_path)
    cfg.vis = "viewer"   # keep current known-good mode
    cfg.logging.local_writer.enable = False  # reduce noise if present

    pipeline = cfg.pipeline.setup(
        device=device,
        test_mode="val",
        world_size=1,
        local_rank=0,
        grad_scaler=None,
    )
    return cfg, pipeline


def get_sparse_points_cpu(pipeline):
    """
    Tries several likely places where COLMAP / dataparser points may live.
    """
    dpo = pipeline.datamanager.train_dataparser_outputs

    candidates = []

    # Common nerfstudio metadata locations
    if hasattr(dpo, "metadata") and isinstance(dpo.metadata, dict):
        md = dpo.metadata
        for key in ["points3D_xyz", "points3D", "points_xyz", "point_cloud_xyz"]:
            if key in md:
                candidates.append((f"train_dataparser_outputs.metadata['{key}']", md[key]))

    ds = pipeline.datamanager.train_dataset
    if hasattr(ds, "metadata") and isinstance(ds.metadata, dict):
        md = ds.metadata
        for key in ["points3D_xyz", "points3D", "points_xyz", "point_cloud_xyz"]:
            if key in md:
                candidates.append((f"train_dataset.metadata['{key}']", md[key]))

    for name, value in candidates:
        if isinstance(value, torch.Tensor) and value.ndim == 2 and value.shape[-1] == 3:
            return name, value.detach().cpu().float()

    raise RuntimeError(
        "Could not find sparse points in known metadata locations. "
        "Print pipeline.datamanager.train_dataparser_outputs.metadata keys and "
        "train_dataset.metadata keys, then adapt this helper."
    )


def print_metadata_keys(pipeline):
    dpo = pipeline.datamanager.train_dataparser_outputs
    print("\n[metadata keys]")
    if hasattr(dpo, "metadata") and isinstance(dpo.metadata, dict):
        print("  train_dataparser_outputs.metadata keys:", sorted(dpo.metadata.keys()))
    else:
        print("  train_dataparser_outputs.metadata: unavailable")

    ds = pipeline.datamanager.train_dataset
    if hasattr(ds, "metadata") and isinstance(ds.metadata, dict):
        print("  train_dataset.metadata keys:", sorted(ds.metadata.keys()))
    else:
        print("  train_dataset.metadata: unavailable")


def inspect_transform_consistency(pipeline):
    dpo = pipeline.datamanager.train_dataparser_outputs
    cams = pipeline.datamanager.train_dataset.cameras

    print("\n=== TRANSFORM CONSISTENCY ===")
    print(f"dataparser_scale = {float(dpo.dataparser_scale)}")
    print(f"dataparser_transform shape = {tuple(dpo.dataparser_transform.shape)}")

    camera_centers = camera_centers_from_c2w(cams.camera_to_worlds)
    bbox_stats(camera_centers, "camera_centers")

    src_name, sparse_points = get_sparse_points_cpu(pipeline)
    print(f"sparse points source: {src_name}")
    bbox_stats(sparse_points, "sparse_points/raw")

    transformed_points = apply_transform_and_scale(
        sparse_points,
        dpo.dataparser_transform,
        float(dpo.dataparser_scale),
    )
    bbox_stats(transformed_points, "sparse_points/transformed")

    cam_center = camera_centers.mean(dim=0)
    raw_center = sparse_points.mean(dim=0)
    transformed_center = transformed_points.mean(dim=0)

    print("\n[center distances]")
    print("  ||camera_mean - raw_points_mean||         =", torch.linalg.norm(cam_center - raw_center).item())
    print("  ||camera_mean - transformed_points_mean|| =", torch.linalg.norm(cam_center - transformed_center).item())

    return sparse_points, transformed_points


def inspect_tetra_quality(points_for_tetra: torch.Tensor, max_points_for_cpu_triangulation: int = 120_000):
    print("\n=== TETRA QUALITY ===")
    n = points_for_tetra.shape[0]
    print(f"num input points = {n}")

    if n > max_points_for_cpu_triangulation:
        print(f"Too many points for a quick debug triangulation ({n} > {max_points_for_cpu_triangulation}).")
        print("Subsampling for diagnostics...")
        idx = torch.randperm(n)[:max_points_for_cpu_triangulation]
        pts = points_for_tetra[idx].contiguous()
    else:
        pts = points_for_tetra.contiguous()

    print(f"triangulating {pts.shape[0]} points...")
    cells = triangulate(pts)  # returns int32 on same device as input; CPU input is fine too
    if cells.is_cuda:
        cells = cells.cpu()
    cells = cells.contiguous().int()

    print(f"num tetrahedra = {cells.shape[0]}")
    vols = tetra_volumes(pts.cpu(), cells.cpu())
    qstats(vols, "tetra_volumes")

    large_idx = torch.argsort(vols, descending=True)[:10]
    print("\n[top 10 tetra volumes]")
    for rank, i in enumerate(large_idx.tolist(), start=1):
        tet = cells[i].tolist()
        print(f"  #{rank:02d}: vol={vols[i].item():.8g}, cell={tet}")

    return pts.cpu(), cells.cpu(), vols.cpu()


def inspect_outliers(points: torch.Tensor):
    print("\n=== OUTLIER CHECK ===")
    center = points.mean(dim=0, keepdim=True)
    d = torch.linalg.norm(points - center, dim=-1)
    qstats(d, "point_distance_from_mean")

    q99 = torch.quantile(d, 0.99)
    q999 = torch.quantile(d, 0.999)

    keep_99 = d <= q99
    keep_999 = d <= q999

    print(f"keep <= q99  : {keep_99.sum().item()} / {points.shape[0]}")
    print(f"keep <= q999 : {keep_999.sum().item()} / {points.shape[0]}")

    return keep_99, keep_999


def inspect_find_tetrahedra(points_for_tetra: torch.Tensor, cells: torch.Tensor, device: str):
    print("\n=== FIND_TETRAHEDRA SANITY ===")

    xyz = points_for_tetra.to(device=device, dtype=torch.float32).contiguous()
    cells_gpu = cells.to(device=device, dtype=torch.int32).contiguous()

    tracer = TetrahedraTracer(torch.device(device))
    tracer.load_tetrahedra(xyz, cells_gpu)

    # Test with tetra centroids: these should be inside their own tetrahedra.
    tet_vertices = xyz[cells_gpu.long()]              # [T,4,3]
    centroids = tet_vertices.mean(dim=1)             # [T,3]

    max_test = min(2048, centroids.shape[0])
    centroids = centroids[:max_test].contiguous()

    result = tracer.find_tetrahedra(centroids)
    tetrahedra = result["tetrahedra"].detach().cpu()
    bary = result["barycentric_coordinates"].detach().cpu()
    valid = result["valid_mask"].detach().cpu()

    valid_rate = valid.float().mean().item()
    print(f"valid centroid rate = {valid_rate:.6f}")

    if valid.any():
        bary_sum = bary[valid].sum(dim=-1)
        qstats(bary_sum, "centroid_bary_sum")
        qstats(bary[valid].reshape(-1), "centroid_bary_values")

    matched_self = (tetrahedra[valid] == torch.arange(max_test, dtype=tetrahedra.dtype)[valid]).float().mean().item() if valid.any() else float("nan")
    print(f"matched original tetra rate = {matched_self:.6f}")

    return tracer

def inspect_ray_trace_from_train_batch(pipeline, tracer, max_rays: int = 256, max_ray_triangles: int = 256):
    print("\n=== TRACE_RAYS SANITY (FROM TRAIN BATCH) ===")

    ray_bundle, batch = pipeline.datamanager.next_train(0)

    ray_origins = ray_bundle.origins.reshape(-1, 3).contiguous().float()
    ray_dirs = ray_bundle.directions.reshape(-1, 3).contiguous().float()

    if ray_origins.shape[0] > max_rays:
        ray_origins = ray_origins[:max_rays]
        ray_dirs = ray_dirs[:max_rays]

    print("ray_origins shape:", tuple(ray_origins.shape), ray_origins.dtype, ray_origins.device)
    print("ray_dirs shape   :", tuple(ray_dirs.shape), ray_dirs.dtype, ray_dirs.device)
    print("max_ray_triangles:", max_ray_triangles)

    result = tracer.trace_rays(ray_origins, ray_dirs, max_ray_triangles)

    num_visited = result["num_visited_cells"].detach().cpu()
    visited = result["visited_cells"].detach().cpu()
    bary = result["barycentric_coordinates"].detach().cpu()
    hit_d = result["hit_distances"].detach().cpu()
    v_idx = result["vertex_indices"].detach().cpu()

    qstats(num_visited.float(), "num_visited_cells_per_ray")

    used = num_visited > 0
    print(f"rays with intersections = {used.sum().item()} / {num_visited.numel()}")

    if used.any():
        first_counts = num_visited[used]
        print(f"mean visited cells over hit rays = {first_counts.float().mean().item():.4f}")

        first_hit = hit_d[used, 0]
        qstats(first_hit.reshape(-1), "first_hit_distances_flat")
        qstats((first_hit[:, 1] - first_hit[:, 0]), "first_hit_interval_length")

        first_bary = bary[used, 0]
        qstats(first_bary.reshape(-1), "first_hit_bary_values")

        print("\n[sample first few rays]")
        hit_rows = torch.nonzero(used, as_tuple=False).squeeze(-1)
        for j in range(min(8, hit_rows.numel())):
            i = hit_rows[j].item()
            print(
                f"  ray {i}: visited={int(num_visited[i])}, "
                f"first_cell={int(visited[i, 0])}, "
                f"first_hit={hit_d[i, 0].tolist()}, "
                f"first_vertex_idx={v_idx[i, 0].tolist()}"
            )
            
def try_model_forward_stats(pipeline):
    print("\n=== MODEL FORWARD STATS (BEST EFFORT) ===")
    try:
        ray_bundle, batch = pipeline.datamanager.next_train(0)
        outputs = pipeline.model(ray_bundle)

        for key in ["rgb", "depth", "accumulation"]:
            if key in outputs and isinstance(outputs[key], torch.Tensor):
                qstats(outputs[key], f"model_output/{key}")

    except Exception as exc:
        print(f"Could not run model forward stats: {exc}")

def print_largest_tetra_vertices(points: torch.Tensor, cells: torch.Tensor, vols: torch.Tensor, topk: int = 10):
    print("\n=== LARGEST TETRA VERTICES ===")
    idx = torch.argsort(vols, descending=True)[:topk]
    for rank, i in enumerate(idx.tolist(), start=1):
        tet = cells[i].long()
        verts = points[tet]
        center = verts.mean(dim=0)
        print(f"\n#{rank:02d} tetra index={i} vol={vols[i].item():.8g}")
        print(f"  cell indices: {tet.tolist()}")
        print(f"  center      : {center.tolist()}")
        for j in range(4):
            print(f"  v{j}: {verts[j].tolist()}")
            
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="Path to dataset dense/ root")
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--max-points-for-cpu-triangulation", type=int, default=120000)
    args = parser.parse_args()

    torch.set_grad_enabled(False)

    print("Building pipeline...")
    cfg, pipeline = build_pipeline(args.data, args.device)
    
    inspect_model_tetra_vertices(pipeline)
    
    print_metadata_keys(pipeline)

    sparse_raw, sparse_transformed = inspect_transform_consistency(pipeline)

    keep_99, keep_999 = inspect_outliers(sparse_transformed)

    # Main tetra diagnostic on the actual model tetra vertices
    model_pts = pipeline.model.tetrahedra_vertices.detach().cpu()

    pts_cpu, cells_cpu, vols = inspect_tetra_quality(
        model_pts,
        max_points_for_cpu_triangulation=args.max_points_for_cpu_triangulation,
    )

    print("\n=== OPTIONAL REPEAT: FILTERED POINTS (q99) ===")
    model_center = model_pts.mean(dim=0, keepdim=True)
    model_d = torch.linalg.norm(model_pts - model_center, dim=-1)
    model_q99 = torch.quantile(model_d, 0.99)
    filtered_pts = model_pts[model_d <= model_q99]
    if filtered_pts.shape[0] >= 16:
        inspect_tetra_quality(
            filtered_pts,
            max_points_for_cpu_triangulation=min(args.max_points_for_cpu_triangulation, filtered_pts.shape[0]),
        )
    else:
        print("Not enough points after filtering.")

    tracer = inspect_find_tetrahedra(pts_cpu, cells_cpu, args.device)
    inspect_ray_trace_from_train_batch(pipeline, tracer)
    try_model_forward_stats(pipeline)
    print_largest_tetra_vertices(pts_cpu, cells_cpu, vols, topk=10)

    print("\nDONE.")


if __name__ == "__main__":
    main()