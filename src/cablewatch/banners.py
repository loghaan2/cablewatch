import subprocess 
import os
from loguru import logger

#Layout carre jaune : 
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=246:86:977:ih-0,fps=0.5" frames/bandeau_%03d.png

#Layout carre noir :
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=908:56:60:ih-145,fps=0.5" frames/bandeau_%03d.png

#Layout carre Blanc actualite : 
# ffmpeg -i data/ingest/segment_2025-12-26_14h11-48s.ts -vf "crop=909:89:60:ih-0,fps=0.5" frames/bandeau_%03d.png

# Layou carre blanc interlocuteur: 
# ffmpeg -i data/ingest/segment_2025-12-26_14h19-05s.ts -vf "crop=909:39:60:ih-190,fps=0.5" frames/bandeau_%03d.png

def extract_banners_in_folder(file: str, crop: str):
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
    if not os.path.exists("frames"):
        os.makedirs("frames", exist_ok=True)
    
    #Extraction des bannières (1 img/s)
    COMMAND = f"""
    ffmpeg -i 
    {file}.ts 
    -vf "{crop}" 
    frames/bandeau_%03d.png
    """
    cmd = COMMAND.replace('\n', ' ')
    cmd = cmd.strip()
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        line = p.stdout.readline()
        if not line:
            break
        logger.info(line.decode('utf-8').strip())

def main ():
    
    #exemple banniere carré noir
    logger.info("Chargement des bannières...")
    extract_banners_in_folder("data/ingest/segment_2025-12-26_14h11-48s", "crop=908:56:60:ih-145,fps=1")
    logger.info("✅ Extraction des bannières terminée.")
    logger.info("Détection du timestamp freeze des bannières...")
    COMMAND = """
    ffmpeg -i 
    data/ingest/segment_2025-12-26_14h11-48s.ts
    -vf "crop=908:56:60:ih-145,freezedetect=n=0.003:d=2"
    -f null -
    """
    cmd = COMMAND.replace('\n', ' ')
    cmd = cmd.strip()
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        line = p.stdout.readline()
        if not line:
            break
        logger.info(line.decode('utf-8').strip())
    print("✅ Détection du timestamp freeze des bannières terminée.")
    
    