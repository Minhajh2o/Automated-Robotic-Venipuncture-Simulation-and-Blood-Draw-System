# pyrefly: ignore [missing-import]
import cv2
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import logging
import serial
import time

# Configure logging for production tracking
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def find_venipuncture_target(original_img, thresh_img, edge_margin=30):
    """
    Analyzes a binary mask of veins to find the optimal venipuncture target.
    
    Args:
        original_img (np.ndarray): The original NIR image (used for visualization).
        thresh_img (np.ndarray): The binary mask of the veins (255 for vein, 0 for background).
        edge_margin (int): Minimum distance from the image edge to consider a valid target.
        
    Returns:
        vis_img (np.ndarray): Image with visualization overlays.
        best_point (tuple): (X, Y) coordinates of the optimal injection site.
    """
    
    # ---------------------------------------------------------
    # 1. Morphological Cleaning
    # ---------------------------------------------------------
    logging.info("Starting morphological cleaning...")
    # Use an elliptical kernel which is better suited for organic, curved shapes like veins
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    
    # Morphological OPENING removes small speckles/noise in the background
    cleaned_mask = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, kernel, iterations=1)
    # Morphological CLOSING fills small holes inside the veins
    cleaned_mask = cv2.morphologyEx(cleaned_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # Area Filtering: Keep only the largest connected component to ignore isolated noise blobs
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned_mask, connectivity=8)
    if num_labels > 1:
        # stats[1:] ignores the background label (0)
        largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        cleaned_mask = np.where(labels == largest_label, 255, 0).astype(np.uint8)
    else:
        logging.warning("No valid vein structures found after cleaning.")
        return original_img, None

    # ---------------------------------------------------------
    # 2. Skeletonization / Thinning
    # ---------------------------------------------------------
    logging.info("Extracting vein centerlines (skeletonization)...")
    try:
        # Modern, fast approach (Requires opencv-contrib-python)
        skeleton = cv2.ximgproc.thinning(cleaned_mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    except AttributeError:
        # Fallback to standard morphological thinning if contrib is not installed
        logging.info("cv2.ximgproc not found. Falling back to morphological thinning.")
        skeleton = np.zeros(cleaned_mask.shape, np.uint8)
        eroded = np.zeros(cleaned_mask.shape, np.uint8)
        temp = np.zeros(cleaned_mask.shape, np.uint8)
        img_copy = cleaned_mask.copy()
        skel_kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        
        while True:
            cv2.erode(img_copy, skel_kernel, eroded)
            cv2.dilate(eroded, skel_kernel, temp)
            cv2.subtract(img_copy, temp, temp)
            cv2.bitwise_or(skeleton, temp, skeleton)
            img_copy[:, :] = eroded[:, :]
            if cv2.countNonZero(img_copy) == 0:
                break

    # ---------------------------------------------------------
    # 3. Target Selection
    # ---------------------------------------------------------
    logging.info("Computing optimal injection coordinates...")
    # Distance Transform calculates the distance from every vein pixel to the nearest background pixel.
    # On the skeleton, this value perfectly represents the local radius (half-width) of the vein.
    dist_transform = cv2.distanceTransform(cleaned_mask, cv2.DIST_L2, 5)
    
    skel_y, skel_x = np.where(skeleton > 0)
    best_point = None
    max_score = -1
    best_radius = 0
    
    height, width = cleaned_mask.shape

    for y, x in zip(skel_y, skel_x):
        # Criterion A: Distance from noisy edges (Safety margin)
        if x < edge_margin or x > width - edge_margin or y < edge_margin or y > height - edge_margin:
            continue
            
        # Criterion B: Straightness (Avoid junctions and endpoints)
        # Extract the 3x3 neighborhood around the skeleton pixel
        neighborhood = skeleton[y-1:y+2, x-1:x+2]
        
        # Count non-zero pixels in the 3x3 area, subtract 1 for the center pixel itself
        neighbors = np.count_nonzero(neighborhood) - 1
        
        # A perfect straight line segment on a 1-pixel wide skeleton has exactly 2 neighbors.
        # 1 neighbor = endpoint, >= 3 neighbors = junction/branch point.
        if neighbors == 2: 
            # Criterion C: Local Width
            # The score is the distance transform value (vein radius)
            score = dist_transform[y, x]
            
            if score > max_score:
                max_score = score
                best_point = (x, y)
                best_radius = score

    # ---------------------------------------------------------
    # 4. Visualization
    # ---------------------------------------------------------
    logging.info("Generating visualization...")
    # Ensure the visualization image is in BGR color space
    if len(original_img.shape) == 2:
        vis_img = cv2.cvtColor(original_img, cv2.COLOR_GRAY2BGR)
    else:
        vis_img = original_img.copy()

    # Overlay the skeleton path in Green
    vis_img[skeleton > 0] = [0, 255, 0]

    if best_point is not None:
        bx, by = best_point
        
        # Draw a circle representing the safe vein width at the target
        cv2.circle(vis_img, (bx, by), int(best_radius), (255, 0, 0), 2)
        
        # Draw a precise targeting crosshair in Red
        crosshair_size = 15
        cv2.line(vis_img, (bx - crosshair_size, by), (bx + crosshair_size, by), (0, 0, 255), 2)
        cv2.line(vis_img, (bx, by - crosshair_size), (bx, by + crosshair_size), (0, 0, 255), 2)
        
        # Annotate coordinates
        cv2.putText(vis_img, f"TARGET: ({bx}, {by})", (bx + 20, by - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        logging.info(f"Optimal target found at X:{bx}, Y:{by} with radius {best_radius:.2f}px")
    else:
        logging.warning("Could not find a suitable venipuncture target meeting the criteria.")

    return vis_img, best_point

# =====================================================================
# Mock Execution Block (To make the script self-contained and runnable)
# =====================================================================
if __name__ == "__main__":
    # 1. Read the actual NIR image
    img = cv2.imread("Vein-Detection-System/Vein Detection/test.jpg")
    
    # 2. Apply your preprocessing pipeline
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced_img = clahe.apply(gray_img)
    blurred_img = cv2.GaussianBlur(enhanced_img, (5, 5), 0)
    thresh_img = cv2.adaptiveThreshold(blurred_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3)

    # 3. Run the Targeting Function
    result_img, target_coords = find_venipuncture_target(img, thresh_img)

    # 4. Transmit to ESP32
    if target_coords is not None:
        bx, by = target_coords
        
        # Format the data cleanly with a newline character at the end so the ESP32 knows when to stop reading
        data_packet = f"{bx},{by}\n"
        
        try:
            # NOTE: 'COM3' is standard for Windows. You will need to change this to the 
            # actual port the ESP32 is plugged into when you test with the hardware.
            esp32 = serial.Serial('COM3', 115200, timeout=1)
            time.sleep(2) # Give the ESP32 a moment to initialize connection
            
            esp32.write(data_packet.encode('utf-8'))
            logging.info(f"Successfully transmitted {data_packet.strip()} to hardware.")
            esp32.close()
            
        except serial.SerialException:
            logging.warning(f"Hardware not connected. Would have sent: {data_packet.strip()}")

    # 5. Display the Final Targeting Crosshair
    cv2.imshow("Venipuncture Targeting System", result_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()