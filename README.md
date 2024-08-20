Capstone Monitoring System
==========================

This repository provides the code for the monitoring system for the Babraham capstone cluster.  It provides a web interface from which users can look at their data usage, the current job queue and their job history.

![Main Screen](../main/www/static/images/screenshots/front_screen.png?raw=true)
![Jobs](../main/www/static/images/screenshots/jobs.png?raw=true)
![Storage](../main/www/static/images/screenshots/storage.png?raw=true)
![Folders](../main/www/static/images/screenshots/folders.png?raw=true)
![All Storage](../main/www/static/images/screenshots/allstorage.png?raw=true)

Setting up the system
=====================

Create a venv
-------------

From the root of the repository

```
python -m venv venv
. venv/Scripts/activate
pip install -r requirements.txt
```

Create the database
-------------------

You'll need to have mongodb installed and know how to get to a root shell.

Copy the text from ```database/create_database_and_user.txt``` into the shell to create your basic setup.  

Once that's done run ```database/setup_database.py``` to check the connection and set up the collections you are going to use.


Start the app
-------------

From the shell in which you started the venv

Move to the ```www``` folder

```
flask --debug --app webapp.py run
```

This should start the server and you should have a basic system running on 127.0.0.1:5000

