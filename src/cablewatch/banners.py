import subprocess 
import os
import cv2
import csv
import numpy as np
import re
import pytesseract
import unicodedata

from loguru import logger
from pathlib import Path
from rapidfuzz import fuzz

#Layout program-title : 
# ffmpeg -i data/ingest/{name_video}.ts -vf "crop=240:84:977:ih-0,fps=0.5" data/banners/frames/banner_%03d.png

#Layout topic :
# ffmpeg -i data/ingest/{name_video}.ts -vf "crop=906:50:60:ih-144,fps=0.5" data/banners/frames/banner_%03d.png

#Layout breaking_news : 
# ffmpeg -i data/ingest/{name_video}.ts -vf "crop=909:89:60:ih-0,fps=0.5" data/banners/frames/banner_%03d.png

# Layou speaker: 
# ffmpeg -i data/ingest/segment_2025-12-26_14h19-05s.ts -vf "crop=909:39:60:ih-190,fps=0.5" data/banners/frames/banner_%03d.png

layout_banners : list = [
    {
        "name": "breaking_news",
        "crop": "crop=909:86:60:ih-0",
        "freeze": "freezedetect=n=0.002:d=3",
        "bg": "blanc",
    },
    {
        "name": "topic",
        "crop": "crop=906:50:60:ih-144",
        "freeze": "freezedetect=n=0.003:d=6",
        "bg": "noir",
    },
    {
        "name": "program_title",
        "crop": "crop=240:82:977:ih-0",
        "freeze": "freezedetect=n=0.005:d=7",
        "bg": "jaune",
    },
    {
        "name": "speaker",
        "crop": "crop=909:39:60:ih-190",
        "freeze": "freezedetect=n=0.005:d=3",
        "bg": "blanc",
    },
]

def extract_img_from_video(file: str, crop: str, type_banner: str, freeze_start: float = None, freeze_end: float = None,  middle_frame: float = None ) :
    """ 
    Extraction des images bannières à partir des vidéos
    """
    
    #Nom fichier sans extension
    path = file.stem
    
    #Creation du dossier frames s'il n'existe pas
    if not os.path.exists("data/banners/frames"):
        logger.info(f" ✅ Crèation du dossier data/banners/frames")
        os.makedirs("data/banners/frames", exist_ok=True)
        os.makedirs(f"data/banners/frames/{path}")
    
    #Creation du dossier frames/{path} s'il n'existe pas
    if not os.path.exists(f"data/banners/frames/{path}"):
        logger.info(f" ✅ Crèation du dossier data/frames/{path}")
        os.makedirs(f"data/banners/frames/{path}", exist_ok=True)

    
    #Extractiom de toutes les frames (middle_frame = None)
    if middle_frame == None: 
        COMMAND = f"""
        ffmpeg 
        -i {file} 
        -vf "{crop},fps=0.5,fps=1" 
        data/banners/frames/{path}/frame_{path}_banner_%03d.png
        """
        
    #Extration de l'img
    else : 
        COMMAND = f"""
        ffmpeg -y  
        -ss {middle_frame} 
        -i {file} 
        -vf "{crop}"
        -frames:v 1  
        data/banners/frames/{path}/frame_{path}_banner_{type_banner}_{freeze_start}_{middle_frame:.2f}_{freeze_end}.png
        """
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

