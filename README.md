<div align='center' markdown> 
<img src="https://user-images.githubusercontent.com/115161827/229175411-59169316-8134-4158-a903-2e1eec528758.png" /> <br>

# Archive Projects to Dropbox

<p align='center'>
  <a href='#overview'>Overview</a> •
  <a href='#preparation'>Preparation</a> •
  <a href='#how-to-run'>How to Run</a>
</p>

[![](https://img.shields.io/badge/supervisely-ecosystem-brightgreen)](https://ecosystem.supervise.ly/apps/supervisely-ecosystem/archive-old-projects-on-community-edition)
[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/archive-old-projects-on-community-edition)
[![views](https://app.supervise.ly/img/badges/views/supervisely-ecosystem/archive-old-projects-on-community-edition.png)](https://supervise.ly)
[![runs](https://app.supervise.ly/img/badges/runs/supervisely-ecosystem/archive-old-projects-on-community-edition.png)](https://supervise.ly)

</div>

## Overview

This application allows admins to archive team projects for selected teams, or all teams if desired, which have been updated before a selected period (in days). Old and unused projects take up space that could be more efficiently used in the present. If you plan to use a project at some point in the future, it is recommended to move it to a repository outside the ecosystem, from where it can be imported back later using other tools.

To archive projects, it is strictly recommended to use <a href="https://www.dropbox.com/">Dropbox</a> as storage.

After the archiving process is complete, the application will continue to run in the background and resume archiving after a specified period (in days). If necessary, you can stop the application in `Workspace Tasks`.

## Preparation

1. You need to create an account on [Dropbox](https://www.dropbox.com/)
2. Go to [Dropbox developers](https://www.dropbox.com/developers) and create your App:
    - Choose an API: "Scoped access"
    - Choose the type of access you need. You can choose any.
3. After creating your app, you need to configure your app permissions for Files and Folders:
    - Metadata: read and write
    - Content: read and write
4. Create a file named "**dropbox.env**" locally and enter your keys from your App Settings:

   ```
   app_key="key"
   app_secret="key"
   refresh_token="key"
   ```

   `refresh_token`
   can be obtained using [this solution](https://www.dropboxforum.com/t5/Dropbox-API-Support-Feedback/Get-refresh-token-from-access-token/td-p/596739)


   ⚠️ if you use a member account of the Dropbox Business team, add one more line

   ```   
   dbx_user_id="dbmid"
   ```

   `dbx_user_id`
   can be obtained using [this solution](https://www.dropboxforum.com/t5/Discuss-Dropbox-Developer-API/Question-on-retrieving-the-dbmid-for-my-user/m-p/530350/highlight/true#M1991)
   
## How to Run

1. Upload "**dropbox.env**" to "Team Files" in Ecosystem.
2. To run the application, right-click on the file and choose "Run App" from the context menu.
3. Select "Old Projects Archivator" from the list of applications and run it.
4. Choose the team and workspace for which you want to archive old projects, or select "All available workspaces" using the checkbox.
5. Choose the types of projects for which you want to archive the old ones, and deselect the "All types" checkbox to see the selector.
6. Set the sleep time in days after which the application will resume its work.
7. Set the period equal to the number of days from today to the past. If the project has not been updated during (To) or before (From) this period, it will be added to the list. Or uncheck "Set range" to archive all available projects.
8. ⚠️ Don't change advanced options if you don't know what they do!
9. Finally, run the application.
   <img src="https://user-images.githubusercontent.com/115161827/229535768-c6eb4c21-7378-47af-a040-48e44785ee29.gif" />

The application will check projects, select those that meet the specified criteria based on the date, and process each one sequentially. During processing, a directory named `archive_{id}` will be created in the `supervisely_project_archives` directory of Dropbox, where `id` is the number of the task that the application is working on. Project archives named with the project `id` will be uploaded to this directory.
If the project size exceeds **348 GB**, the project will be split into parts and uploaded into a created in-advance subdirectory that is named with the project `id`.
After processing, the projects in the workspace will be marked as archived, and instead of the data, there will be a link to it on Dropbox.
