# ROADMAP

## Version 1


Pour la version 1 on va se limiter à une ochrestration la plus simple possible (un simple ``cron``).
On reste en local: pas de déploiement sur VM. On va également ignorer les programmes de nuits
qui semblent différent des programmes de jours et se limiter à la plage horaire ``7h00 -> 0h00``.
On vise également les *features* suivantes:

### Ingest complet (avec de bons *timestamps*) 
 
 [done]


### Fournir une de interface de programation pour itérer proprement sur les segments d'ingest

[seb]


### Extraction des bandeaux (nom de l'émission, locuteur, topic) vers un fichier CSV ou une base 

[rachel]
  
```
$ cablewatch-extract-banners <timerange>
```

On obtient dans ``banners.csv``:

| timestamp_begin | timestamp_end  | banner_type    | banner_content
|:----------------|:---------------|:---------------|-------------------------------
| Ta0             | Ta1            | show-title     | Tout est politique
| Tb0             | Tb1            | topic          | Crise agricole: un virage populiste ?
| Tc0             | Tc1            | locutor        | Antoine Bueno, Essayiste


Si on execute ``cablewatch-extract-banners`` avec le même ``timerange`` et en partant du principe
que les données d'ingest sont toujours là, ``banners.csv`` est inchangé.

**Note:** *Insérer le mot savant ici ;)*

   
### Extraction de l'audio et transcription en texte puis stockage dans un fichier CSV ou une base
   
[jean]
   
```
$ cablewatch-extract-speech <timerange>
```

On obtient dans ``speech.csv`` :

| timestamp_begin | timestamp_end | locutor    | text
|:----------------|:--------------|:-----------|:-----------------------------------
| Ta0             | Ta1           | locutor 1  | bla bla bla
| Tb0             | Tb1           | locutor 2  | blo blo blo
| Tc0             | Tc1           | locutor 1  | ah ah ah


Si on execute ``cablewatch-extract-speech`` avec le même ``timerange`` et en partant du principe
que les données d'ingest sont toujours là, ``speech.csv`` est inchangé.



### Reconstruire le programme de la chaîne de la journée spécifiée


```
$ cablewatch-generate-tvgrid <day>
```

Ca va constuire le fichier ``2025-12-26_tvgrid.json`` qui pourrait contenir quelque chose
comme ci-dessous à partir des données extraites précédemment:

```
{
    "document-type": "tvgrid"
    "date": 2025-12-26
    "tv-shows": [
        {
            "name": "La matinale",
            "begin": "06h29",
            "end": "07h40",
            "topics": ["Vote du budget", "Crise agricole", ...]
        },
        {
            "name": "L'invité politique",
            "begin": "07h45",
            "end": "08h33",
            "topics": [...]
        }
    ]
}
```

### Reconstruire pour chaques émissions de la journée spécifée le programme de la chaîne
   
```
$ cablewatch-generate-tvshowdetails <day>
```
    
A partir des informations extraites (CSV ou base), on reconstruit également des documents qui décrivent chaque émission, par exemple dans un fichier ``2025-12-26_la_matinale.json``:
    
```
{
    "document-type": "tv-show-details",
    "name": "La matinale",
    "begin": "2025-12-26 06h29",
    "end": "2025-12-26 07h40",
    "topics": [
        {
            "title": "Vote du budget",
            "locutors": ["Antoine Bueno Essayiste", "...", "..."]
            "speech": [
                {locutor=0, text="bla bla bla", 
                    timestamp_begin="...", timestamp_end="..."},
                {locutor=1, text="blo blo blo", "..."},
                {locutor=0, text="ah ah ah", "..."},
            ]
        }
    ]
}
```
    

## Bac à sable

- Utiliser ``docker`` pour le déploiement sur VM
- Utiliser``airflow`` ou ``prefect`` ou ``cron`` pour l'orchestration du *batch* (extraction
    et génération des documents)
- extraction de l'audio et transcription *voice-to-text* vers un fichier ou une base:
    - Open Source: Whisper v3 (dans Groq environmment)
    - GCP: Speech-to-text:chirp_3
    - Open Source: pyannote (via Hugging Face)
    - Open Source: WhisperX
- Etudier comment un LLM pourrait répondre aux questions de l'utilisateur en se basant sur des documents générés à partir du stream
- Est-ce que les questions utlisateurs sont prédéfinies à l'avance ou pas ?
- on fait des tests ? avec ``pytest`` ?
- choix du moteur de la base ? ou manipulation de ``CSV`` avec ``pandas``