# cloud-based-speech-translator-generator

This repository contains a project for the *Cloud Computing* course at the Faculty of Mathematics and Information Science, Warsaw University of Technology.

The aim of this project was to build a cloud based solution. 
Ours utilizes Django with CloudRun, CloudSQL, Google Storage and various AI solution from Google Cloud.
The final product is a working web application.

Main features:
- Text to speech – Input text file and obtain a generated audio of the text
- Speech to text – Recognize speech and convert it into text 
- Translation - Optionally for both features above you can also translate the input into a chosen language
- File Support – Upload files (e.g., PDF, TXT, DOCX, MP3, WAV) for translation 
- History – Store previous notes for user reference 

## Contributors
- [@sokolowskij](https://github.com/sokolowskij)
- [@AgEwa](https://github.com/AgEwa)
- [@Sasimowskaz](https://github.com/Sasimowskaz)

## Instructions for setting up the web app

1. Authenticate with gcloud
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up everything with terraform
```bash
   terraform init
```
   ```bash
   terraform plan
   ```
   ```bash
   terraform apply
   ```
4. Go to the returned url