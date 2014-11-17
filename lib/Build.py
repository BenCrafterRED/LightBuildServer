#!/usr/bin/env python3
"""Light Build Server: build packages for various distributions, using linux containers"""

# Copyright (c) 2014 Timotheus Pokorra

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
# USA
#

from RemoteContainer import RemoteContainer
from BuildHelper import BuildHelper
from BuildHelperFactory import BuildHelperFactory
from time import gmtime, strftime
import yaml
import os
import shutil
from Shell import Shell
import logging

class Build:
  'run one specific build of one package'

  def __init__(self, LBS, logger):
    self.LBS = LBS
    self.logger = logger
    self.container = None
    self.finished = False
    self.buildmachine = None
    configfile="../config.yml"
    stream = open(configfile, 'r')
    self.config = yaml.load(stream)

  def createbuildmachine(self, lxcdistro, lxcrelease, lxcarch, buildmachine):
    # create a container on a remote machine
    self.buildmachine = buildmachine
    self.container = RemoteContainer(buildmachine, self.logger)
    return self.container.createmachine(lxcdistro, lxcrelease, lxcarch, buildmachine)

  def buildpackage(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch, buildmachine):
    userconfig = self.config['lbs']['Users'][username]
    self.logger.startTimer()
    self.logger.print(" * Starting at " + strftime("%Y-%m-%d %H:%M:%S GMT%z"))
    self.logger.print(" * Preparing the machine...")
    if self.createbuildmachine(lxcdistro, lxcrelease, lxcarch, buildmachine):

      try:
        # install a mount for the project repo
        self.container.installmount("/root/repo", "/var/www/repos/" + username + "/" + projectname + "/" + lxcdistro + "/" + lxcrelease)
        self.container.installmount("/root/tarball", "/var/www/tarballs/" + username + "/" + projectname)
      
        # prepare container, install packages that the build requires; this is specific to the distro
        self.buildHelper = BuildHelperFactory.GetBuildHelper(lxcdistro, self.container, "lbs-" + projectname + "-master", username, projectname, packagename)
        if not self.buildHelper.PrepareMachineBeforeStart():
          raise Exception("Problem with PrepareMachineBeforeStart")
        if self.container.startmachine():
          self.logger.print("container has been started successfully")
        if not self.buildHelper.PrepareMachineAfterStart():
          raise Exception("Problem with PrepareMachineAfterStart")
        if not self.buildHelper.PrepareForBuilding():
          raise Exception("Problem with PrepareForBuilding")

        # get the sources of the packaging instructions
        pathSrc=self.LBS.getPackagingInstructions(userconfig, username, projectname)
        # copy the repo to the container
        self.container.copytree(pathSrc+'lbs-'+projectname, "/root/lbs-"+projectname)

        if not self.buildHelper.InstallRequiredPackages(self.config['lbs']['LBSUrl']):
          raise Exception("Problem with InstallRequiredPackages")
        if not self.buildHelper.DownloadSources():
          raise Exception("Problem with DownloadSources")
        if not self.buildHelper.SetupEnvironment(branchname):
          raise Exception("Setup script did not succeed")
        # disable the network, so that only code from the tarball is being used
        if not self.buildHelper.DisableOutgoingNetwork():
          raise Exception("Problem with disabling the network")
        if not self.buildHelper.BuildPackage(self.config):
          raise Exception("Problem with building the package")
        if not self.container.rsyncHostGet("/var/www/repos/" + username + "/" + projectname + "/" + lxcdistro + "/" + lxcrelease):
          raise Exception("Problem with syncing repos")
        if not self.container.rsyncHostGet("/var/www/tarballs/" + username + "/" + projectname):
          raise Exception("Problem with syncing tarballs")
        # create repo file
        self.buildHelper.CreateRepoFile(self.config)
        self.logger.print("Success!")
      except Exception as e:
        # TODO: logging to log file does not work yet?
        logging.basicConfig(level=logging.DEBUG, filename='/var/log/lbs.log')
        logging.exception("Error happened...")
        self.logger.print("LBSERROR: "+str(e))
      finally:  
        self.LBS.ReleaseMachine(buildmachine)
    else:
      self.logger.print("LBSERROR: There is a problem with creating the container!")
      self.LBS.ReleaseMachine(buildmachine)
    self.finished = True
    logpath=self.logger.getLogPath(username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch)
    buildnumber=self.logger.store(self.config['lbs']['DeleteLogAfterDays'], self.config['lbs']['KeepMinimumLogs'], logpath)
    if self.logger.hasLBSERROR() or not self.config['lbs']['SendEmailOnSuccess'] == False:
      self.logger.email(self.config['lbs']['EmailFromAddress'], userconfig['EmailToAddress'], "LBS Result for " + projectname + "/" + packagename, self.config['lbs']['LBSUrl'] + "/logs/" + logpath + "/" + str(buildnumber))
    return self.logger.get()
