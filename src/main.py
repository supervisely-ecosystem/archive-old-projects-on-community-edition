import os, time
from datetime import datetime, timedelta
import supervisely as sly
from supervisely.io.fs import archive_directory, remove_dir, silent_remove
from dotenv import load_dotenv


if sly.is_development():
    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


api = sly.Api.from_env()

days_storage = int(os.environ["modal.state.clear"])
sleep_time = int(os.environ["modal.state.sleep"]) * 86400
del_date = datetime.now() - timedelta(days=days_storage)
gb_format = 1024 * 1024 * 1024
storage_dir = sly.app.get_data_dir()


def sort_by_date(projects_info):
    projects_to_del = {}
    for project_info in projects_info:
        project_date = project_info.updated
        if project_date < del_date:
            projects_to_del[project_info.id] = project_info.name

    return projects_to_del


def upload_arch_to_dropbox(archive_path):
    pass


def main():

    while True:
        teams_infos = api.team.get_list()
        sly.logger.info("Start archiving old projects")
        for team_info in teams_infos:
            team_id = team_info[0]
            team_name = team_info[1]
            workspaces_info = api.workspace.get_list(team_id)

            for workspace_info in workspaces_info:
                workspace_id = workspace_info[0]
                workspace_name = workspace_info[1]

                projects_info = api.project.get_list(workspace_id)
                projects_to_del = sort_by_date(projects_info)

                sly.logger.info(
                    "Check old projects for {} team, {} workspace".format(team_name, workspace_name)
                )

                for project_id in projects_to_del.keys():
                    dest_dir = os.path.join(storage_dir, str(project_id))
                    sly.Project.download(api, project_id=project_id, dest_dir=dest_dir)
                    archive_path = dest_dir + ".tar"
                    archive_directory(dest_dir, archive_path)
                    remove_dir(dest_dir)
                    link_to_restore = upload_arch_to_dropbox(archive_path)  # TODO
                    sly.logger.info(
                        "Project with name {} was archived, link to restore: {}".format(
                            projects_to_del[project_id], link_to_restore
                        )
                    )
                    api.project.remove(project_id)
                    silent_remove(archive_path)  # or move to backup?

        time.sleep(sleep_time)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
