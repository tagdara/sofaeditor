#!/usr/bin/python3

import json
import asyncio
import aiohttp
from aiohttp import web
import ssl
import concurrent.futures
import aiofiles
import datetime
import os
import socket
import sys
from os.path import isfile, isdir, join

import logging
from logging.handlers import RotatingFileHandler

class sofaEditorServer():
    
    def initialize(self):
            
        try:
            self.serverApp = web.Application()
            self.serverApp.router.add_get('/', self.root_handler)
            self.serverApp.router.add_get('/dir', self.directory_handler)
            self.serverApp.router.add_post('/dir', self.directory_handler_post)
            self.serverApp.router.add_get('/dir/{path:.+}', self.directory_handler)

            self.serverApp.router.add_get('/file', self.file_handler)
            self.serverApp.router.add_get('/file/{path:.+}', self.file_handler)
            self.serverApp.router.add_post('/save/{path:.+}', self.save_handler_post)

            self.serverApp.router.add_get('/favorites', self.favorites_handler)

            self.serverApp.router.add_static('/', path=self.config['client'])

            self.runner = aiohttp.web.AppRunner(self.serverApp)
            self.loop.run_until_complete(self.runner.setup())

            ssl_cert = self.config['cert']
            ssl_key = self.config['key']
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(str(ssl_cert), str(ssl_key))

            self.site = web.TCPSite(self.runner, self.config['hostname'], self.config['port'], ssl_context=self.ssl_context)
            self.log.info('Starting editor webserver at https://%s:%s' % (self.config['hostname'], self.config['port']))
            self.loop.run_until_complete(self.site.start())
            return True
        except socket.gaierror:
            self.log.error('Error - DNS or network down during intialize.', exc_info=True)
            return False
        except:
            self.log.error('Error starting REST server', exc_info=True)
            return False


    def date_handler(self, obj):
        
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.info('Caused type error: %s' % obj)
            raise TypeError

    async def root_handler(self, request):
        self.log.info('<- %s session start' % (request.transport.get_extra_info('peername')[0]))
        return web.FileResponse(os.path.join(self.config['client'],"index.html"))

    async def save_handler_post(self, request):
        
        try:
            if request.body_exists:
                body=await request.read()
                body=body.decode()
            else:
                return web.Response(text='{"status":"failed", "reason":"No Content"}')
                
            if 'path' in request.match_info:
                path=request.match_info['path']
            else:
                return web.Response(text='{"status":"failed", "reason":"Bad Path"}')

            self.log.info('<- %s save: %s' % (request.transport.get_extra_info('peername')[0], path))
            result=await self.app.save_file(path, body)
            if result:
                return web.Response(text='{"status":"success"}')
            else:
                return web.Response(text='{"status":"failed", "reason":"Error with Save Handler"}')
                
        except:
            self.log.info('error handling save request', exc_info=True)
            return web.Response(text='{"status":"failed", "reason":"Error with Save Handler"}')

    async def directory_handler(self, request):
        
        try:
            path="/"
            if 'path' in request.match_info:
                path=request.match_info['path']
            dirlist=await self.app.get_directory(path)
            self.log.info('<- %s dir: %s' % (request.transport.get_extra_info('peername')[0], path))
            return web.Response(text=json.dumps(dirlist, default=self.date_handler))
        except:
            self.log.info('error handling directory request: %s' % path, exc_info=True)
            return web.Response(text='[]')

    async def directory_handler_post(self, request):
        
        try:
            path="/"
            if request.body_exists:
                body=await request.read()
                body=json.loads(body.decode())
                path=body['startdir']
            self.log.info('<- %s dir: %s' % (request.transport.get_extra_info('peername')[0], path))
            if path=='/favorites':
                dirlist=await get_favorites()
            else:
                dirlist=await self.app.get_directory(path)
            return web.Response(text=json.dumps(dirlist, default=self.date_handler))
        except:
            self.log.info('error handling directory request: %s' % path, exc_info=True)
            return web.Response(text='[]')

    async def get_favorites(self):

        try:
            async with aiofiles.open('/opt/sofa-editor/favorites.json', mode='r') as f:
                result = await f.read()
                favs=json.loads(result)
            return favs
        except:
            self.log.info('error getting favorites', exc_info=True)
            return []
        

    async def favorites_handler(self, request):
        
        try:
            favs=await self.get_favorites()
            return web.Response(text=json.dumps(favs, default=self.date_handler))
        except:
            self.log.info('error getting favorites', exc_info=True)
            return web.Response(text='[]')

        

    async def file_handler(self, request):
        
        try:
            path="/"
            if 'path' in request.match_info:
                path=request.match_info['path']
            self.log.info('<- %s file: %s' % (request.transport.get_extra_info('peername')[0], path))
            file_contents=await self.app.get_file(path)
            return web.Response(text=file_contents)

        except:
            self.log.info('error handling file request: %s' % path, exc_info=True)
            return web.Response(text='')

    def shutdown(self):
        self.loop.run_until_complete(self.serverApp.shutdown())


    def __init__(self, config, loop, log=None, app=None):
        self.config=config
        self.loop = loop
        self.log=log
        self.app=app
 