def check_bg_color_banner (image_path, min_ratio=0.6) -> tuple:
    """
    Vérifie la couleur de fond d'une image.
    """
    #Lecture de l'image
    img = cv2.imread(image_path)
    
    if img is None:
        return False, "image_not_loaded", 0.0
     
    #
    h, w = img.shape[:2]
    total = h * w

    # Conversion img gris
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    #Calcul el ration de blanc, noir ou gris
    black_ratio = np.sum(gray < 40) / total
    white_ratio = np.sum(gray > 210) / total
    light_gray_ratio = np.sum((gray >= 170) & (gray <= 210)) / total

    # Utilisation hsv pour background jaune 
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Calcal des differentes intensité de jaune
    lower_yellow = np.array([15, 80, 80])
    upper_yellow = np.array([40, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    yellow_ratio = np.sum(yellow_mask > 0) / total

    
    if black_ratio >= min_ratio:
        return True, "black", black_ratio

    if yellow_ratio >= min_ratio:
        return True, "yellow", yellow_ratio

    if white_ratio >= min_ratio:
        return True, "white", white_ratio

    # fond blanc + texte gris clair
    if light_gray_ratio >= min_ratio:
        return True, "light_gray", light_gray_ratio

    return False, "no_dominant_background", max(
        black_ratio, white_ratio, yellow_ratio, light_gray_ratio
    )

def extract_info_name_img (path: Path, word: str = "timestamp_start")  -> str:
    """
    
    Extrait les informations de nom d'image.
    
    """
    
    #Nom fichier sans extension
    path = path.stem
     
    # On split le nom du fichier par "_"
    parts = path.split("_")  
    
    # On récupère les infos
    type_banner = parts[5]
    
    if "breaking" in type_banner or "program" in type_banner:
        start = float(parts[7])
    else:
        start = float(parts[6])
    
    if "breaking" in type_banner or "program" in type_banner:
        end = float(parts[9])
    else:
        end = float(parts[8])

    if word == "timestamp_start":
        return start
    
    if word == "timestamp_end":
        return end
    else:
        if "breaking" in type_banner or "program" in type_banner:
            return f"{parts[5]}_{parts[6]}"  
        else:
            return type_banner
    
def clean_raw_ocr(text: str) -> str:
    """
    Nettoie le texte brut extrait par OCR.
    """
    # Supression des caractères indésirables (saut de ligne, |, etc...)
    text = text.replace('\n', ' ')
    text = text.replace('|', ' ')
    text = text.replace('[', ' ') 
    text = text.replace(']', ' ')
    return " ".join(text.split())

def score_best_text (text: str) -> int:
    """
    Calcule un score pour déterminer la qualité du texte OCR.
    """
    if not text:
        return 0

    score = 0
    score += len(text)

    # Enlève du score si les caractères OCR sont moches
    score -= sum(text.count(c) for c in "_|[]{}")

    # Enlève du score si mots improbables
    score -= sum(1 for w in text.split() if len(w) > 12)

    # Ajoute au score si accents (français réel)
    score += sum(1 for c in text if c in "éèàùçôêî")

    return score

def final_clean_text(text: str) -> str:
    
    """
    Nettoie définitivement le texte OCR.
    """
    
    #Supression des caractères indésirable 
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'\s+([,.:;!?])', r'\1', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('""', '"')
    text = re.sub(r'""+', '"', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def select_best_text(items, similarity=85) -> list:
    
    """
    Sélectionne le meilleur texte parmi des items similaires.
    """
    merged = []

    for item in items:
        found = False

        for m in merged:
            #Comparaison de la similitude entre les lignes
           if (
                item["banner_type"] == m["banner_type"]
                # and item["banner"] in "breaking-news"
                and fuzz.ratio(item["banner_content"], m["banner_content"]) >= similarity
            ):
                # fusion temporelle
                m["timestamp_start"] = min(m["timestamp_start"], item["timestamp_start"])
                m["timestamp_end"] = max(m["timestamp_end"], item["timestamp_end"])

                # Garde le texte le plus long (souvent plus propre)
                if len(item["banner_content"]) > len(m["banner_content"]):
                    m["banner_content"] = item["banner_content"]
                
                # Test du meilleur score entre item et m (choix)
                if score_best_text(item["banner_content"]) > score_best_text(m["banner_content"]):
                 m["banner_content"] = item["banner_content"]

                found = True
                break

        if not found:
            merged.append(item.copy())

    return merged

def write_csv(path_file: str) :
    """
    
    Ecriture du fichier csv des bannières extraites.
    
    """
    #Nom fichier sans extension
    path = path_file.stem
    
    #Creation du fichier csv
    if not os.path.exists("data/banners/csv"):
        os.makedirs("data/banners/csv", exist_ok=True)
    
    # Trie des frames en fonction des nom de fichiers
    frames = sorted(Path(f"data/banners/frames/{path}").glob("*.png"), key=extract_info_name_img)
    
    # Ecriture du csv
    with open(f"data/banners/csv/banners_{path}.csv", "w", newline="", encoding="utf-8") as f:
        
        #Elements de base du csv
        writer = csv.writer(f)
        writer.writerow(["Name File", f"program_{path}"])
        # writer.writerow(["filename_frame", "banner_type", "timestamp_start", "timestamp_end","banner_content"])
        writer.writerow([ "banner_type", "timestamp_start", "timestamp_end","banner_content"])
        
        results = []
       
       
        for img_path in frames:
            
            #Lecture de mon image 
            img = cv2.imread(str(img_path))

            # Conversion en niveaux de gris
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) 
            
            # Application d'un filtre CLAHE (pour améliorer le contraste)
            clahe = cv2.createCLAHE(2.0, (8,8))
    
            # Application du CLAHE
            gray = clahe.apply(gray)
            
            #Check la validation bg de l'image 
            valid, bg_type, ratio = check_bg_color_banner(img_path)
           
            # logger.debug(
            #         f"{img_path.name} | bg={bg_type} | confidence={ratio:.2f}"
            #     ) 
            
            #si l'image n'est pas valide - pas de bg dominant 
            if not valid:
                logger.debug( 
                    f"❌ Image not valid {img_path.name} | bg={bg_type} | confidence={ratio:.2f}"
                ) 
                continue
            
            #Appliquer un seuillage adaptatif pour améliorer la lisibilité du texte
            thresh = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31, 10
            )

            if bg_type in ("black", "yellow"):
                thresh = cv2.bitwise_not(thresh)
            
            

            # Utilisation de pytesseract pour extraire le texte
            raw_text = pytesseract.image_to_string(thresh, lang='fra', config="--psm 6 --oem 3")   
            
            #Pré-clean du text 
            clean_text = clean_raw_ocr(raw_text)
            # print(f"{img_path} - Texte détecté:", clean_text)
             
        
            # writer.writerow([
            #     # img_path,
            #     extract_info_name_img(img_path, "banner_type"),
            #     extract_info_name_img(img_path, "timestamp_start"),
            #     extract_info_name_img(img_path, "timestamp_end"),
            #     clean_text
            # ])
            
            results.append({
                "banner_type": extract_info_name_img(img_path, "banner_type"),
                "timestamp_start": extract_info_name_img(img_path, "timestamp_start"),
                "timestamp_end": extract_info_name_img(img_path, "timestamp_end"),
                "banner_content": clean_text
            })
        
        #Selectionne les meilleurs resultats simillaires
        clean_results = select_best_text(results)
        
        #Ecriture du csv
        for row in clean_results:
            writer.writerow([
                # img_path,
                row["banner_type"],
                row["timestamp_start"],
                row["timestamp_end"],
                final_clean_text(row["banner_content"])
            ])
    
def main (path_file):
    """
    
    Extraction des bannières à partir des vidéos
    
    """

   
    logger.info("Détection du timestamp freeze des bannières...")
    
    #Parcours des différents layout de bannières
    for type_banner in layout_banners:
        
        
        logger.info(f"Processing banner layout: {type_banner['name']} with crop: {type_banner['crop']}")
        
        COMMAND = f"""
        ffmpeg -i 
        {path_file}
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
        
        # Regex pour extraire les informations de freeze
        reg_start = re.compile(r"freeze_start:\s*([0-9.]+)")
        reg_end = re.compile(r"freeze_end:\s*([0-9.]+)")
        reg_duration = re.compile(r"freeze_duration:\s*([0-9.]+)")

        while True:
            line = p.stdout.readline()
            
            if not line:
                break
            
            # logger.info(line.decode('utf-8').strip())
            
            if "freeze_start" in line.decode("utf-8").strip():
                if reg_start.search(line.decode("utf-8").strip()):
                    freeze_start = float(reg_start.search(line.decode("utf-8").strip()).group(1))
                    # print("❄️❄️ Freeze start detected:", freeze_start)
            
            if "freeze_duration" in line.decode("utf-8").strip():
                if reg_duration.search(line.decode("utf-8").strip()):
                    freeze_duration = float(reg_duration.search(line.decode("utf-8").strip()).group(1))
                    # print("❄️❄️ Freeze duration detected:", freeze_duration)
                    
                
            if "freeze_end" in line.decode("utf-8").strip():
                if reg_end.search(line.decode("utf-8").strip()):
                    freeze_end = float(reg_end.search(line.decode("utf-8").strip()).group(1))
                    # print("❄️❄️ Freeze end detected:", freeze_end)
                    
                    if freeze_start is not None: 
                        middle_freeze = freeze_start + freeze_duration / 2
                        # logger.info(f"🎯 Middle Frame for OCR à t={middle_freeze:.2f}s")
                        # print(f"🎯 Middle Frame for OCR à t={middle_freeze:.2f}s")
                        # p_extract.wait()
                        
                        extract_img_from_video( path_file , type_banner['crop'], type_banner['name'], freeze_start, freeze_end, middle_freeze )
                        
                        #Reset freeze
                        freeze_start = None
                        freeze_duration = None
                        freeze_end =  None
                    
                        # logger.info("✅ Extraction des bannières terminée.")            

            if freeze_start and not freeze_duration:
                logger.info(f"❄️ Freeze ignoré" )
                
      
        
        logger.info(f"✅ Fin processing banner layout: {type_banner['name']} with crop: {type_banner['crop']}")
    
    logger.info(f"Ecriture CSV pour le fichier vidéo: {path_file.name}")    
    write_csv( path_file)
    logger.info("✅ Fin écriture CSV.")

    