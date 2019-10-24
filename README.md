# Galicaster Select User
a Galicaster plugin that allows a user to enter a student, staff, or temporary staff number (according to configured REGEXP).

The user information and series information is requested from Opencast (`users/{user_id}.json` and `api/series/`).

And if the user does not have a series then one will be created (`api/series/`).

On completion of the popup Galicaster will display the name of the user and will then on recording ingest it into the user's series.

## Installation

1. Copy `set_user.py` to `/[path to install]/Galicaster/galicaster/plugins/set_user.py`
2. Copy over the content of `resources/ui` to `/[path to install]/Galicaster/resources/ui`
3. If not already part of the codebase also copy:
  * `galicaster/classui/recorderui.py` to `/[path to install]/Galicaster/galicaster/classui/recorderui.py`
  * `galicaster/opencast/client.py` to `/[path to install]/Galicaster/galicaster/opencast/client.py`

_NOTE:_
  * `galicaster/classui/recorderui.py` contains changes to display the name of the selected user.
  * `galicaster/opencast/client.py` contains new methods that are used to communicate with Opencast External API.
  * `resources/ui/series_metadata_template.json` contains the template for creating the metadata for the new series.
  * `resources/ui/acl_template.json` contains the template for creating ACL's for the new series.
  * `resources/ui/set_user.glade` contains the UI elemnts for popup that shows the user selection input.

## Configuration
```
vi /etc/galicaster/conf.ini

[plugins]
set_user = True

[set_user]
# The regular expression that defines a valid student, staff, or temporary staff number
rexexp = "[0-9]{8}|[a-zA-Z]{6}[0-9]{3}|[T|t][0-9]{7}"

# Additional filter parameters that might be usefull in finding the correct type of series
# e.g ,subject:Personal
filter = "%2Csubject%3APersonal"
```