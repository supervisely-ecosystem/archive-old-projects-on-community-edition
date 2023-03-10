<div align='center' markdown> 
<img src='https://i.imgur.com/UdBujFN.png' width='250'/> <br>

# Old Projects Archivator

<p align='center'>
  <a href='#overview'>Overview</a> •
  <a href='#Preparation'>Preparation</a> •
  <a href='#How to Run'>How to Run</a> •
  <a href='#Release notes'>Release notes</a>
</p>

[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/archive-old-projects-on-community-edition)

</div>

## Overview

This application allows admins to archive team projects for selected teams, or all teams if desired, which have been updated prior to a selected period of time (in days). Old and unused projects take up space which could be more efficiently used in the present. If you plan to use a project at some point in the future, it is recommended to move it to a repository outside the ecosystem, from where it can be imported back later using other tools.

To archive projects, it is strictly recommended to use <a href="https://www.dropbox.com/">Dropbox</a> as a save storage.

After the archiving process is complete, the application will continue to run in the background and resume archiving after a specified period of time (in days). If necessary, you can stop the application in `Workspace Tasks`.

## Preparation
1. You need to create an account on [Dropbox](https://www.dropbox.com/)
2. Go to [Dropbox developers](https://www.dropbox.com/developers) and create your App:
   - Choose an API: "Scoped access"
   - Choose the type of access you need. You can choose any. 
3. After creating your app, you need to configure your app permissions for Files and Folders:
   - Metadata: read and write
   - Content: read and write 
4. Create a file named "**dropbox.env**" locally and enter your keys from your App Settings:
    ~~~
    app_key="key"
    app_secret="key"
    refresh_token="key"
    ~~~
    `refresh_token` can be obtained using [this solution](https://www.dropboxforum.com/t5/Dropbox-API-Support-Feedback/Get-refresh-token-from-access-token/td-p/596739)


## How to Run

1. Upload "**dropbox.env**" to "Team Files" in Ecosystem.
2. To run the application, right-click on the file and choose "Run App" from the context menu.
3. Select "Old Projects Archivator" from the list of applications and run it.
4. Choose the team for which you want to archive old projects, or select all teams using the check-box.
5. Set the number of days for the project age. Any project older than this period will be archived.
6. Set the sleep time in days after which the application will resume its work.
7. Finally, run the application.

## Release notes
#### v0.0.1
 - Works only with project type: Image