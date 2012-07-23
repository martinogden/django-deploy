django-deploy
=============

Inspired by [capistrano](https://github.com/capistrano/capistrano/), django-deploy is a [fabfile](http://docs.fabfile.org/en/1.3.1/index.html) to aid quick and easy setup and deployment of django-powered websites. Configured for use with git, ubuntu, apache virtual hosts, nginx, mod_wsgi and mysql / mysqlite3.


Installation
------------

Download the fabfile into the root of a django project (alongside `manage.py` etc.):

    git clone git://github.com/martinogden/django-deploy.git fabfile


Add the following settings to your `settings.py` file

    FABRIC_DOMAIN = 'your-domain.com'
    FABRIC_USER = 'Your SSH username'
    FABRIC_PASSWORD = 'Your SSH password'
    FABRIC_HOST = 'Your server IP'
    FABRIC_REPO = 'git@your-git-repository.git'

Optional:

    FABRIC_RELEASES = number of old releases to keep (default 5)


Usage
-----

From the root of your django project you can run the fab commands. The commands are in the format `fab <ENVIRONMENT> <COMMAND>` e.g. `fab staging deploy`.


Commands
=======

### bootstrap

Example: `fab production boostrap`.

 * create apache / nginx / mod_wsgi configuration files
 * create a new virtualenv
 * checkout the git repository
 * create static / media folders
 * Create database and initial schema (not including migrations)


- - -
### deploy

Example: `fab production deploy`.

 * checkout the latest release of the git repository
 * backup the current version - keeps last 5 (`settings.FABRIC_RELEASES`)
 * run south migrations
 * collect any new static files and move them to `settings.STATIC_ROOT`


- - -
### rollback

Example: `fab production rollback`.

Move project back to previous state, update migrations and static files


- - -
### test

Example: `fab production test deploy`.

Run all tests locally. Useful if chained before a deploy command as the deploy will not run if any tests fail.


- - -
### create_database

Example: `fab production create_database`.

Creates remote database and runs `syncdb`. Currently uses your ssh user and
password, @todo add facility to override this.


- - -
### sync_local_database

Example: `fab production sync_local_database`.

Update your local environment with data from remote database. Useful for
quickly accessting data to work with in development.


- - -
### sync_local_media

Example: `fab production sync_local_media`.

Same as above, but syncs remote user-uploaded media.


- - -
### django_admin

Example: `fab production django_admin:'migrate app 0002'`.

Small wrapper around remote `django-admin.py` command.


Requirements
-----------

 * django
 * fabric
 * south (for database migrations)


Authors
-------

 * [Martin Ogden](@martinogden)
 * [Sam Starling](@samstarling)


License
------

Licensed for use under [Attribution 3.0 unported](http://creativecommons.org/licenses/by/3.0/).