class sofaeditor(object):

    async def get_config(self, path):
        
        try:
            async with aiofiles.open(path, mode='r') as f:
                result = await f.read()
                config=json.loads(result)
                self.config=config
            return config

        except:
            self.log.error('An error occurred while getting config: %s' % path, exc_info=True)
            return {}


    async def get_file(self, path):
        
        try:
            filepath=os.path.join(self.config['path'], path)
            async with aiofiles.open(filepath, mode='r') as f:
                result = await f.read()

            return result
        except:
            self.log.error('An error occurred while getting directory: %s' % path, exc_info=True)
            return ''

    async def save_file(self, path, contents):
        
        try:
            filepath=os.path.join(self.config['path'], path)
            async with aiofiles.open(filepath, mode='w') as f:
                result = await f.write(contents)
            return result

        except:
            self.log.error('An error occurred while getting directory: %s' % path, exc_info=True)
            return False

    async def get_directory(self, path):
                
        try:
            all_list=[]
            filelist=[]
            dirlist=[]
            self.log.info(' path: %s / %s' % (self.config, path))
            dirpath=os.path.join(self.config['path'], path)
            
            for file in os.listdir(dirpath):
                if os.path.splitext(file)[1] in self.config['excluded']:
                    pass
                else:
                    fileinfo={'name': file, 'path': path}
                    if isfile(join(dirpath,file)):
                        fileinfo={'name': file, 'path': path, 'type':'file', 'icon':'description' }
                        filelist.append(fileinfo)
                    elif isdir(join(dirpath,file)):
                        fileinfo={'name': file, 'path': path, 'type':'folder', 'icon':'folder' }
                        dirlist.append(fileinfo)

                    all_list=sorted(dirlist, key = lambda k: k["name"])+sorted(filelist, key = lambda k: k["name"])
            
            return all_list
                        
        except:
            self.log.error('An error occurred while getting directory: %s' % path, exc_info=True)
            return []

    def logsetup(self, logbasepath, logname, level="INFO", errorOnly=[]):

        #log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s','%m/%d %H:%M:%S')
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)
        #check if a log file already exists and if so rotate it

        needRoll = os.path.isfile(logfile)
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if needRoll:
            log_handler.doRollover()
            
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(logging.INFO)
        
        logging.getLogger(logname).addHandler(console)

        self.log =  logging.getLogger(logname)
        self.log.setLevel(logging.INFO)
        self.log.addHandler(log_handler)
        if not os.path.exists(loglink):
            os.symlink(logfile, loglink)
        
        self.log.info('-- -----------------------------------------------')

    def __init__(self):
        self.error_state=False
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.get_config('./config.json'))
        self.logsetup(self.config["log_directory"], 'editor')

    def start(self):
        try:
            self.log.info('.. Starting editor server')
            asyncio.set_event_loop(self.loop)
            self.server = sofaEditorServer(config=self.config, loop=self.loop, log=self.log, app=self)
            result=self.server.initialize()
            if result:
                self.loop.run_forever()
            else:
                self.error_state=True
        except KeyboardInterrupt:  # pragma: no cover
            pass
        except:
            self.log.error('Loop terminated', exc_info=True)
        finally:
            self.server.shutdown()
        
        self.log.info('.. stopping sofa editor')
        self.loop.close()
        if self.error_state:
            sys.exit(1)


if __name__ == '__main__':
    editor=sofaeditor()
    editor.start()
 
    
