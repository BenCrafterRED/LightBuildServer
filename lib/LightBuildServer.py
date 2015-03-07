#!/usr/bin/env python3
"""Light Build Server: build packages for various distributions, using linux containers"""

# Copyright (c) 2014-2015 Timotheus Pokorra

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
from Logger import Logger
from Build import Build
from time import gmtime, strftime
import yaml
import os
import shutil
import time
import datetime
from Shell import Shell
import logging
from threading import Thread
from collections import deque

class LightBuildServer:
  'light build server based on lxc and git'

  def __init__(self):
    configfile="../config.yml"
    stream = open(configfile, 'r')
    self.config = yaml.load(stream)

    self.machines = {}
    for buildmachine in self.config['lbs']['Machines']:
      # init the machine
      self.machines[buildmachine] = { }
      self.machines[buildmachine]['status'] = 'available'

    self.lbsList = {}
    self.recentlyFinishedLbsList = {}
    self.buildqueue = deque()
    self.ToBuild = deque()
    self.finishedqueue = deque()
    thread = Thread(target = self.buildqueuethread, args=())
    thread.start()

  def GetLbsName(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch):
    return username+"/"+projectname+"/"+packagename+"/"+branchname+"/"+lxcdistro+"/"+lxcrelease+"/"+lxcarch

  def GetAvailableBuildMachine(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch):
    buildjob=username+"/"+projectname+"/"+packagename+"/"+branchname+"/"+lxcdistro+"/"+lxcrelease+"/"+lxcarch
    queue=username+"/"+projectname+"/"+branchname+"/"+lxcdistro+"/"+lxcrelease+"/"+lxcarch
    machineToUse=None
    machinePriorityToUse=101
    for buildmachine in self.config['lbs']['Machines']:
      if self.machines[buildmachine]['status'] == 'available':
        buildmachinePriority=100
        if 'priority' in self.config['lbs']['Machines'][buildmachine]:
          buildmachinePriority=self.config['lbs']['Machines'][buildmachine]['priority']
        if buildmachinePriority < machinePriorityToUse:
          machinePriorityToUse = buildmachinePriority
          machineToUse = buildmachine
    if machineToUse is not None:
      self.machines[machineToUse]['status'] = 'building'
      self.machines[machineToUse]['buildjob'] = buildjob
      self.machines[machineToUse]['queue'] = queue
      self.machines[machineToUse]['username'] = username
      self.machines[machineToUse]['projectname'] = projectname
      self.machines[machineToUse]['packagename'] = packagename
      return machineToUse
    return None

  def CheckForHangingBuild(self):
      # check for hanging build (BuildingTimeout in config.yml)
      for lbsName in self.lbsList:
        lbs = self.lbsList[lbsName]
        if (lbs.logger.lastTimeUpdate + self.config['lbs']['BuildingTimeout'] < int(time.time())):
          self.ReleaseMachine(lbs.buildmachine)

  def ReleaseMachine(self, buildmachine):
    RemoteContainer(buildmachine, self.config['lbs']['Machines'][buildmachine], Logger()).stop()
    self.machines[buildmachine]['status'] = 'available'

  def GetBuildMachineState(self, buildmachine):
    if self.machines[buildmachine]['status'] == 'building':
      return ("building", self.machines[buildmachine]['buildjob'])
    if self.machines[buildmachine]['status'] == 'available':
      return "available"
    return "undefined"

  def CanFindMachineBuildingOnSameQueue(self, username, projectname, branchname, lxcdistro, lxcrelease, lxcarch):
    queue=username+"/"+projectname+"/"+branchname+"/"+lxcdistro+"/"+lxcrelease+"/"+lxcarch
    for buildmachine in self.config['lbs']['Machines']:
      if self.machines[buildmachine]['status'] == 'building':
        if self.machines[buildmachine]['queue'] == queue:
          # there is a machine building a package on the same queue (same user, project, branch, distro, release, arch)
          return True
    return False

  def CanFindMachineBuildingProject(self, username, projectname):
    for buildmachine in self.config['lbs']['Machines']:
      if self.machines[buildmachine]['status'] == 'building':
        if self.machines[buildmachine]['username'] == username and self.machines[buildmachine]['projectname'] == projectname:
          # there is a machine building a package of the specified project
          return True
    return False

  def getPackagingInstructions(self, userconfig, username, projectname):
    lbsproject=userconfig['GitURL'] + 'lbs-' + projectname
    pathSrc="/var/lib/lbs/src/"+username+"/"
    os.makedirs(pathSrc, exist_ok=True)
    if os.path.isdir(pathSrc+'lbs-'+projectname):
        #we want a clean clone
        shutil.rmtree(pathSrc+'lbs-'+projectname)
    shell = Shell(Logger())
    if not 'GitType' in userconfig or userconfig['GitType'] == 'github':
      url=lbsproject + "/archive/master.tar.gz"
      cmd="cd " + pathSrc + ";";
      cmd+="curl --retry 10 --retry-delay 30 -f -L -o master.tar.gz \"" + url + "\";"
      cmd+="tar xzf master.tar.gz; mv lbs-" + projectname + "-master lbs-" + projectname
      shell.executeshell(cmd)
    elif userconfig['GitType'] == 'gitlab':
      url=lbsproject + "/repository/archive.tar.gz?ref=master"
      tokenfilename=self.config["lbs"]["SSHContainerPath"] + "/" + username + "/" + projectname + "/gitlab_token"
      if os.path.isfile(tokenfilename):
        with open (tokenfilename, "r") as myfile:
          url+="&private_token="+myfile.read().strip()
      cmd="cd " + pathSrc + ";";
      cmd+="curl --retry 10 --retry-delay 30 -f -o source.tar.gz \"" + url + "\";"
      cmd+="tar xzf source.tar.gz; mv lbs-" + projectname + ".git lbs-" + projectname
      shell.executeshell(cmd)
    if not os.path.isdir(pathSrc+'lbs-'+projectname):
      raise Exception("Problem with cloning the git repo")
    return pathSrc

  def CalculatePackageOrder(self, username, projectname, lxcdistro, lxcrelease, lxcarch):
    userconfig = self.config['lbs']['Users'][username]

    # get the sources of the packaging instructions
    self.getPackagingInstructions(userconfig, username, projectname)

    buildHelper = BuildHelperFactory.GetBuildHelper(lxcdistro, None, None, username, projectname, None)
    return buildHelper.CalculatePackageOrder(self.config, lxcdistro, lxcrelease, lxcarch)

  def AddToBuildQueue(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch):
    # find if this project depends on other projects
    DependsOnOtherProjects={}
    if 'DependsOn' in self.config['lbs']['Users'][username]['Projects'][projectname]:
      DependsOnOtherProjects=self.config['lbs']['Users'][username]['Projects'][projectname]['DependsOn']
    self.buildqueue.append((username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch, DependsOnOtherProjects))

  def BuildProject(self, username, projectname, lxcdistro, lxcrelease, lxcarch):
    packages=self.CalculatePackageOrder(username, projectname, lxcdistro, lxcrelease, lxcarch)

    if packages is None:
      message="Error: circular dependancy!"
    else:
      message=""
      branchname="master"
      for packagename in packages:
        # add package to build queue
        message += packagename + ", "
        lbsName=self.GetLbsName(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
        if lbsName in self.recentlyFinishedLbsList:
          del self.recentlyFinishedLbsList[lbsName]
        if not lbsName in self.lbsList:
          self.ToBuild.append(lbsName)
          self.AddToBuildQueue(username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch)

    return message

  def BuildProjectWithBranch(self, username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch):
    lbsName=self.GetLbsName(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
    if lbsName in self.recentlyFinishedLbsList:
      del self.recentlyFinishedLbsList[lbsName]
    if not lbsName in self.lbsList:
       self.ToBuild.append(lbsName)
       self.AddToBuildQueue(username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch)

  def BuildProjectWithBranchAndPwd(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch, auth_username, password):
    lbsName=self.GetLbsName(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
    if not lbsName in self.lbsList:
      self.ToBuild.append(lbsName)
      self.AddToBuildQueue(username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch)
      return "Build for {{lbsName}} has been triggered."
    else:
      return "{{lbsName}} is already in the build queue."

  def WaitForBuildJobFinish(self, thread, lbsName):
      thread.join()
      self.recentlyFinishedLbsList[lbsName] = self.lbsList[lbsName]
      listLbsName=lbsName.split('/')
      listLbsName.append(Logger().getLastBuild(listLbsName[0], listLbsName[1], listLbsName[2], listLbsName[3], listLbsName[4]+"/"+listLbsName[5]+"/"+listLbsName[6]))
      listLbsName.append(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
      self.finishedqueue.appendleft(listLbsName)
      if len(self.finishedqueue) > self.config['lbs']['ShowNumberOfFinishedJobs']:
        self.finishedqueue.pop()
      del self.lbsList[lbsName]

  def attemptToFindBuildMachine(self, item, FirstItemInQueue):
    username = item[0]
    projectname = item[1]
    packagename = item[2]
    branchname = item[3]
    lxcdistro = item[4]
    lxcrelease = item[5]
    lxcarch = item[6]
    DependsOnOtherProjects = item[7]

    if not FirstItemInQueue:
      # 1: check if there is a package building or waiting from the same user and buildtarget => return False
      if self.CanFindMachineBuildingOnSameQueue(username,projectname,branchname,lxcdistro,lxcrelease,lxcarch):
        return False
      
      # 2: check if any project that this package depends on is still building or waiting => return False
      for DependantProjectName in DependsOnOtherProjects:
        if self.CanFindMachineBuildingProject(username, DependantProjectName):
          return False

    lbs = Build(self, Logger())
    lbsName=self.GetLbsName(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
    # get name of available slot
    buildmachine=self.GetAvailableBuildMachine(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
    if not buildmachine == None:
      self.lbsList[lbsName] = lbs
      thread = Thread(target = lbs.buildpackage, args = (username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch, buildmachine))
      thread.start()
      threadWait = Thread(target = self.WaitForBuildJobFinish, args = (thread, lbsName))
      threadWait.start()
      self.ToBuild.remove(lbsName)
      self.buildqueue.remove(item)
      return True
    return False

  def buildqueuethread(self):
      while True:
        if len(self.buildqueue) > 0:
          # peek at the leftmost item
          item = self.buildqueue[0]
          if not self.attemptToFindBuildMachine(item, True):
            # check if any other project might be ready to build
            for item in self.buildqueue:
              if self.attemptToFindBuildMachine(item, False):
                break
        self.CheckForHangingBuild()
        # sleep two seconds before looping through buildqueue again
        time.sleep(2)

  def LiveLog(self, username, projectname, packagename, branchname, lxcdistro, lxcrelease, lxcarch):
        lbsName=self.GetLbsName(username,projectname,packagename,branchname,lxcdistro,lxcrelease,lxcarch)
        if lbsName in self.lbsList:
          lbs = self.lbsList[lbsName]
        elif lbsName in self.recentlyFinishedLbsList:
          lbs = self.recentlyFinishedLbsList[lbsName]
        else:
          if lbsName in self.ToBuild:
            return ("We are waiting for a build machine to become available...", 10)
          else:
            return ("No build is planned for this package at the moment...", -1)

        if lbs.finished:
          output = lbs.logger.get()
          # stop refreshing
          timeout=-1
        else:
          output = lbs.logger.get(4000)
          timeout = 2

        return (output, timeout)

