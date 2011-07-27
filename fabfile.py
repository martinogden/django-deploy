from fabric.api import local, run, sudo, prefix, cd, env
from fabric.contrib import django
from fabric.contrib.console import confirm
from fabric import tasks
from fabric.utils import abort
from django.conf import settings

env.path = local('pwd')
env.repo = 'minge-net'
env.settings = 'production'


print settings.ENVIRONMENT_SETTINGS[env.settings]


class MyTask(tasks.Task):

    def get_local_settings(self):
        django.settings_module('settings.development')
        return settings

    def production(self):
        env.name = 'production'
        env.user = 'cahoona'
        env.hosts = ['92.63.136.213']
        env.password = 'v-Fj9P@8'
        env.domain = 'minge.net'
        env.virtual_env = '$WORKON_HOME/%(domain)s' % env
        django.settings_module('settings.%(name)s' % env)

    def staging(self):
        env.name = 'staging'
        env.user = 'cahoona'
        env.hosts = ['92.63.136.213']
        env.password = 'v-Fj9P@8'
        env.domain = 'staging.minge.net'
        env.virtual_env = '$WORKON_HOME/%(domain)s' % env
        django.settings_module('settings.%(name)s' % env)


task = MyTask()
task.__getattribute__(env.settings)()


class Deploy(MyTask):
    """
    Deploy to remote server and run migrations if run_migrations == True
    """
    name = 'deploy'

    def run(self, run_migrations=True, update_requirements=True,\
            run_tests=False):
        """
        @todo
        """
        # Run tests
        if run_tests:
            self.test_local()
        # Perform bulk of work
        self.git_pull()
        if update_requirements:
            self.update_requirements()
        if run_migrations:
            self.run_migrations()
        self.restart_apache()

    def git_pull(self):
        with cd('%(virtual_env)s/project' % env):
            run('git pull')

    def test_local(self):
        with cd(env.path):
            with prefix('source ../bin/activate'):
                local('django-admin.py test')

    def update_requirements(self):
        with cd('%(virtual_env)s/project' % env):
            with prefix('workon %(domain)s' % env):
                run('pip install -r %(virtual_env)s/project/REQUIREMENTS'\
                    % env)

    def run_migrations(self):
        with cd('%(virtual_env)s/project' % env):
            with prefix('workon %(domain)s' % env):
                run('django-admin.py syncdb --noinput --migrate')

    def restart_apache(self):
        sudo('service apache2 graceful')


deploy = Deploy()


class PrepareLocal(MyTask):
    """
    @todo
    """
    name = 'prepare_local'

    def run(self):
        self.ungit_directory()

    def ungit_directory(self):
        """
        Remove .git directory from project
        """
        with cd('$WORKON_HOME/%(domain)s/project' % env):
            local('rm -rf .git')


prepare_local = PrepareLocal()


class PrepareEnvironment(MyTask):
    """
    Prepare a virtualenv with apache2 and nginx config files

    You must provide an enviroment (staging or production)
        for this to work
    """
    name = 'prepare_environment'

    def run(self):
        # On your local machine
        # local('mkvirtualenv')
        # Clone skeleton
        # Remove .git directory
        # On the server
        if not confirm('This will create a new virtualenv on your local\n'\
            'machine as well as on the server. Are you sure?'):
            abort('Task aborted')
        # if not env.name:
        #     abort('You must specify an environment to deploy to\n'\
        #           'e.g. fab production prepare_environment')
        # @todo what was the next line about?
        # self.env = environment
        self.create_remote_virtualenv()
        self.setup_local_repo()
        self.append_activate()
        deploy = Deploy()
        deploy.run(run_migrations=True, update_requirements=True)
        self.setup_server()

    def create_local_virtualenv(self):
        # Create local virtualenv
        run('mkvirtualenv %(domain)s' % env)

    def create_remote_virtualenv(self):
        # Create remote virtualenv
        with cd('/home/cahoona/.virtualenvs'):
            sudo('chown cahoona:cahoona hook*')
            sudo('chown cahoona:cahoona hosudo')
        run('mkvirtualenv %(domain)s' % env)

    def setup_local_repo(self):
        with cd('$WORKON_HOME/%(domain)s/project' % env):
            local('git init')
            local('git add .')
            local('git commit -m "Fabfile: Initial auto-commit"')
            local('git remote add origin git@cahoona.co.uk:%(repo)s.git' % env)
            local('git push origin master')

    def clone_git_repo(self):
        # Checkout git repo from cahoona VM-3
        with cd('%(virtual_env)s' % env):
            run('git clone git@92.63.136.209:%(repo)s.git project' % env)

    def append_activate(self):
        with cd('%(virtual_env)s/project' % env):
            run('export DJANGO_SETTINGS_MODULE=settings.%(name)s' % env)
            run('echo "export DJANGO_SETTINGS_MODULE=settings.%(name)s" >> ../bin/activate' % env)
            run('export PYTHONPATH=$PYTHONPATH:$PWD')
            run('echo "export PYTHONPATH=$PYTHONPATH:$PWD" >> ../bin/activate')

    def update_requirements(self):
        with cd('%(virtual_env)s/project' % env):
            with prefix('workon %(domain)s' % env):
                run('pip install -r %(virtual_env)s/project/REQUIREMENTS'\
                    % env)

    def setup_server(self):
        # Move config files into correct places
        with cd('%(virtual_env)s/project/conf' % env):
            # Replace placeholders in generic config files
            sudo("find . -type f -name '%(name)s*' -exec "\
                 "sed -i 's/<DOMAIN_NAME>/%(domain)s/g' '{}' ';'" % env)
            # Apache
            sudo('cp %(name)s.apache '\
                 '/etc/apache2/sites-available/%(domain)s' % env)
            sudo('a2ensite %(domain)s' % env)
            sudo('service apache2 graceful')
            # nginx
            sudo('cp %(name)s.nginx '\
                 '/etc/nginx/sites-available/%(domain)s' % env)
            try:
                sudo('ln -s /etc/nginx/sites-available/%s /etc/nginx/sites-enabled/%s' % (env.domain, env.domain, ))
            except:
                print 'Site already available'
            sudo('service nginx restart')

prepare_environment = PrepareEnvironment()


class CreateDatabase(MyTask):
    """
    Create and populate remote database (with syncdb)

    Migrations will be run if run_migrations == True
    """
    name = 'create_database'

    def run(self, run_migrations=False):
        with prefix('workon %(domain)s' % env):
            remote_db_settings = settings.DATABASES['default']
            sudo('mysql -u%(USER)s -p%(PASSWORD)s -e "CREATE DATABASE %(NAME)s;"' %\
                 remote_db_settings)
            #run('workon %(domain)s' % env)
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
