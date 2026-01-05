import subprocess 
import os
import cv2
import csv
import numpy as np
import re
import pytesseract

from loguru import logger
from pathlib import Path


#Layout carre jaune : 
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=240:84:977:ih-0,fps=0.5" data/banners/frames/bandeau_%03d.png

#Layout carre noir :
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=906:50:60:ih-144,fps=0.5" data/banners/frames/bandeau_%03d.png

#Layout carre Blanc actualite : 
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=909:89:60:ih-0,fps=0.5" data/banners/frames/bandeau_%03d.png

# Layou carre blanc interlocuteur: 
# ffmpeg -i data/ingest/segment_2025-12-26_14h19-05s.ts -vf "crop=909:39:60:ih-190,fps=0.5" data/banners/frames/bandeau_%03d.png

bannerss : list = [
    {
        "name": "blanche_actualite",
        "crop": "crop=909:89:60:ih-0",
        "freeze": "freezedetect=n=0.003:d=1",
        "bg": "blanc",
    },
    {
        "name": "carre_sujet",
        "crop": "crop=906:50:60:ih-144",
        "freeze": "freezedetect=n=0.005:d=3",
        "bg": "noir",
    },
    {
        "name": "carre_emission",
        "crop": "crop=240:82:977:ih-0",
        "freeze": "freezedetect=n=0.005:d=6",
        "bg": "jaune",
    },
    {
        "name": "blanche_interlocuteur",
        "crop": "crop=909:39:60:ih-190",
        "freeze": "freezedetect=n=0.005:d=3",
        "bg": "blanc",
    },
]

def extract_banners_in_folder(file: str, crop: str, type_banner: str, freeze_start: float = None, freeze_end: float = None,  middle_frame: float = None ):
    """
     Fonction qui permet d'extract les differentes bannieres de la vidéo
     crop: largeur:hauteur:x:y
     largeur	iw	on garde toute la largeur
     hauteur	220	on garde seulement 220 px de hauteur
     x	0	on commence tout à gauche
     y	ih-220	on commence 220 px au-dessus du bas
     
     fps=0.5   # 1 image toutes les 2 secondes
     fps=2     # 2 images par seconde
    """

    #Creation du dossier frames s'il n'existe pas
    if not os.path.exists("data/banners/frames"):
        logger.info(f" ✅ Crèation du dossier data/banners/frames")
        os.makedirs("data/banners/frames", exist_ok=True)
    
    #Extractiom de toutes les frames 
    if middle_frame == None: 
        COMMAND = f"""
        ffmpeg 
        -i {file}.ts 
        -vf "{crop},fps=0.5,fps=1" 
        data/banners/frames/bandeau_%03d.png
        """
    #Extration depuis le freeze
    else : 
        COMMAND = f"""
        ffmpeg -y  
        -ss {middle_frame} 
        -i data/ingest/segment_2025-12-26_14h11-48s.ts 
        -vf "{crop}"
        -frames:v 1  
        data/banners/frames/bandeau_{type_banner}_{freeze_start}_{middle_frame:.2f}_{freeze_end}.png
        """
     #ffmpeg -y
    cmd = COMMAND.replace('\n', ' ')
    cmd = cmd.strip()
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    
    if middle_frame is not None:
        p.wait()
    else: 
        while True:
            line = p.stdout.readline()
            if not line:
                break
            logger.info(line.decode('utf-8').strip())

def detect_colors_banners (image_path):
    #Lis mon image
    img = cv2.imread(image_path)
    #Converti en gris (gris -noir)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Detecte les pixels noirs (seuil a 30)
    black_pixels = gray < 30
    # Calcule le ratio de pixels noirs
    ratio_black = np.sum(black_pixels) / gray.size
    # Minimum de ratio doit etre a 70% et le ratio est ratio_black
    # N'enverrais que les images correct ?
    # if ratio_black >= 0.7 == True:
        # return ratio_black >= 0.7, ratio_black 
    # else:
    #     return None, 0.0
    return ratio_black >= 0.7, ratio_black 

def filter_on_file (frames_dir="data/banners/frames"):
    results = []
    
    #Va checker les fichiers dans le dossier  est va check la validiter du document 
    for img_path in Path(frames_dir).glob("*.png"):
        is_valid, ratio = detect_colors_banners(img_path)

        results.append({
            "file": img_path.name,
            "valid": is_valid,
            "black_ratio": ratio
        })

    return results

def extract_info_file (path: Path, word: str = "start") -> float:
    """
    Extrait le timestamp depuis bandeau_XX.XX.png
    """
    # match = re.search(r"bandeau_([0-9.]+)\.png", path.name)
 
    path = path.stem
     
    
    # On split par "_"
    parts = path.split("_")  
    # On récupère 
    type_banner = parts[2]
    start = float(parts[3])
    end = float(parts[5])

    if word == "start":
        return start
    if word == "end":
        return end
    else:
        return type_banner
    
def clean_ocr_text(text: str) -> str:
    text = text.replace('\n', ' ')
    text = text.replace('|', ' ')
    return " ".join(text.split())


