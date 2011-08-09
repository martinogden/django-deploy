from datetime import datetime

from fabric.api import local, run, sudo, prefix, cd, env
from fabric.contrib import django
from fabric.contrib.files import upload_template, append
from fabric.contrib.console import confirm
from fabric import tasks
from fabric.utils import abort, puts

from django.conf import settings

django.settings_module('settings.development')
if not hasattr(settings, 'FABRIC_DOMAIN'):
    abort('You must set FABRIC_DOMAIN in your settings file')

env.domain = settings.FABRIC_DOMAIN
env.path = local('pwd')
env.user = 'cahoona'
env.hosts = ['92.63.136.213']
env.password = 'v-Fj9P@8'
# Allow fabric to restart apache2
env.always_use_pty = False

# Number of previous deploy releases to keep
RELEASE_COUNT = 5

# @link https://bitbucket.org/dhellmann/virtualenvwrapper/issue/62/hooklog-permissions#comment-229798
# env.shell = '/bin/bash --noprofile -l -c'


class BaseTask(tasks.Task):

    def run(self):
        if not hasattr(env, 'name'):
            abort('You must specify an environment to deploy to\n\n'\
                  'e.g. fab production prepare_environment')

    def get_local_settings(self):
        django.settings_module('settings.development')
        return settings

    def select_env(self, name='staging'):
        env.name = name
        env.repo = env.domain.replace('.', '_')
        env.virtual_env = '$WORKON_HOME/%(domain)s' % env
        django.settings_module('settings.%(name)s' % env)


class Production(BaseTask):
    """
    Run tasks in production environment
    """
    name = 'production'

    def run(self):
        return self.select_env('production')


class Staging(BaseTask):
    """
    Run tasks in staging environment
    """
    name = 'staging'

    def run(self):
        env.domain = 'staging.%(domain)s' % env
        return self.select_env('staging')


class Bootstrap(BaseTask):
    """
    Prepare a virtualenv with apache2 and nginx config files
    """
    name = 'bootstrap'

    def run(self):
        super(Bootstrap, self).run()
        self.create_virtualenv()
        self.clone_git_repo()
        self.create_folders()
        self.upload_config_files()

    def create_virtualenv(self):
        sudo('chmod 777 $WORKON_HOME/hook.log')
        run('mkvirtualenv %(domain)s' % env)
        # append env vars to virtualenv activate file
        append('%(virtual_env)s/bin/activate' % env, ['',
            'export DJANGO_SETTINGS_MODULE=settings.%(name)s' % env,
            'export PYTHONPATH=$VIRTUAL_ENV/project',
            ''])

    def clone_git_repo(self):
        # Checkout git repo from cahoona VM-3
        run('mkdir -p %(virtual_env)s/releases' % env)
        with cd('%(virtual_env)s/releases' % env):
            run('git clone git@92.63.136.209:%(repo)s.git current' % env)
        # symlink project to current release
        run('ln -s %(virtual_env)s/releases/current %(virtual_env)s/project'\
            % env)

    def create_folders(self):
        # Create dirs
        vhost_root = '/var/www/vhosts/%(domain)s' % env
        for folder in ['media', 'static', 'apache', 'log']:
            run('mkdir -p %(vhost_root)s/%(folder)s' % locals())

        # Permissions
        for folder in ['media', 'log']:
            run('chmod 777 %(vhost_root)s/%(folder)s' % locals())

    def upload_config_files(self):
        vhost_root = '/var/www/vhosts/%(domain)s' % env
        kwargs = dict(context=env, use_sudo=True, backup=False)
        # wsgi
        upload_template('%(real_fabfile)s/conf/wsgi.conf' % env,\
                        vhost_root + '/apache/%(name)s.wsgi' % env, **kwargs)
        # apache
        upload_template('%(real_fabfile)s/conf/apache.conf' % env,\
                    '/etc/apache2/sites-available/%(domain)s' % env, **kwargs)
        sudo('a2ensite %(domain)s' % env)
        sudo('service apache2 restart')

        # nginx
        upload_template('%(real_fabfile)s/conf/nginx.conf' % env,\
                    '/etc/nginx/sites-available/%(domain)s' % env, **kwargs)
        sudo('ln -sf /etc/nginx/sites-available/%(domain)s '\
             '/etc/nginx/sites-enabled/%(domain)s' % env)
        sudo('service nginx restart')


