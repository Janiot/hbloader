import asyncio
import docker
import json
from docker.types import LogConfig
import tarfile
from pathlib import Path
import subprocess
import re
from aiohttp.client_exceptions import ClientOSError, ClientResponseError
from datetime import datetime, timedelta

from .ddi.client import DDIClient, APIError
from .ddi.client import (ConfigStatusExecution, ConfigStatusResult)
from .ddi.deployment_base import (
    DeploymentStatusExecution, DeploymentStatusResult)
from .ddi.cancel_action import (
    CancelStatusExecution, CancelStatusResult)
from .mi.client import MIClient
import logging


class HBClient(object):
    """
    HawkBit downloader
    """

    def __init__(self,
                 session,
                 result_callback,
                 step_callback=None,
                 lock_keeper=None,
                 **kwargs):

        super(HBClient, self).__init__()

        self.logger = logging.getLogger('hbloader')
        self.session = session

        self.docker_client = None

        self.config = kwargs

        self.logger.info(self.config)

        self.run_mode = kwargs['run_as_service']
        self.docker_mode = True
        self.attributes = kwargs['attributes']

        self.action_id = None
        self.lock_keeper = lock_keeper

        self.result_callback = result_callback
        self.step_callback = step_callback

        self.dl_dir = Path.joinpath(Path.home(), 'BUNDLE')
        Path(self.dl_dir).mkdir(parents=True, exist_ok=True)

        self.dl_filename = ''
        self.service_dir = Path.joinpath(Path.home(), '.config/systemd/user')
        Path(self.service_dir).mkdir(parents=True, exist_ok=True)
        self.auth_token = ''
        self.controller_id = kwargs['controller_id']
        self.mi = MIClient(session, **kwargs)
        self.ddi = None

    async def run_ddi(self):
        '''
        Register target on server using MI
        and switch to DDI with received parmeters
        '''
        self.logger.info('')

        ''' loop until target will be registred on server'''
        while True:
            target = await self.get_target_details()
            if target:
                break
            await self.mi.register_target()

        self.logger.debug('name: \n {}'.format(target['name']))
        self.logger.debug('controller_id: \n {}'.format(target['controllerId']))
        self.logger.debug('securityTocken: \n {}'.format(target['securityToken']))

        '''
        get generated on server auth tocken,
        add it to config dictionary
        and run DDI with full set of params
        '''
        self.config['auth_token'] = target['securityToken']
        self.logger.debug('{}'.format(self.config))
        self.ddi = DDIClient(self.session, **self.config)

    async def get_target_details(self):
        '''
        If target exists return details (dict)
        If not return None
        '''
        self.logger.info('')

        targets = await self.mi()
        content = targets['content']
        self.logger.info(content)
        if content:
            for item in content:
                self.logger.info("content item: {}".format(item))
                if item['controllerId'] == self.controller_id:
                    return item
        self.logger.info('no content')     
        return None

    async def start_polling(self, wait_on_error=60):
        """
        Wrapper around self.poll_base_resource() for exception handling.
        """
        self.logger.info('')

        INFO_POLLING = 'Polling cancelled'
        WARN_TIMEOUT = 'Polling failed due to TimeoutError'
        WARN_TEMP_ERROR = 'Polling failed with a temporary error:'
        WARN_EXCEPTION = 'Polling failed with an unexpected exception:'
        INFO_RETRY_FMT = 'Retry will happen in {} seconds'

        while True:
            try:
                await self.poll_base_resource()
            except asyncio.CancelledError:
                self.logger.info(INFO_POLLING)
                break

            except asyncio.TimeoutError:
                self.logger.warning(WARN_TIMEOUT)

            except (APIError,
                    TimeoutError,
                    ClientOSError,
                    ClientResponseError) as e:
                # log error and start all over again
                self.logger.warning('{} {}'.format(WARN_TEMP_ERROR, e))

            except Exception:
                self.logger.exception(WARN_EXCEPTION)

            self.action_id = None
            self.logger.info(INFO_RETRY_FMT.format(wait_on_error))

            await asyncio.sleep(wait_on_error)

    async def poll_base_resource(self):
        """
        Poll DDI API base resource.
        """
        while True:

            base = await self.ddi()
            if '_links' in base:

                if 'configData' in base['_links']:
                    await self.identify(base)

                if 'deploymentBase' in base['_links']:
                    await self.process_deployment(base)

                if 'cancelAction' in base['_links']:
                    await self.cancel(base)

            await self.sleep(base)

    async def identify(self, base):
        """
        Identify target against HawkBit.
        """
        self.logger.info('> identify')

        await self.ddi.configData(
                ConfigStatusExecution.closed,
                ConfigStatusResult.success, **self.attributes)

    async def process_deployment(self, base):
        """
        Check and download deployments
        """
        self.logger.info('> process_deployment')

        if self.action_id is not None:
            self.logger.info('Deployment is already in progress')
            return

        # retrieve action id and resource parameter from URL
        deployment = base['_links']['deploymentBase']['href']
        self.logger.info('deploymentBase: {}'.format(deployment))
        match = re.search('/deploymentBase/(.+)\?c=(.+)$', deployment)
        action_id, resource = match.groups()
        self.logger.debug('action_id: {}'.format(action_id))
        self.logger.debug('resource: {}'.format(resource))
        self.logger.info('Deployment found for this target')
        # fetch deployment information
        deploy_info = await self.ddi.deploymentBase[action_id](resource)
        try:
            chunk = deploy_info['deployment']['chunks'][0]
        except IndexError:
            # send negative feedback to HawkBit
            status_execution = DeploymentStatusExecution.closed
            status_result = DeploymentStatusResult.failure
            msg = 'Deployment without chunks found. Ignoring'
            await self.ddi.deploymentBase[action_id].feedback(
                    status_execution, status_result, [msg])
            raise APIError(msg)

        try:
            artifact = chunk['artifacts'][0]

        except IndexError:
            # send negative feedback to HawkBit
            status_execution = DeploymentStatusExecution.closed
            status_result = DeploymentStatusResult.failure
            msg = 'Deployment without artifacts found. Ignoring'

        # prefer https ('download') over http ('download-http')
        # HawkBit provides either only https, only http or both
        if 'download' in artifact['_links']:
            download_url = artifact['_links']['download']['href']

        else:
            download_url = artifact['_links']['download-http']['href']

        # download artifact, check md5 and report feedback
        md5_hash = artifact['hashes']['md5']
        self.logger.info('Starting bundle download')
        await self.download_artifact(action_id, download_url, md5_hash)

        # download successful, start install
        self.logger.info('Starting installation')
        try:
            self.action_id = action_id
            await asyncio.shield(self.install())
        except Exception as e:
            # send negative feedback to HawkBit
            status_execution = DeploymentStatusExecution.closed
            status_result = DeploymentStatusResult.failure
            await self.ddi.deploymentBase[action_id].feedback(
                    status_execution, status_result, [str(e)])
            raise APIError(str(e))

    async def install(self):
        
        self.logger.info('{} {}'.format(self.dl_dir, self.dl_filename))
        manifest_file_name = Path(self.dl_dir).joinpath(self.dl_filename)
        manifest = {}

        with open(manifest_file_name, "r") as manifest_file:
            manifest = json.load(manifest_file) 

        uri = manifest["imageUri"]
        options = manifest["containerCreateOptions"]
        port_bindings = options ["HostConfig"]["PortBindings"]
        
        for port_int, port_list in port_bindings.items(): 
            port_ext = port_list[0]["HostPort"]

        print(port_ext)
        print(port_int)
        print(uri)
        
        ports = {port_int : port_ext}
        print (ports)
        
        self.docker_client = docker.from_env()
        client = docker.from_env()
        
        print("pulling image")
        self.docker_client.images.pull(uri)
        print("pull done")

        self.logger.info("Image load finished.")
        #self.logger.info("Images available:\n{}".format(images))

        await self.process_image(uri, ports)


    async def install_old(self):

        self.logger.info('{} {}'.format(self.dl_dir, self.dl_filename))

        artifact_type = self.identify_artifact()
        self.logger.info('artifact type {}'.format(artifact_type))

        dl_location = Path(self.dl_dir).joinpath(self.dl_filename)

        if artifact_type == 'python':
            commands = [['pip3', 'install', self.dl_filename], ]
            for command in commands:
                self.logger.info(command)
                process = subprocess.run(command, cwd=self.dl_dir.as_posix())
                rc = process.returncode

                await self.run_as_service()

        if artifact_type == 'docker':
            self.docker_client = docker.from_env()

            with open(dl_location, 'rb') as image:
                images = self.docker_client.images.load(image)
            
            rc = 0
            self.logger.info("Image load finished.")
            self.logger.info("Images available:\n{}".format(images))

            last_image = images[0]

            await self.process_image(last_image)

        if self.lock_keeper:
            self.lock_keeper.unlock(self)

        self.logger.info("Install complete {}".format(rc))

        if rc == 0:
            status_execution = DeploymentStatusExecution.closed
            status_result = DeploymentStatusResult.success

        else:
            status_execution = DeploymentStatusExecution.closed
            status_result = DeploymentStatusResult.failure

        await self.ddi.deploymentBase[self.action_id].feedback(
                status_execution, status_result, ['Install completed'])

        self.logger.info("Install complete fb {}".format(rc))

        self.action_id = None
        self.result_callback(result)

    async def uninstall(self):
        pass


    def ask_yn(self):
        '''
        Ask yes or  no
        '''
        while True:
            yn = input('(Y/n)')

            if yn in ('n', 'N'):
                return True

            if yn in ('y', 'Y', ''):
                return False

            print('Wrong input')

    async def process_image(self, image, ports):
        '''
        Make descision about image usage
        and run container if yes.
        '''
        self.logger.info('')
        if self.docker_mode == 'no':
            print("no start container")
            return

        print("start container")
        log_params = {'max-size': '10m', 'max-file': '3'}
        log_config = LogConfig(type=LogConfig.types.JSON, config=log_params)
        container = self.docker_client.containers.run(image,
                                        detach=True,
                                        log_config=log_config, 
                                        ports=ports)

        self.logger.info('container {} {} {}'.format(container.short_id,
                                                     container.name,
                                                     container.status))
                                                     
                                                     
        status_execution = DeploymentStatusExecution.closed
        status_result = DeploymentStatusResult.success
                                                     
        await self.ddi.deploymentBase[self.action_id].feedback(
                status_execution, status_result, ['Install completed'])

    async def run_as_service(self):
        '''
        If it enabled by configuration
        create service file and pass  it to systemd.
        '''

        self.logger.info('> run_as_service {} {}'.format(self.run_mode, self.dl_filename))

        '''
        choose operating mode
        '''
        if self.run_mode == 'no':
            return

        if self.run_mode == 'ask':
            print("Run installed as service ?")
            if not self.ask_yn():
                return
        '''
        create service file, put it to systemd
        '''
        app_name =  self.dl_filename.split('-')[0]
        service_file_name = app_name + '.service'
        exec_file_name = app_name + '.py'

        self.logger.debug("Names: {} {} {}".format(app_name, service_file_name, exec_file_name))

        self.create_service_file(service_file_name, exec_file_name)

        self.logger.debug('service_dir {}'.format(self.service_dir))

        commands = [['pwd'],
                    ['ls', '-la'],
                    ['cp', service_file_name, self.service_dir],
                    ['systemctl', '--user', 'daemon-reload'],
                    ['systemctl', '--user', 'enable', service_file_name],
                    ['systemctl', '--user', 'start', service_file_name],
                    ['systemctl', '--user', 'status', service_file_name]]

        for command in commands:
            self.logger.info(command)
            process = subprocess.run(command, cwd=self.dl_dir)
            rc = process.returncode

    async def download_artifact(self, action_id, url, md5sum,
                                tries=3):
        """
        Download bundle artifact.
        """
        self.logger.info('')

        ERR_CHECKSUMM_FMT = 'Checksum does not match. {} tries remaining'
        STATUS_MSG_FMT = 'Artifact checksum does not match after {} tries.'

        try:
            match = re.search('/softwaremodules/(.+)/artifacts/(.+)$', url)
            software_module, self.dl_filename = match.groups()
            static_api_url = False

        except AttributeError:
            static_api_url = True

        if self.step_callback:
            self.step_callback(0, "Downloading bundle...")
        
        self.dl_filename = 'manifest.json'

        self.logger.debug('dl_filename: {}'.format(self.dl_filename))
        self.logger.debug('dl_dir: {}'.format(self.dl_dir))

        dl_location = Path(self.dl_dir).joinpath(self.dl_filename)

        # try several times
        for dl_try in range(tries):

            if not static_api_url:
                checksum = await self.ddi.softwaremodules[software_module].artifacts[self.dl_filename](dl_location)

            else:
                # API implementations might return static URLs, so bypass API
                # methods and download bundle anyway
                checksum = await self.ddi.get_binary(url, dl_location)

            if checksum == md5sum:
                self.logger.info('Download successful')
                return

            else:
                self.logger.error(ERR_CHECKSUMM.format(tries-dl_try))

        # MD5 comparison unsuccessful, send negative feedback to HawkBit
        status_msg = STATUS_MSG_FMT.format(tries)
        status_execution = DeploymentStatusExecution.closed
        status_result = DeploymentStatusResult.failure

        self.logger.info('Feedback failure')
        await self.ddi.deploymentBase[action_id].feedback(
                status_execution, status_result, [status_msg])

        raise APIError(status_msg)

    def identify_artifact(self):
        '''
        Get archive's file list and determines type of content.
        '''
        self.logger.info('')

        dl_location = Path(self.dl_dir).joinpath(self.dl_filename)

        with tarfile.open(dl_location,'r') as tar:
            names = tar.getnames()

        items = [Path(name).name for name in names]

        if 'manifest.json' in items:
            result = 'docker'

        if 'setup.py' in items:
            result = 'python'

        self.logger.debug("{} is a |{}|".format(self.dl_filename, result))
        return result

    async def sleep(self, base):
        """
        Sleep time suggested by HawkBit.
        """
        self.logger.info('')
        sleep_str = base['config']['polling']['sleep']
        self.logger.info('Will sleep for {}'.format(sleep_str))
        t = datetime.strptime(sleep_str, '%H:%M:%S')
        delta = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        # await asyncio.sleep(delta.total_seconds())
        await asyncio.sleep(30)

    def create_service_file(self,
                            service_file_name,
                            exec_name,
                            description='hbloader test service'):
        '''
        Create .service file for installed programm.

        '''
        self.logger.info('> create_service_file {}'.format(self.run_mode))

        result = subprocess.run(['whereis', exec_name],  stdout=subprocess.PIPE)
        full_exec_name = result.stdout.split()[1].decode('utf-8')
        str = '''[Unit]
Description={}

[Service]
ExecStart=/usr/bin/python3 {}

[Install]
WantedBy=multi-user.target
'''.format(description, full_exec_name)
        p = Path.joinpath(self.dl_dir, service_file_name)
        with p.open( 'w') as service_file:
            service_file.write(str)