def write_csv(type_banner: str) :
    
    if not os.path.exists("data/banners/csv"):
        os.makedirs("data/banners/csv", exist_ok=True)
        
    frames = sorted(
    Path("data/banners/frames").glob("*.png"),
    key=extract_info_file
        )
    
   
    
    with open("data/banners/csv/banners_segment_2025-12-26_14h11-48s.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name File", "segment_2025-12-26_14h11-48s"])
        writer.writerow(["filename_frame", "name_banner", "time_star", "time_end","text"])
        
        
        # img = cv2.imread("data/banners/frames/bandeau_13.00.png")
        for img_path in frames:
        
            img = cv2.imread(str(img_path))
            # Prétraitement de l'image pour améliorer la reconnaissance OCR
            # Conversion en niveaux de gris
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) 
            
            # Application d'un filtre CLAHE pour améliorer le contraste
            clahe = cv2.createCLAHE(2.0, (8,8))
            # Application du CLAHE
            gray = clahe.apply(gray)
            # print(gray)
            
            # Calcul de l'intensité moyenne de gris 
            mean_intensity = gray.mean()
            
            #Revoir le traitement de contrate different texte
            if mean_intensity < 127:
                # Texte clair sur fond sombre (banniere noire)
                _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            else:
                # Texte sombre sur fond clair (banniere blanche)
                _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
            
            # Texte clair sur fond sombre (banniere noire)
            # _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
            
            
            # Application d'un seuillage adaptatif
            thresh = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31, 10
            )

            # Utilisation de pytesseract pour extraire le texte
            raw_text = pytesseract.image_to_string(thresh, lang='fra')  # 'fra' pour français
            clean_text = clean_ocr_text(raw_text)
            print(f"{img_path} - Texte détecté:", clean_text)
             
           

            writer.writerow([
                img_path,
                extract_info_file(img_path, "type_banner"),
                extract_info_file(img_path, "start"),
                extract_info_file(img_path, "end"),
                clean_text
            ])
    
def main ():
    """
    freezedetect=n=0.003:d=2
    n= : Mesure la différence entre deux frames (Plus le nombre est petit → plus strict (sensible))
    d=: durée minimale (en secondes) L’image doit rester quasi identique pendant au moins 2 secondes
    """

   
    logger.info("Détection du timestamp freeze des bannières...")
    # logger.info("Check image color...")
    # img_conform, num  = detect_colors_banners()
    # if img_conform:
    #     logger.info(f" ✅ Image conforme, ratio de pixels noirs : {num:.2%}")
    # else:
    #     logger.warning(f"Image non conforme, ratio de pixels noirs : {num:.2%}")
    
    
    for type_banner in bannerss:
        print(type_banner)
        logger.info(f"Processing banner layout: {type_banner['name']} with crop: {type_banner['crop']}")
        COMMAND = f"""
        ffmpeg -i 
        data/ingest/segment_2025-12-26_14h11-48s.ts
        -vf "{type_banner['crop']},fps=0.5,{type_banner['freeze']}"
        -f null -
        """
        cmd = COMMAND.replace('\n', ' ')
        cmd = cmd.strip()
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        freezes = []
        freeze_start = None
        freeze_end = None
        freeze_duration = None
        reg_start = re.compile(r"freeze_start:\s*([0-9.]+)")
        reg_end = re.compile(r"freeze_end:\s*([0-9.]+)")
        reg_duration = re.compile(r"freeze_duration:\s*([0-9.]+)")

        while True:
            line = p.stdout.readline()
            if not line:
                break
            logger.info(line.decode('utf-8').strip())
            
            if "freeze_start" in line.decode("utf-8").strip():
                if reg_start.search(line.decode("utf-8").strip()):
                    freeze_start = float(reg_start.search(line.decode("utf-8").strip()).group(1))
                # current_start = float(line.decode('utf-8').search("freeze_start: ([0-9.]+)", line).group(1))
                    print("❄️❄️ Freeze start detected:", freeze_start)
            
            if "freeze_duration" in line.decode("utf-8").strip():
                if reg_duration.search(line.decode("utf-8").strip()):
                    freeze_duration = float(reg_duration.search(line.decode("utf-8").strip()).group(1))
                # current_start = float(line.decode('utf-8').search("freeze_start: ([0-9.]+)", line).group(1))
                    print("❄️❄️ Freeze duration detected:", freeze_duration)
                    
                
            if "freeze_end" in line.decode("utf-8").strip():
                if reg_end.search(line.decode("utf-8").strip()):
                    freeze_end = float(reg_end.search(line.decode("utf-8").strip()).group(1))
                # current_start = float(line.decode('utf-8').search("freeze_start: ([0-9.]+)", line).group(1))
                    print("❄️❄️ Freeze end detected:", freeze_end)
                    
                    if freeze_start is not None: 
                        middle_freeze = freeze_start + freeze_duration / 2
                        # logger.info(f"🎯 Middle Frame for OCR à t={middle_freeze:.2f}s")
                        print(f"🎯 Middle Frame for OCR à t={middle_freeze:.2f}s")
                        
                        
                      
                        # p_extract.wait()
                        extract_banners_in_folder("data/ingest/segment_2025-12-26_14h11-48s", type_banner['crop'], type_banner['name'], freeze_start, freeze_end, middle_freeze  )
                        
                        #Reset freeze
                        freeze_start = None
                        freeze_duration = None
                        freeze_end =  None
                    
                        # logger.info("✅ Extraction des bannières terminée.")            

        print("✅ Détection du timestamp freeze des bannières terminée.")
        # print("Détection bg color img")
        # banners = filter_on_file("frames")

        # for b in banners:
        #     print(b)
        
        # print("✅ Détection bg color img")
        
        #Ecriture fichier CSV
    write_csv(type_banner["name"])

    