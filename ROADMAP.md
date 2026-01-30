# ``ROADMAP.md``

<!-- after-titles -->

## Version 0


Pour la version 0 on va se limiter à une ochrestration la plus simple possible.
On va ignorer les programmes de nuits qui semblent différent des programmes de jours (rediffusion, bandeaux, ...) et se limiter à la plage horaire ``6h30 -> 0h00``.
On vise également les *features* suivantes:

### Ingest complet
 
 **[seb / done]** voir ``README.rst`` et ``report.rst``


### Fournir une interface de programation pour itérer "proprement" sur les segments d'ingest
**[seb / done]** voir ``README.rst`` et ``report.rst``
 

### Extraction des bandeaux (nom de l'émission, locuteur, topic) vers un fichier CSV, JSON ou une base

**[rachel / seb / done]**
  
```
$ cablewatch-banners <timerange>
```

On obtient un table:

| timestamp_begin | timestamp_end  | banner_type    | banner_content
|:----------------|:---------------|:---------------|-------------------------------
| Ta0             | Ta1            | show-title     | Tout est politique
| Tb0             | Tb1            | topic          | Crise agricole: un virage populiste ?
| Tc0             | Tc1            | locutor        | Antoine Bueno, Essayiste


Si on execute ``cablewatch-banners`` avec le même ``timerange`` et en partant du principe
que les données d'ingest sont toujours là, la table est inchangé.

**Note:** *insérer le mot savant ici ;)*

**Note:** *damien* a trouvé c'est **idempotence**

   
### Extraction de l'audio et transcription en texte
   
**[jean / seb / done]** on utilise l'API Google Speech en mode batch
   
```
$ cablewatch-speech <timerange>
```

On obtient dans une table:

| timestamp_begin | timestamp_end | locutor    | text
|:----------------|:--------------|:-----------|:-----------------------------------
| Ta0             | Ta1           | locutor 1  | bla bla bla
| Tb0             | Tb1           | locutor 2  | blo blo blo
| Tc0             | Tc1           | locutor 1  | ah ah ah


Si on execute ``cablewatch-speech`` avec le même ``timerange`` et en partant du principe
que les données d'ingest sont toujours là, la table est inchangé.



### Reconstruire pour chaques émissions de la journée spécifée un document (ou *papers*)

[seb / done]

```
$ cablewatch-papers <day>
```
    
A partir des informations extraites ci-dessus, on reconstruit des documents qui décrivent chaque émission, par exemple dans un fichier ``2025-12-26_la_matinale.json``:
    
```
{
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

- Lancer ``cablewatch-super`` pendant plusieurs jours afin d'obtenir des données d'ingest

    **[seb / done]** 

    Ca semble marcher (Ca a tourné 6 jours et on a ~40G de video)

- Trouver un moyen d'installer (script d'install ?) la bonne version de ``ffmpeg`` sans passer
par le packet manager de l'OS.
    - sous Linux
    - sous Mac

    **[seb / wip]**

- Fournir un ``Dockerfile`` pour le dev (notamment pour avoir la bonne version de ``ffmpeg``)

    **[seb / done]**

- Utiliser ``docker`` et/ou ``docker compose`` pour le déploiement sur VM

    **[not started]**

- Utiliser ``airflow`` ou ``prefect`` pour l'orchestration du *batch* (extraction et génération des documents)
    - pouvoir arrêter/demarrer l'ingest à des heures convenues
    - pouvoir faire ``import cablewatch`` depuis les tâches de l'orchestrateur
    - ``prefect`` semble plus *light* à déployer
    - ``apscheduler`` semble encore plus *light* et minimaliste (lib python)

    **[seb / done]** ``apscheduler`` !!!
    
- R&D de Jean sur l'extraction de l'audio et transcription *voice-to-text* vers un fichier ou une base:
    - Open Source: Whisper v3 (dans Groq environmment)
    - GCP: Speech-to-text:chirp_3
    - Open Source: pyannote (via Hugging Face)
    - Open Source: WhisperX

    **[jean / wip]**

- Etudier comment un LLM pourrait répondre aux questions de l'utilisateur en se basant sur des documents générés à partir du stream

  Est-ce que les questions utlisateurs sont prédéfinies à l'avance ou pas ?
  
    **[jean / wip]**

- on fait des tests avec ``pytest`` ? 
    on en fait quelques uns juste pour la forme ;)

    **[seb / done]** ``test_codequality.py test_gcp.py  test_sanity.py``

- choix du type de base ? ou manipulation de ``CSV`` / ``JSON`` ? avec ``pandas`` ?

- Quand la chaine passe en mode "Edition spéciale" les bandeaux n'ont plus le même format :(

- Avec l'ingest il peut y avoir des problemes d'authentification sur le *stream* youtube
    - *workaround*: utiliser l'option ``--cookies-from-browser chrome`` et bien s'authentifier avec chrome sur youtube
    - voir branche ``main``
    - pour le déploiement il va falloir trouver une autre solution (token d'API ou un truc du genre)
    - pas sûr que ca soit lié à l'authentification :|
 
     **[seb / wip]**

- checker la qualité du code avec un outil comme ``ruff`` ou ``blake``

    **[seb / done]** ``test_codequality.py``

- il faudrait un système d'authentification minimaliste pour le service web

    **[seb / done]** authentification basic avec ``aiohttp``

- **[bug ingest]** si la commande ``yt-dlp | ffmpeg`` échoue, elle *restart* immédiatement (après 300ms). En cas d'erreurs successives c'est pas très heureux. Il faudrait allonger le temps avant *restart* dans ces cas là ou bien lever une erreur fatale.
    
    **[seb / done]**

- si on met en production, on ne pourra pas conserver tous les segments video pour des raisons évidentes de place. Par contre on pourra conserver les ``.json`` ou ``.csv`` et les documents générés. Donc il faudra orchestrer le *cleanup* des segments video.

    **[not started]**

- **[bug ingest]** dans les timelines. L'utilisation de ``-f concat`` marche mal. A remplacer par la génération de commandes ``ffmpeg`` mixant ``-ss``, ``-t`` et ``-filter_complex``. Voir la branche ``seb-current-work1``

    **[seb / fixed]**
