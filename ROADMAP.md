# ROADMAP

## Version 1


Pour la version 1 on va se limiter à une ochrestration la plus simple possible.
On reste en local: pas de déploiement sur VM. On va également ignorer les programmes de nuits
qui semblent différent des programmes de jours (rediffusion, bandeaux, ...) et se limiter à la plage horaire ``6h30 -> 0h00``.
On vise également les *features* suivantes:

### Ingest complet (avec de bons *timestamps*) 
 
 [seb / done]
 voir ``README.rst``


### Fournir une interface de programation pour itérer "proprement" sur les segments d'ingest
[seb / done]
 voir les exemples dans ``cli.py`` de la forme ``tlex_xxx()``


### Extraction des bandeaux (nom de l'émission, locuteur, topic) vers un fichier CSV ou une base 

[rachel / wip]
  
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

**Note:** *insérer le mot savant ici ;)*

**Note:** *damien a trouvé c'est* **idempotence**

   
### Extraction de l'audio et transcription en texte puis stockage dans un fichier CSV ou une base
   
[jean / seb / wip]
   
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

[not started]

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

[not started]
   
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


## Bac à sable / Open points / Issues

- Lancer ``cablewatch-ingest`` pendant plusieurs heures (jours ?) afin d'obtenir des données d'ingest

[seb / wip] Ca semble marcher (Ca a tourné 6 jours et on a ~40G de video)

- Trouver un moyen d'installer (script d'install ?) la bonne version de ``ffmpeg`` sans passer
par le packet manager de l'OS.
    - sous Linux
    - sous Mac
[seb / wip] ``devel.Dockerfile``

- Fournir un ``Dockerfile`` pour le dev (notamment pour avoir la bonne version de ``ffmpeg``)
[seb / wip] ``devel.Dockerfile``
 il manque l'exposition du port

- Utiliser ``docker`` et/ou ``docker compose`` pour le déploiement sur VM
[not started]

- Utiliser ``airflow`` ou ``prefect`` pour l'orchestration du *batch* (extraction et génération des documents)
    - pouvoir arrêter/demarrer l'ingest à des heures convenues
    - pouvoir faire ``import cablewatch`` depuis les tâches de l'orchestrateur
    - ``prefect`` semble plus *light* à déployer
[damien / wip]
    
- Mise en place d'un orchestrateur minimaliste ``apscheduler``
[seb / done]

- extraction de l'audio et transcription *voice-to-text* vers un fichier ou une base:
    - Open Source: Whisper v3 (dans Groq environmment)
    - GCP: Speech-to-text:chirp_3
    - Open Source: pyannote (via Hugging Face)
    - Open Source: WhisperX
[jean / wip]

- Etudier comment un LLM pourrait répondre aux questions de l'utilisateur en se basant sur des documents générés à partir du stream
  Est-ce que les questions utlisateurs sont prédéfinies à l'avance ou pas ?
[jean / wip]

- on fait des tests avec ``pytest`` ? - on en fait quelques uns juste pour la forme ;)
[seb / done] ``test_codequality.py test_gcp.py  test_sanity.py``

- choix du type de base ? ou manipulation des ``CSV`` avec ``pandas`` ?
[rachel / wip] Utilisation du module ``csv`` pour la tâche d'extration des *banners*
[seb / wip] Utilisation du module ``duckdb`` pour la tâche d'extration du *speech*

- Quand la chaine passe en mode "Edition spéciale" les bandeaux n'ont plus le même format :(

- Avec l'ingest il peut y avoir des problemes d'authentification sur le *stream* youtube
    - *workaround*: utiliser l'option ``--cookies-from-browser chrome`` et bien s'authentifier avec chrome sur youtube
    - voir branche ``main``
    - pour le déploiement il va falloir trouver une autre solution (token d'API ou un truc du genre)
 [seb / wip]

- checker la qualité du code avec un outil comme ``ruff`` ou ``blake``
[seb / done] ``test_codequality.py``

- il faudrait un système d'authentification minimaliste pour le service web
[not started]

- **[bug ingest]** si la commande ``yt-dlp | ffmpeg`` échoue, elle *restart* immédiatement (après 300ms). En cas d'erreurs successives c'est pas très heureux. Il faudrait allonger le temps avant *restart* dans ces cas là ou bien lever une erreur fatale. [seb / done]

- si on met en production, on ne pourra pas conserver tous les segments video pour des raisons évidentes de place. Par contre on pourra conserver les ``.csv`` et les documents générés. Donc il faudra orchestrer le *cleanup* des segments video.
[not started]

- **[bug ingest]** dans les timelines. L'utilisation de ``-f concat`` marche mal. A remplacer par la génération de commandes ``ffmpeg`` mixant ``-ss``, ``-t`` et ``-filter_complex``. Voir ``seb-current-work1``
[seb / wip]