class Deploy(BaseTask):
    """
    Deploy project to remote server
    """
    name = 'deploy'

    def run(self, update_requirements=True, migrate=True, static=True):
        super(Deploy, self).run()
        sudo('chmod 777 $WORKON_HOME/hook.log')

        # Move current to old release
        with cd('%(virtual_env)s/releases' % env):
            now = datetime.now().strftime('%Y%m%d%H%M%S')
            run('cp -R current %s' % now)

        with cd('%(virtual_env)s/project' % env):
            run('git pull')
            with prefix('workon %(domain)s' % env):
                if update_requirements:
                    run('pip install -r REQUIREMENTS')
                if migrate:
                    run('django-admin.py migrate --all')
                if static:
                    run('django-admin.py collectstatic --noinput')
        sudo('service apache2 graceful')


class Rollback(BaseTask):
    """
    Rollback remote project to previous release if one exists
    """
    name = 'rollback'

    def run(self, update_requirements=True, migrate=True, static=True):
        super(Rollback, self).run()
        with cd('%(virtual_env)s/releases' % env):
            # Only rollback if we have previous releases
            if int(run('ls -1 | wc -l')) < 2:
                abort('There is no previous release to rollback to')

            # Get previous release
            output = run("ls . | sort -f | grep -v '^current$' $1")
            previous_release = output.split()[-1]

            # Move previous release to current
            run('rm -Rf current')
            run('mv %s current' % previous_release)

            # Tidy up (remove) old releases
            while int(run('ls -1 | wc -l')) >  RELEASE_COUNT:
                run('rm -Rf $(ls . | sort -f | head -n 1)')
            if update_requirements:
                run('pip install -r REQUIREMENTS')
            if migrate:
                run('django-admin.py migrate --all')
            if static:
                run('django-admin.py collectstatic')
            sudo('service apache2 graceful')


class Test(tasks.Task):
    """
    Run tests locally
    """
    name = 'test'

    def run(self):
        with cd(env.path):
            local('django-admin.py validate')
            local('django-admin.py test')


class CreateDatabase(BaseTask):
    """
    Create and populate remote database (with syncdb)
    """
    name = 'create_database'

    def run(self, run_migrations=False):
        remote_db_settings = settings.DATABASES['default']

        sudo('mysql -u%(USER)s -p%(PASSWORD)s -e '\
             '"CREATE DATABASE %(NAME)s"' % remote_db_settings)
        with prefix('workon %(domain)s' % env):
            migs = ' --migrate' if run_migrations else ''
            run('django-admin.py syncdb --noinput %s' % migs)


class SyncDatabase(BaseTask):
    """
    Sync local MYSQL database with remote database
    """
    name = 'sync_database'

    def run(self):
        self.remote_db_settings = settings.DATABASES['default']
        if not self.remote_db_settings['ENGINE'].endswith('mysql'):
            abort('Command only possible with MySQL databases')
        self.export_db()
        self.import_db()

    def export_db(self):
        # Export remote database
        run('mysqldump -u%(USER)s -p%(PASSWORD)s --databases %(NAME)s '\
            '> /tmp/%(NAME)s.sql' % self.remote_db_settings)
        local('scp %s@%s:/tmp/%s.sql /tmp/' % (
              env.user, env.hosts[0],
              self.remote_db_settings['NAME']))

    def import_db(self):
        # Import remote database to local
        local_settings = self.get_local_settings()
        local('mysql -p -h localhost %s < /tmp/%(NAME)s.sql' % (
              local_settings.DATABASES['default']['NAME'],\
              self.remote_db_settings['NAME']))


class VirtualenvPermission(tasks.Task):

    name = 'virtualenv_permission'

    def run(self):
        sudo('chmod 777 $WORKON_HOME/hook.log')


virtualenv_permission = VirtualenvPermission()
production = Production()
staging  = Staging()
bootstrap = Bootstrap()
deploy = Deploy()
rollback = Rollback()
test  = Test()
create_database = CreateDatabase()
sync_database = SyncDatabase()
