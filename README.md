<div align='center' markdown> 
<img src='https://i.imgur.com/UdBujFN.png' width='250'/> <br>

# Cleaner

<p align='center'>
  <a href='#overview'>Overview</a> •
   <a href='#How to Run'>How to Run</a> •
</p>

[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/cleaner)

</div>

## Overview

This application allows admins to clear the teams folders for all teams in an instance over a period of time(in days).
Cleaning in teams folders will be carried out in the following ways:

`/tmp/supervisely/export`, `/Export-as-masks`, `/Export-to-Supervisely`, `/yolov5_format`, `/Export to COCO`, `/ApplicationsData/Export-to-Pascal-VOC`, `/activity_data`, `/reference_items`, `/Export only labeled items`, `/ApplicationsData/Export-Metadata`, `/cityscapes_format`, `/video_from_images`, `/tags_to_urls`, `/export-to-dota`.
All these paths are used for exporting data and many users forget to empty these folders after they finish their work.
This is necessary to delete obsolete temporary data that is no longer used and takes up a lot of space on the instance.

After the cleaning is finished, the application will continue to run in the background and resume cleaning after a specified period of time(in days). You can stop it in `Workspace Tasks`.

## How to Run

1. Add Cleaner to your team from Ecosystem.

2. Run App.

3. Set period of time you want to clear teams folders(in days).

4. Set the sleep time after which the application will resume its work(in days).
