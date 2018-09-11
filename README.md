# galicaster-select-user
a GC plugin that allows a user to enter a student number, validates it with confirmation, and sets up a series for that user and changes the GC default series as ad-hoc recs go to the right place.

```
pip install requests_futures
```

```
vi /etc/galicaster/conf.ini

[plugins]
set_user = True

[set_user]
url_find = http://[server]/api/find/
url_create = http://[server]/api/series/
rexexp_lecturer = "[0-9]{8}"
rexexp_learner = "[a-zA-z]{6}[0-9]{3}"
```