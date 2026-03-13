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


def _match_template_worker(template_path, threshold, debug, region, frame_bytes):
    """
    [WORKER] Multi-method template matching for maximum accuracy.
    
    Methods:
      1. Grayscale TM_CCOEFF_NORMED (best general method)
      2. Grayscale TM_CCORR_NORMED (more tolerant to brightness)
      3. Multi-scale search (0.7x - 1.3x in 13 steps)
      4. Color histogram verification (secondary check)
    
    Returns: (center_x, center_y, final_score) or None
    """
    template_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template_bgr is None:
        return None
        
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)

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
    
    # DEBUG: Always save raw screenshot + template for comparison
    try:
        os.makedirs("debug", exist_ok=True)
        tpl_name_debug = os.path.splitext(os.path.basename(template_path))[0]
        cv2.imwrite(f"debug/capture_{tpl_name_debug}.jpg", img_bgr)
        cv2.imwrite(f"debug/template_{tpl_name_debug}.png", template_bgr)
        img_h_dbg, img_w_dbg = img_bgr.shape[:2]
        tpl_h_dbg, tpl_w_dbg = template_bgr.shape[:2]
        print(f"[Vision] Screenshot: {img_w_dbg}x{img_h_dbg}, Template: {tpl_w_dbg}x{tpl_h_dbg}")
    except:
        pass
        
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # ==========================================
    # MULTI-SCALE + MULTI-METHOD matching
    # ==========================================
    best_ccoeff = None   # (score, loc, w, h)
    best_ccorr = None    # (score, loc, w, h)
    
    # Wider scale range: 0.7x to 1.3x, 13 steps
    for scale in np.linspace(0.7, 1.3, 13)[::-1]:
        width = int(template_gray.shape[1] * scale)
        height = int(template_gray.shape[0] * scale)
        
        if width < 10 or height < 10:
            continue
        if width > img_gray.shape[1] or height > img_gray.shape[0]:
            continue
        
        resized = cv2.resize(template_gray, (width, height))
        
        # Method 1: TM_CCOEFF_NORMED — best for exact structural match
        res1 = cv2.matchTemplate(img_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val1, _, max_loc1 = cv2.minMaxLoc(res1)
        if best_ccoeff is None or max_val1 > best_ccoeff[0]:
            best_ccoeff = (max_val1, max_loc1, width, height)
        
        # Method 2: TM_CCORR_NORMED — more tolerant to brightness/contrast changes
        res2 = cv2.matchTemplate(img_gray, resized, cv2.TM_CCORR_NORMED)
        _, max_val2, _, max_loc2 = cv2.minMaxLoc(res2)
        if best_ccorr is None or max_val2 > best_ccorr[0]:
            best_ccorr = (max_val2, max_loc2, width, height)

    # ==========================================
    # SCORE FUSION — pick the best result  
    # ==========================================
    ccoeff_score = best_ccoeff[0] if best_ccoeff else 0
    ccorr_score = best_ccorr[0] if best_ccorr else 0
    
    # TM_CCORR_NORMED scores are naturally higher, scale down to match CCOEFF range
    # CCORR typically >0.9 even for bad matches, only really good matches are >0.98
    # Map CCORR score: remap [0.9, 1.0] -> [0.0, 1.0]
    ccorr_normalized = max(0, (ccorr_score - 0.9) * 10.0)
    
    # Weighted fusion: CCOEFF is primary (more reliable), CCORR is boost
    # If CCOEFF is already above threshold, trust it
    # If CCOEFF is close but not quite, CCORR can confirm it
    fusion_score = max(ccoeff_score, ccoeff_score * 0.7 + ccorr_normalized * 0.3)
    
    # Pick result from whichever method had higher raw score
    if ccoeff_score >= ccorr_normalized and best_ccoeff:
        best_result = best_ccoeff
        match_method = "CCOEFF"
    elif best_ccorr:
        best_result = best_ccorr
        match_method = "CCORR"
    elif best_ccoeff:
        best_result = best_ccoeff
        match_method = "CCOEFF"
    else:
        return None
        
    best_val, best_loc, best_w, best_h = best_result
    
    # ==========================================
    # ADDITIONAL: Color histogram check at matched location
    # (only used for logging, doesn't block detection)
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
    
    # If histogram shows strong color match, boost the fusion score slightly
    if hist_score > 0.7:
        fusion_score = min(1.0, fusion_score + 0.05)
    
    # Final score for threshold comparison
    final_score = fusion_score
    
    # [DEBUG LOG]
    tpl_name = os.path.basename(template_path)
    is_web = frame_bytes is not None
    print(f"[Vision] [{tpl_name}] {'WEB' if is_web else 'MSS'} CC:{ccoeff_score:.3f} CR:{ccorr_score:.3f} H:{hist_score:.3f} => final:{final_score:.3f} vs thresh:{threshold}")

    if debug:
        try:
            debug_img = img_bgr.copy()
            top_left = best_loc
            bottom_right = (top_left[0] + best_w, top_left[1] + best_h)
            
            color = (0, 255, 0) if final_score >= threshold else (0, 0, 255)
            cv2.rectangle(debug_img, top_left, bottom_right, color, 3)
            
            text = f"[{match_method}] CC:{ccoeff_score:.2f} CR:{ccorr_score:.2f} H:{hist_score:.2f} => {final_score:.2f}"
            cv2.putText(debug_img, text, (top_left[0], max(20, top_left[1]-10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            os.makedirs("debug", exist_ok=True)
            cv2.imwrite("debug/last_scan.jpg", debug_img)
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

    def find_template_on_screen(self, template_path, threshold=0.8, debug=True, region=None, frame_bytes=None):
        """
        Multi-method template matching with ThreadPool.
        Returns: (center_x, center_y, final_score) or None
        """
        try:
            future = self._pool.submit(
                _match_template_worker,
                template_path, threshold, debug, region, frame_bytes
            )
            result = future.result(timeout=10)
            return result
        except Exception as e:
            try:
                return _match_template_worker(template_path, threshold, debug, region, frame_bytes)
            except:
                return None

    def shutdown_pool(self):
        global _global_pool
        if _global_pool:
            _global_pool.shutdown(wait=False)
            _global_pool = None
