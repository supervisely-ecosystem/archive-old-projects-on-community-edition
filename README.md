<div align='center' markdown> 
<img src='https://i.imgur.com/UdBujFN.png' width='250'/> <br>

# Old Projects Archivator

<p align='center'>
  <a href='#overview'>Overview</a> •
  <a href='#Preparation'>Preparation</a> •
  <a href='#How to Run'>How to Run</a> •
</p>

[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/archive-old-projects-on-community-edition)

</div>

## Overview

This application allows admins to archive team projects for choosen teams (even for all teams) in an instance that have been updated later than selected period of time (in days). 
Old and currently unused projects take up space that can be used more efficiently at the moment. If you plan to use a project at some point in the future, it is recommended to move it to a repository outside the ecosystem from where it can be imported back later if needed with other tool.

For archiving purposes it is stricktly recommended to use <a href="https://www.dropbox.com/">Dropbox</a> as a save storage.

After the archiving is finished, the application will continue to run in the background and resume archiving after a specified period of time (in days). You can stop it in `Workspace Tasks`.

## Preparation
1. At first you need to have an account on [Dropbox](https://www.dropbox.com/)
2. Go to [Dropbox developers](https://www.dropbox.com/developers) and create your App:
   - Choose an API "Scoped access"
   - Choose the type of access you need. You could choose any. 
3. After creation you need to configure your App Permissions -> Files and folders:
   - Metadata: read and write
   - Content: read and write 
4. Create file **dropbox.env** locally and put your keys from App Settings:
    ~~~
    app_key="key"
    app_secret="key"
    refresh_token="key"
    ~~~
    `refresh_token` can be obtained using [this solution](https://www.dropboxforum.com/t5/Dropbox-API-Support-Feedback/Get-refresh-token-from-access-token/td-p/596739)


## How to Run

1. Upload **dropbox.env** to "Team Files" in Ecosystem
2. Call context menu by clicking right button on file and choose "Run App"
3. Find Old Projects Archivator application in list and run
4. Choose team for which old projects will be archivated or just choose all with check-box
5. Set count of days for Project Age to archive Projects older than this period
6. Set the sleep time in days after which the application will resume its work
7. Run the App