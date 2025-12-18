.. |br| raw:: html

    <br/>


.. |nbsp| raw:: html

    &nbsp;


.. |big_hspace| raw:: html

    <span style="display:inline-block; width:40cm;">


================
 ``cablewatch``
================


|br|
|br|

Une proposition de projet pour la formation |br|
*Data Engineer* de **Artefact School of Data**

|br|

|big_hspace| Sébastien MATZ |br|
|big_hspace| ``batch-072-paris`` |br|
|big_hspace| *Décembre 2025*


En quelques mots
================

- analyser le direct d'une chaîne d'info en continue
  (comme ``france info`` par exemple)

- fournir des réponses à des questions en rapport
  avec ce qui a été diffusé sur la chaîne


Les questions
=============

- Quel était le sujet d'actualité majeur de la journée du 17 décembre ?

- Donne moi la liste des invités de l'émission ``La Matinale`` du 18 décembre ?

- (...)


Architecture du projet
======================


Archi(1): *Ingest*
==================

- *process* qui enregistre en continue le *live* à partir d'un flux
  que l'on trouvera sur internet

- l'enregistrement est découpé en segments (petit fichiers video ou *chunks*)
  de 30s environ

- les segments doivent être *taggés* avec un *timestamp*


Archi(2): Tranfos
=================

Périodiquement, sur les segments enregistrés: |br|

- extraire l'audio et faire du *voice-to-text*

- analyser les bandeaux standardisés (*image recognition*) de la chaîne
  pour retrouver de la meta-donnée (locuteur, émission en cours...)

- *cleanup*: une fois les segments video traités il faut les
  effacer (pour économiser de la place dans le *storage*)

|big_hspace| ==> c'est du *batch* !


Archi(3): Les bandeaux
======================

.. image:: /_static/images/franceinfo_frame.png



*A partir d'ici c'est un peu plus flou pour moi* 😉
===================================================

.. image:: /_static/images/velma.png
    :scale: 25%


Archi(4): Géneration de documents
=================================


- L'idée est de générer des documents à partir
  des données extraites et d'utiliser un ``LLM`` pour
  les exploiter

- on peut imaginer de faire un document par émission


Archi(5): Géneration de documents
=================================

- Ca a l'air de ressembler à du ``RAG`` ?

- il faut conserver l'information temporelle dans ces documents

|big_hspace| ==> *To be defined* mais c'est aussi du *batch* !


Archi(6): Résultats
===================

Résultat dans un document web:

- Est-ce que les questions sont prédéfinies à l'avance ?

- Présenter les questions/réponses de manière statique

- *chatbot* si les questions sont pas prédéfinies

|big_hspace| ==> *To be defined !*


Dernier slide 😁
================

:Ordres de grandeurs:
    - Taille des fichier video: ``~8M/min``
    - Locution chaînes d'info: ~170 mots/min
    - Taille d'un mot en francais: ``~6chars``

:Les technos:
    ``#python #ffmpeg #yt-dlp #fastapi #airflow #docker
    #web-front #LLM #RAG #GCP:Speech-to-Text #GCP:Vision``
