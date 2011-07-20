from fabric.api import local, run, sudo, prefix, cd, env
from fabric.contrib import django
from fabric import tasks
from fabric.utils import abort
from django.conf import settings

env.path = local('pwd')
env.repo = 'eusalive'


class MyTask(tasks.Task):

    def get_local_settings(self):
        django.settings_module('settings.development')
        return settings

    def production(self):
        env.name = 'production'
        env.user = 'cahoona'
        env.hosts = ['92.63.136.213']
        env.password = 'v-Fj9P@8'
        env.domain = 'eusalive.co.uk'
        env.virtual_env = '$WORKON_HOME/%(domain)s' % env
        django.settings_module('settings.%(name)s' % env)

    def staging(self):
        env.name = 'staging'
        env.user = 'cahoona'
        env.hosts = ['92.63.136.213']
        env.password = 'v-Fj9P@8'
        env.domain = 'example.com'
        env.virtual_env = '$WORKON_HOME/%(domain)s' % env
        django.settings_module('settings.%(name)s' % env)


class Deploy(MyTask):
    """
    Deploy to remote server and run migrations if run_migrations == True
    """
    name = 'deploy'
    def run(self, run_migrations=False, update_requirements=True):
        self.test_local()
        self.git_pull()
        if update_requirements:
            self.update_requirements()

    def git_pull():
        with cd(env.virtual_env):
            run('git pull')

    def test_local():
        with cd(env.path):
            with prefix('source ../bin/activate'):
                local('django-admin.py test')

    def update_requirements():
        with prefix('workon %(domain)s' % env) and\
                                        cd('%(virtual_env)s/project' % env):
            run('pip install -r %(virtual_env)s/REQUIREMENTS' % env)

deploy = Deploy()


class PrepareEnvironment(MyTask):
    """
    Prepare a virtualenv with apache2 and nginx config files

    You must provide an enviroment (staging or production)
        for this to work
    """
    name = 'prepare_environment'

    def run(self):
        if not confirm('This will create a new virtualenv. Are you sure?'):
            abort('Task aborted')
        if not env.name:
            abort('You must specify an environment to deploy to\n\n'\
                  'e.g. fab production prepare_environment')
        self.env = environment
        self.create_virtualenv()
        self.clone_git_repo()
        self.setup_server()

    def create_virtualenv(self):
        # Create virtualenv
        run('mkvirtualenv %(domain)s' % env)

    def clone_git_repo(self):
        # Checkout git repo from cahoona VM-3
        with cd('%(virtual_env)s/project' % env):
            run('git clone git@92.63.136.209:%(repo)s.git project' % env)

    def setup_server(self):
        # Move config files into correct places
        with cd('%(virtual_env)s/project/conf' % env):
            # Replace placeholders in generic config files
            sudo("find . -type f -name '%(name)s*' -exec "\
                 "sed -i 's/<DOMAIN_NAME>/%(domain)s/g' '{}' ';'" % env)
            # Apache
            sudo('cp %(name)s.apache '\
                 '/etc/apache2/sites-available/%(domain)s' % env)
            sudo('service apache2 graceful')
            # nginx
            sudo('cp %(name)s.nginx '\
                 '/etc/nginx/sites-available/%(domain)s' % env)
            sudo('service nginx restart')

prepare_environment = PrepareEnvironment()


class CreateDatabase(MyTask):
    """
    Create and populate remote database (with syncdb)

    Migrations will be run if run_migrations == True
    """
    name = 'create_database'

    def run(self, run_migrations=False):
        remote_db_settings = settings.DATABASES['default']

        sudo('mysql -u%(USER)s -p%(PASSWORD)s -e "CREATE DATABASE %(NAME)s"' %\
             remote_db_settings)
        with prefix('workon %(domain)s' % env):
            migs = ' --migrate' if run_migrations else ''
            run('django-admin.py syncdb --noinput %s' % migs)

create_database = CreateDatabase()


class SyncDatabase(MyTask):
    """
    Sync local MYSQL database with remote database

    You must provide an enviroment (staging or production)
        for this to work
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

sync_database = SyncDatabase()
