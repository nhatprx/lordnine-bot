import cv2
import numpy as np
import mss
import time
import os
import ctypes
from concurrent.futures import ThreadPoolExecutor

# DPI Aware
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) 
except Exception:
    pass


def _match_template_worker(template_path, threshold, debug, region, frame_bytes, write_debug=True):
    """
    [WORKER] Multi-layer template matching for maximum accuracy.
    
    Layer 1: CLAHE-enhanced grayscale matching (CCOEFF + CCORR)
    Layer 2: Canny edge-based matching (immune to background noise)
    Layer 3: ORB feature matching (fallback for hard cases)
    + Color histogram verification
    
    Returns: (center_x, center_y, final_score) or None
    """
    template_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template_bgr is None:
        return None
        
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    tpl_h_orig, tpl_w_orig = template_gray.shape[:2]
    is_small_template = tpl_w_orig < 60 or tpl_h_orig < 60

    # 1. Capture screen
    if frame_bytes is not None:
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None
        region = None
    else:
        with mss.mss() as sct:
            if region:
                monitor = {"left": region[0], "top": region[1], "width": int(region[2]), "height": int(region[3])}
            else:
                monitor = sct.monitors[0]
            screenshot = sct.grab(monitor)
        img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
    
    # DEBUG: Save raw images (disabled in multi-account to prevent file corruption)
    if write_debug:
        try:
            os.makedirs("debug", exist_ok=True)
            tpl_name_debug = os.path.splitext(os.path.basename(template_path))[0]
            cv2.imwrite(f"debug/capture_{tpl_name_debug}.jpg", img_bgr)
            cv2.imwrite(f"debug/template_{tpl_name_debug}.png", template_bgr)
        except:
            pass
        
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # ==========================================
    # PREPROCESSING: CLAHE contrast enhancement
    # ==========================================
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_clahe = clahe.apply(img_gray)
    tpl_clahe = clahe.apply(template_gray)
    
    # ==========================================
    # PREPROCESSING: Canny edge maps
    # ==========================================
    # Gaussian blur FIRST to suppress noise from complex 3D backgrounds
    img_blur = cv2.GaussianBlur(img_clahe, (3, 3), 0)
    tpl_blur = cv2.GaussianBlur(tpl_clahe, (3, 3), 0)
    
    # Higher thresholds for screen (very busy 3D game scene)
    img_edges = cv2.Canny(img_blur, 80, 200)
    # Lower thresholds for template (clean, small UI element)
    tpl_edges = cv2.Canny(tpl_blur, 50, 150)
    
    # Dilate edges for overlap tolerance (thicker = more forgiving matching)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    img_edges = cv2.dilate(img_edges, kernel, iterations=1)
    tpl_edges = cv2.dilate(tpl_edges, kernel, iterations=1)

    # ==========================================
    # MULTI-SCALE + MULTI-METHOD matching
    # ==========================================
    best_ccoeff = None   # (score, loc, w, h)
    best_ccorr  = None   # (score, loc, w, h)
    best_edge   = None   # (score, loc, w, h)
    
    # Scale range: 0.8x to 1.2x, 9 steps (tighter range = faster + more precise)
    for scale in np.linspace(0.8, 1.2, 9)[::-1]:
        width = int(template_gray.shape[1] * scale)
        height = int(template_gray.shape[0] * scale)
        
        if width < 10 or height < 10:
            continue
        if width > img_gray.shape[1] or height > img_gray.shape[0]:
            continue
        
        resized_clahe = cv2.resize(tpl_clahe, (width, height))
        resized_edge  = cv2.resize(tpl_edges, (width, height))
        
        # Method 1: CLAHE-enhanced CCOEFF
        res1 = cv2.matchTemplate(img_clahe, resized_clahe, cv2.TM_CCOEFF_NORMED)
        _, max_val1, _, max_loc1 = cv2.minMaxLoc(res1)
        if best_ccoeff is None or max_val1 > best_ccoeff[0]:
            best_ccoeff = (max_val1, max_loc1, width, height)
        
        # Method 2: CLAHE-enhanced CCORR
        res2 = cv2.matchTemplate(img_clahe, resized_clahe, cv2.TM_CCORR_NORMED)
        _, max_val2, _, max_loc2 = cv2.minMaxLoc(res2)
        if best_ccorr is None or max_val2 > best_ccorr[0]:
            best_ccorr = (max_val2, max_loc2, width, height)
        
        # Method 3: Edge-based CCOEFF (background-immune)
        # Only match if template has enough edges (avoid blank edge maps)
        if np.count_nonzero(resized_edge) > 20:
            res3 = cv2.matchTemplate(img_edges, resized_edge, cv2.TM_CCOEFF_NORMED)
            _, max_val3, _, max_loc3 = cv2.minMaxLoc(res3)
            if best_edge is None or max_val3 > best_edge[0]:
                best_edge = (max_val3, max_loc3, width, height)

    # ==========================================
    # SCORE EXTRACTION
    # ==========================================
    ccoeff_score = best_ccoeff[0] if best_ccoeff else 0
    ccorr_score  = best_ccorr[0]  if best_ccorr  else 0
    edge_score   = best_edge[0]   if best_edge   else 0
    
    # Normalize CCORR to comparable range
    ccorr_normalized = max(0, (ccorr_score - 0.9) * 10.0)
    
    # ==========================================
    # SMART SCORE FUSION (size-aware)
    # ==========================================
    if is_small_template:
        # Small icons: use the BEST of edge or ccoeff as primary
        # Don't let a low edge score drag down a decent ccoeff
        primary = max(edge_score, ccoeff_score)
        secondary = min(edge_score, ccoeff_score)
        # Only blend secondary if it's actually helpful (> 0.3)
        if secondary > 0.3:
            fusion_score = primary * 0.60 + secondary * 0.25 + ccorr_normalized * 0.15
        else:
            fusion_score = primary * 0.80 + ccorr_normalized * 0.20
        # If edge alone is very strong, trust it
        if edge_score > 0.65:
            fusion_score = max(fusion_score, edge_score * 0.85 + ccorr_normalized * 0.15)
    else:
        # Large templates: CCOEFF is reliable, edge is boost only
        fusion_score = max(
            ccoeff_score * 0.50 + edge_score * 0.30 + ccorr_normalized * 0.20,
            ccoeff_score * 0.80 + ccorr_normalized * 0.20  # fallback: ignore weak edge
        )
    
    # Pick the best location from whichever method scored highest
    candidates = []
    if best_ccoeff: candidates.append(("CCOEFF", ccoeff_score, best_ccoeff))
    if best_edge:   candidates.append(("EDGE",   edge_score,   best_edge))
    if best_ccorr:  candidates.append(("CCORR",  ccorr_normalized, best_ccorr))
    
    if not candidates:
        return None
    
    # Use location from the highest-scoring method
    candidates.sort(key=lambda c: c[1], reverse=True)
    match_method = candidates[0][0]
    best_result = candidates[0][2]
    best_val, best_loc, best_w, best_h = best_result
    
    # ==========================================
    # COLOR HISTOGRAM verification (boost factor)
    # ==========================================
    hist_score = 0.0
    try:
        roi_x = max(0, best_loc[0])
        roi_y = max(0, best_loc[1])
        roi = img_bgr[roi_y:roi_y+best_h, roi_x:roi_x+best_w]
        
        if roi.shape[0] > 0 and roi.shape[1] > 0:
            resized_template_bgr = cv2.resize(template_bgr, (best_w, best_h))
            
            hist_scores = []
            for ch in range(3):
                hist_roi = cv2.calcHist([roi], [ch], None, [64], [0, 256])
                hist_tpl = cv2.calcHist([resized_template_bgr], [ch], None, [64], [0, 256])
                cv2.normalize(hist_roi, hist_roi)
                cv2.normalize(hist_tpl, hist_tpl)
                similarity = cv2.compareHist(hist_roi, hist_tpl, cv2.HISTCMP_CORREL)
                hist_scores.append(similarity)
            
            hist_score = float(np.mean(hist_scores))
    except:
        hist_score = 0.0
    
    if hist_score > 0.7:
        fusion_score = min(1.0, fusion_score + 0.05)
    
    # ==========================================
    # ORB FEATURE MATCHING (fallback layer)
    # ==========================================
    orb_score = 0.0
    orb_loc = None
    
    # Only run ORB if we're below threshold and template has enough detail
    if fusion_score < threshold and tpl_w_orig >= 20 and tpl_h_orig >= 20:
        try:
            orb = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8,
                                  edgeThreshold=10, patchSize=20)
            
            kp_tpl, des_tpl = orb.detectAndCompute(tpl_clahe, None)
            kp_img, des_img = orb.detectAndCompute(img_clahe, None)
            
            if des_tpl is not None and des_img is not None and len(kp_tpl) >= 4 and len(kp_img) >= 4:
                bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
                matches = bf.knnMatch(des_tpl, des_img, k=2)
                
                # Lowe's ratio test
                good_matches = []
                for m_pair in matches:
                    if len(m_pair) == 2:
                        m, n = m_pair
                        if m.distance < 0.75 * n.distance:
                            good_matches.append(m)
                
                min_good = max(4, len(kp_tpl) // 5)  # At least 20% of template keypoints
                
                if len(good_matches) >= min_good:
                    # Calculate match quality score
                    orb_score = min(1.0, len(good_matches) / max(1, len(kp_tpl)) * 2.0)
                    
                    # Find bounding box of matched region
                    matched_pts = np.float32([kp_img[m.trainIdx].pt for m in good_matches])
                    center_x_orb = int(np.mean(matched_pts[:, 0]))
                    center_y_orb = int(np.mean(matched_pts[:, 1]))
                    orb_loc = (center_x_orb - tpl_w_orig // 2, center_y_orb - tpl_h_orig // 2)
                    
                    # Verify location is reasonable (within image bounds)
                    if orb_loc[0] < 0 or orb_loc[1] < 0:
                        orb_score = 0.0
                        orb_loc = None
        except:
            orb_score = 0.0
    
    # If ORB found a strong match, use it
    if orb_score > 0.5 and orb_loc is not None:
        # Blend ORB into fusion
        orb_fusion = fusion_score * 0.4 + orb_score * 0.6
        if orb_fusion > fusion_score:
            fusion_score = orb_fusion
            best_loc = orb_loc
            best_w = tpl_w_orig
            best_h = tpl_h_orig
            match_method = "ORB"
    
    # Final score
    final_score = fusion_score
    
    # [DEBUG LOG]
    tpl_name = os.path.basename(template_path)
    is_web = frame_bytes is not None
    small_tag = "[S]" if is_small_template else "[L]"
    print(f"[Vision] [{tpl_name}] {small_tag} {'WEB' if is_web else 'MSS'} CC:{ccoeff_score:.3f} ED:{edge_score:.3f} CR:{ccorr_score:.3f} ORB:{orb_score:.2f} H:{hist_score:.3f} => final:{final_score:.3f} vs thresh:{threshold}")

    if debug and write_debug:
        try:
            debug_img = img_bgr.copy()
            top_left = best_loc
            bottom_right = (top_left[0] + best_w, top_left[1] + best_h)
            
            color = (0, 255, 0) if final_score >= threshold else (0, 0, 255)
            cv2.rectangle(debug_img, top_left, bottom_right, color, 3)
            
            text = f"[{match_method}] CC:{ccoeff_score:.2f} ED:{edge_score:.2f} ORB:{orb_score:.2f} => {final_score:.2f}"
            cv2.putText(debug_img, text, (top_left[0], max(20, top_left[1]-10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            os.makedirs("debug", exist_ok=True)
            cv2.imwrite("debug/last_scan.jpg", debug_img)
            
            # Save edge maps for debugging
            tpl_name_clean = os.path.splitext(os.path.basename(template_path))[0]
            cv2.imwrite(f"debug/edge_screen_{tpl_name_clean}.jpg", img_edges)
            cv2.imwrite(f"debug/edge_tpl_{tpl_name_clean}.jpg", tpl_edges)
        except:
            pass

    if final_score >= threshold:
        if frame_bytes is not None:
            offset_x = region[0] if region else 0
            offset_y = region[1] if region else 0
        else:
            offset_x = monitor["left"]
            offset_y = monitor["top"]
        
        center_x = best_loc[0] + best_w // 2 + offset_x
        center_y = best_loc[1] + best_h // 2 + offset_y
        
        # Safety bounds check
        img_h, img_w = img_bgr.shape[:2]
        if frame_bytes is not None:
            if center_x < 0 or center_x > img_w or center_y < 0 or center_y > img_h:
                return None
        
        return (center_x, center_y, final_score)

    return None


# ===================================================================
# Singleton ThreadPool
# OpenCV releases GIL so ThreadPool gives real parallelism
# ===================================================================
_global_pool = None

def _get_pool(max_workers=None):
    global _global_pool
    if _global_pool is None:
        if max_workers is None:
            max_workers = max(2, (os.cpu_count() or 4))
        _global_pool = ThreadPoolExecutor(max_workers=max_workers)
    return _global_pool


class Vision:
    def __init__(self, pool_workers=None):
        os.makedirs("debug", exist_ok=True)
        self._pool = _get_pool(pool_workers)

    def find_template_on_screen(self, template_path, threshold=0.8, debug=True, region=None, frame_bytes=None, write_debug=True):
        """
        Multi-layer template matching with ThreadPool.
        Returns: (center_x, center_y, final_score) or None
        """
        try:
            future = self._pool.submit(
                _match_template_worker,
                template_path, threshold, debug, region, frame_bytes, write_debug
            )
            result = future.result(timeout=10)
            return result
        except Exception as e:
            try:
                return _match_template_worker(template_path, threshold, debug, region, frame_bytes, write_debug)
            except:
                return None

    def find_template_direct(self, template_path, threshold=0.8, debug=False, region=None, frame_bytes=None):
        """
        Direct template matching — bypasses ThreadPool entirely.
        Use this from multi-account worker threads to avoid pool saturation.
        Each worker thread already has its own thread, so no pool needed.
        
        Returns: (center_x, center_y, final_score) or None
        """
        try:
            return _match_template_worker(
                template_path, threshold, debug, region, frame_bytes, write_debug=False
            )
        except Exception as e:
            print(f"[Vision] Direct match error: {e}")
            return None

    def shutdown_pool(self):
        global _global_pool
        if _global_pool:
            _global_pool.shutdown(wait=False)
            _global_pool = None
