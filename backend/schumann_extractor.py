#!/usr/bin/env python3
"""
schumann_extractor.py
Autonomous Optical Data Extractor

Downloads the latest Schumann frequency spectrogram (srf.jpg) from sos70.ru (Tomsk),
uses deterministic topological pixel-slicing to find the modal F1 white line plot,
and extracts the modal proxy value (graph height) to represent FSR physically without LLM tokens.
"""

import os
import sys
import tempfile
import numpy as np
import requests
from PIL import Image
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger("omega.schumann_extractor")

TOMSK_SRF_URL = "https://sos70.ru/provider.php?file=srf.jpg"
DATA_FILE = Path(__file__).resolve().parent / "data" / "real_schumann_history.csv"

def extract_f1_proxy_from_image(img_path: str) -> float:
    """
    Reads the Tomsk srf.jpg spectrogram.
    The F1 line is plotted in pure white.
    Returns the inverted Y-coordinate of the structural mean,
    so that an upward mathematical shift in the graph equals a positive value proxy.
    """
    img = Image.open(img_path).convert('RGB')
    arr = np.array(img)
    
    # Isolate white pixels (F1 line plot is white in Tomsk graphs)
    white_mask = (arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] > 200)
    
    y_coords, x_coords = np.where(white_mask)
    if len(y_coords) == 0:
        raise ValueError("Could not detect any white pixel data in the spectrogram.")
        
    # The Tomsk image plots multiple days, the right-most 25% represents the latest 24hr period.
    max_x = np.max(x_coords)
    recent_mask = x_coords > (max_x * 0.75)
    
    recent_y = y_coords[recent_mask]
    if len(recent_y) == 0:
        recent_y = y_coords  # fallback if crop fails
        
    # Invert Y so that a higher structural position on the graph = a higher proxy float
    mean_y = np.mean(recent_y)
    proxy_val = -mean_y
    return proxy_val

def update_schumann_history():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure CSV headers
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w") as f:
            f.write("date,fsr\n")
            
    try:
        r = requests.get(TOMSK_SRF_URL, timeout=15)
        r.raise_for_status()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name
            
        try:
            proxy_f1 = extract_f1_proxy_from_image(tmp_path)
            
            import datetime as dt
            today_str = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
            
            # Read existing to avoid duplicate entries for the same day
            lines = []
            if DATA_FILE.exists():
                with open(DATA_FILE, "r") as f:
                    lines = f.readlines()
                    
            if len(lines) > 0 and lines[-1].startswith(today_str):
                # Update today's value
                lines[-1] = f"{today_str},{proxy_f1:.4f}\n"
            else:
                # Append new day
                lines.append(f"{today_str},{proxy_f1:.4f}\n")
                
            with open(DATA_FILE, "w") as f:
                f.writelines(lines)
                
            logger.info(f"Successfully extracted real F1 topological proxy: {proxy_f1:.4f}")
            print(f"Extracted proxy: {proxy_f1:.4f}")
            return proxy_f1
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
    except Exception as e:
        logger.error(f"Failed to extract Schumann optical proxy: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Setup basic console logging for standalone testing
    logging.basicConfig(level=logging.INFO)
    update_schumann_history()
