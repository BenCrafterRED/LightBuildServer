#!/usr/bin/env python3
"""Interface class for Container Management"""

# Copyright (c) 2014-2024 Timotheus Pokorra

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

import sys
import os
import time
import socket
from pathlib import Path

from django.conf import settings

from lib.Logger import Logger
from lib.Shell import Shell

class RemoteContainer:
  def __init__(self, containername, configBuildMachine, logger, packageSrcPath, containertype):
    self.hostname = containername
    self.containertype = containertype
    self.staticMachine = configBuildMachine.static

    self.port = str(configBuildMachine.port)
    self.cid = configBuildMachine.cid

    self.containername = str(self.cid).zfill(3) + "-" + containername
    if containertype == "incus":
      self.containername="l" + str(self.cid).zfill(3) + "-" + containername.replace(".","-")

    if "example.org" in self.hostname:
        raise Exception("please replace example.org with actual hostname")

    self.containerIP=socket.gethostbyname(self.hostname)
    self.containerPort=str(2000+int(self.cid))

    if configBuildMachine.local:
      # the host server for the build container is actually hosting the LBS application as well
      # or the container is running on localhost
      if containertype in ("lxc", "incus"):
        self.containerIP=self.calculateLocalContainerIP(self.cid)
        self.containerPort="22"
      if containertype == "docker":
        self.containerIP=self.calculateLocalContainerIP(1)
        self.containerPort=str(2000+int(self.cid))

    if not configBuildMachine.private_key or configBuildMachine.private_key=="TODO":
        raise Exception(f"please add a private key for machine {containername}")

    self.SSHContainerPath = f"{settings.SSH_TMP_PATH}/{containername}/"
    Path(self.SSHContainerPath).mkdir(parents=True, exist_ok=True)
    with open(self.SSHContainerPath + 'container_rsa', 'w') as f:
        f.write(configBuildMachine.private_key)
    # only the user can read and write this file
    os.chmod(self.SSHContainerPath + 'container_rsa', 0o600)

    self.logger = logger
    self.shell = Shell(logger)
    # we are reusing the slots, for caches etc
    self.slot = containername
    self.distro = ""
    self.release = ""
    self.arch = ""
    self.staticIP = ""
    self.packageSrcPath = packageSrcPath

  def calculateLocalContainerIP(self, cid):
    # for Incus, we always configure the bridge with 10.0.6:
    if self.containertype == "incus":
      return "10.0.6." + str(cid)

    # test if we are inside a container as well
    # we just test if the host server for the build container is actually hosting the LBS application as well
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # just need to connect to any external host to know which is the IP address of the machine that hosts LBS
    s.connect((self.hostname, 80))
    lbsipaddress=s.getsockname()[0].split('.')
    lbsipaddress.pop()
    # on CentOS: /etc/libvirt/qemu/networks/default.xml 192.168.122
    # on Fedora 27: /etc/libvirt/qemu/networks/default.xml 192.168.124
    # on Ubuntu 16.04: /etc/default/lxc-net 10.0.3
    # for Incus I am using 10.0.6
    if '.'.join(lbsipaddress) in ("192.168.122", "192.168.124", "10.0.3", "10.0.4", "10.0.6"):
      return '.'.join(lbsipaddress) + "." + str(cid)

    # we are running uwsgi and lxc/docker on one host
    if os.path.isfile("/etc/redhat-release"):
      file = open("/etc/redhat-release", 'r')
      version = file.read()
      if "Fedora" in version:
        return "192.168.124." + str(cid)
      if "CentOS" in version:
        return "192.168.122." + str(cid)
    elif os.path.isfile("/etc/lsb-release"):
      file = open("/etc/lsb-release", 'r')
      version = file.read()
      if "Ubuntu" in version:
        return "10.0.3." + str(cid)

  def executeOnHost(self, command):
    if self.shell.executeshell('ssh -f -o "StrictHostKeyChecking no" -p ' + self.port + ' -i ' + self.SSHContainerPath + "/container_rsa root@" + self.hostname + " \"export LC_ALL=C; (" + command + ") 2>&1; echo \$?\""):
      return self.logger.getLastLine() == "0"
    return False

  def createmachine(self, distro, release, arch, staticIP):
    # not implemented here
    return False

  def startmachine(self):
    # not implemented here
    return False

  def executeInContainer(self, command):
    """Execute a command in a container via SSH"""
    # not implemented here
    return False

  def destroy(self):
    # not implemented here
    return False

  def stop(self):
    # not implemented here
    return False

  def rsyncContainerPut(self, src, dest):
    # not implemented here
    return False

  def rsyncContainerGet(self, path, dest = None):
    # not implemented here
    return False

  def rsyncHostPut(self, src, dest = None):
    # not implemented here
    return False

  def rsyncHostGet(self, path, dest = None):
    # not implemented here
    return False

  def installmount(self, localpath, hostpath = None):
    # not implemented here
    return False
