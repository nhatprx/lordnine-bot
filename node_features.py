"""
Node Features — Precompute template features for fast detection.

Instead of computing CLAHE, edges, ORB keypoints, and histograms
on every single detect call, precompute them once when a node 
template is added/re-captured, and store as .features.npz alongside
the PNG file.

Usage:
    from node_features import precompute_features, load_features, batch_precompute
    
    # Precompute features for a single template
    precompute_features("trackers/Revivie.png")
    
    # Load precomputed features (returns dict or None if not available)
    feats = load_features("trackers/Revivie.png")
    # feats = {"clahe", "edges", "edges_dilated", "hist_r/g/b", 
    #          "orb_kp", "orb_des", "tpl_w", "tpl_h", "is_small"}
    
    # Batch precompute all templates in a directory
    batch_precompute("trackers/")
"""

import cv2
import numpy as np
import os
import time


def _features_path(template_path):
    """Get the .features.npz path for a template."""
    base, _ = os.path.splitext(template_path)
    return base + ".features.npz"


def precompute_features(template_path):
    """
    Precompute all detection features for a template image.
    Saves to .features.npz alongside the PNG.
    
    Returns: True if successful, False otherwise.
    """
    try:
        bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if bgr is None:
            return False
        
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        is_small = 1 if (w < 60 or h < 60) else 0
        
        # 1. CLAHE enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        tpl_clahe = clahe.apply(gray)
        
        # 2. Canny edges + dilation
        tpl_edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((2, 2), np.uint8)
        tpl_edges_dilated = cv2.dilate(tpl_edges, kernel, iterations=1)
        
        # 3. Color histograms (3 channels × 64 bins)
        hist_r = cv2.calcHist([bgr], [2], None, [64], [0, 256])
        hist_g = cv2.calcHist([bgr], [1], None, [64], [0, 256])
        hist_b = cv2.calcHist([bgr], [0], None, [64], [0, 256])
        cv2.normalize(hist_r, hist_r)
        cv2.normalize(hist_g, hist_g)
        cv2.normalize(hist_b, hist_b)
        
        # 4. ORB keypoints + descriptors (for fallback matching)
        orb_kp_data = np.array([])
        orb_des = np.array([])
        if w >= 20 and h >= 20:
            try:
                orb = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8,
                                      edgeThreshold=10, patchSize=20)
                kps, des = orb.detectAndCompute(tpl_clahe, None)
                if kps and des is not None:
                    # Serialize keypoints as array: [x, y, size, angle, response]
                    orb_kp_data = np.array(
                        [[kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response] for kp in kps],
                        dtype=np.float32
                    )
                    orb_des = des
            except:
                pass
        
        # 5. Multi-scale templates for template matching
        # Pre-resize to common scales to avoid repeated resize
        scales = [1.0]
        if not is_small:
            scales.extend([0.95, 1.05])
        
        scaled_clahe = {}
        scaled_edges = {}
        for s in scales:
            if s == 1.0:
                scaled_clahe[f"clahe_{s:.2f}"] = tpl_clahe
                scaled_edges[f"edges_{s:.2f}"] = tpl_edges_dilated
            else:
                new_w = max(5, int(w * s))
                new_h = max(5, int(h * s))
                scaled_clahe[f"clahe_{s:.2f}"] = cv2.resize(tpl_clahe, (new_w, new_h))
                edges_resized = cv2.Canny(cv2.resize(gray, (new_w, new_h)), 50, 150)
                scaled_edges[f"edges_{s:.2f}"] = cv2.dilate(edges_resized, kernel, iterations=1)
        
        # Save all features
        save_dict = {
            "gray": gray,
            "bgr": bgr,
            "clahe": tpl_clahe,
            "edges": tpl_edges,
            "edges_dilated": tpl_edges_dilated,
            "hist_r": hist_r.flatten(),
            "hist_g": hist_g.flatten(),
            "hist_b": hist_b.flatten(),
            "orb_kp": orb_kp_data,
            "orb_des": orb_des,
            "meta": np.array([w, h, is_small], dtype=np.int32),
            "mtime": np.array([os.path.getmtime(template_path)]),
        }
        # Add scaled templates
        save_dict.update(scaled_clahe)
        save_dict.update(scaled_edges)
        
        np.savez_compressed(_features_path(template_path), **save_dict)
        return True
        
    except Exception as e:
        print(f"[NodeFeatures] Error precomputing {template_path}: {e}")
        return False


def load_features(template_path):
    """
    Load precomputed features for a template.
    Returns dict with features, or None if not available or outdated.
    """
    feat_path = _features_path(template_path)
    
    if not os.path.exists(feat_path):
        return None
    
    try:
        # Check if template has been modified since features were computed
        tpl_mtime = os.path.getmtime(template_path)
        feat_mtime = os.path.getmtime(feat_path)
        
        if tpl_mtime > feat_mtime:
            # Template changed, features are stale
            return None
        
        data = np.load(feat_path, allow_pickle=False)
        
        # Verify mtime matches
        stored_mtime = float(data["mtime"][0])
        if abs(stored_mtime - tpl_mtime) > 1.0:
            return None
        
        meta = data["meta"]
        w, h, is_small = int(meta[0]), int(meta[1]), bool(meta[2])
        
        result = {
            "gray": data["gray"],
            "bgr": data["bgr"],
            "clahe": data["clahe"],
            "edges": data["edges"],
            "edges_dilated": data["edges_dilated"],
            "hist_r": data["hist_r"].reshape(64, 1),
            "hist_g": data["hist_g"].reshape(64, 1),
            "hist_b": data["hist_b"].reshape(64, 1),
            "orb_kp": data["orb_kp"],
            "orb_des": data["orb_des"],
            "tpl_w": w,
            "tpl_h": h,
            "is_small": is_small,
        }
        
        # Load scaled templates
        for key in data.files:
            if key.startswith("clahe_") or key.startswith("edges_"):
                result[key] = data[key]
        
        # Reconstruct ORB keypoints from array
        if result["orb_kp"].size > 0:
            kp_array = result["orb_kp"]
            result["orb_keypoints"] = [
                cv2.KeyPoint(x=float(row[0]), y=float(row[1]), size=float(row[2]),
                            angle=float(row[3]), response=float(row[4]))
                for row in kp_array
            ]
        else:
            result["orb_keypoints"] = []
        
        return result
        
    except Exception as e:
        print(f"[NodeFeatures] Error loading {feat_path}: {e}")
        return None


def batch_precompute(trackers_dir="trackers"):
    """
    Precompute features for all PNG templates in a directory.
    Returns (success_count, fail_count, skipped_count).
    """
    success = 0
    failed = 0
    skipped = 0
    
    if not os.path.exists(trackers_dir):
        return 0, 0, 0
    
    for filename in os.listdir(trackers_dir):
        if not filename.endswith(".png"):
            continue
        if filename.endswith(".features.npz"):
            continue
            
        template_path = os.path.join(trackers_dir, filename)
        feat_path = _features_path(template_path)
        
        # Skip if features are up-to-date
        if os.path.exists(feat_path):
            try:
                tpl_mtime = os.path.getmtime(template_path)
                feat_mtime = os.path.getmtime(feat_path)
                if feat_mtime >= tpl_mtime:
                    skipped += 1
                    continue
            except:
                pass
        
        if precompute_features(template_path):
            success += 1
        else:
            failed += 1
    
    return success, failed, skipped


def get_feature_status(trackers_dir="trackers"):
    """
    Get learning status for all templates.
    Returns list of (name, has_features, is_stale).
    """
    status = []
    if not os.path.exists(trackers_dir):
        return status
    
    for filename in sorted(os.listdir(trackers_dir)):
        if not filename.endswith(".png"):
            continue
            
        name = filename[:-4]
        template_path = os.path.join(trackers_dir, filename)
        feat_path = _features_path(template_path)
        
        if not os.path.exists(feat_path):
            status.append((name, False, False))
        else:
            try:
                tpl_mtime = os.path.getmtime(template_path)
                feat_mtime = os.path.getmtime(feat_path)
                is_stale = tpl_mtime > feat_mtime
                status.append((name, True, is_stale))
            except:
                status.append((name, False, False))
    
    return status
