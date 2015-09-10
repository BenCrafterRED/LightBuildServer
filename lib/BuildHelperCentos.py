#!/usr/bin/env python3
"""BuildHelper for CentOS: knows how to build packages for CentOS"""

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
from BuildHelper import BuildHelper;
import time
import os
import glob
import yaml
import tempfile
import shutil
import re
import logging

class BuildHelperCentos(BuildHelper):
  'build packages for CentOS'

  def __init__(self, container, username, projectname, packagename):
    self.dist='centos'
    BuildHelper.__init__(self, container, username, projectname, packagename)
    self.yumOrDnf = 'yum'

  def PrepareMachineBeforeStart(self):
    return True

  def PrepareForBuilding(self):
    #self.run(self.yumOrDnf + " clean headers dbcache rpmdb")
    if not self.run(self.yumOrDnf + " -y update"):
      if not self.run(self.yumOrDnf + " clean all && " + self.yumOrDnf + " -y update"):
        return False
    yumUtils="yum-utils"
    if self.yumOrDnf == "dnf":
      yumUtils="'dnf-command(config-manager)'"
    if not self.run(self.yumOrDnf + " -y install tar createrepo gcc rpm-build rpm-sign gnupg make curl rsync " + yumUtils):
      return False
    # CentOS5: /root/rpmbuild should point to /usr/src/redhat
    if self.dist == "centos" and self.release == "5":
      self.run("mkdir -p /usr/src/redhat; ln -s /usr/src/redhat rpmbuild")
      self.run("yum -y install make iptables")
    self.run("mkdir -p rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}")
    return True

  def GetSpecFilename(self):
    if os.path.isdir(self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename):
      for file in os.listdir(self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename):
        if file.endswith(".spec") and self.packagename.startswith(file.split('.')[0]):
          return file
    return self.packagename + ".spec"

  def InstallRepositories(self, DownloadUrl):
    # first install required repos
    configfile=self.pathSrc + "/lbs-" + self.projectname + "/config.yml"
    if os.path.isfile(configfile):
      stream = open(configfile, 'r')
      config = yaml.load(stream)
      if self.dist in config['lbs'] and str(self.release) in config['lbs'][self.dist]:
        repos = config['lbs'][self.dist][str(self.release)]['repos']
        for repo in repos:
          if repo.endswith('.repo'):
            self.run("cd /etc/yum.repos.d/; curl -L " + repo + " -o `basename " + repo + "`")
          elif repo.endswith('.rpm'):
            if not self.run(self.yumOrDnf + " -y install " + repo):
              return False
          elif repo.startswith('http://') or repo.startswith('https://'):
            configmanager="yum-config-manager --add-repo "
            if self.yumOrDnf == "dnf":
              configmanager="dnf config-manager --add-repo "
            if not self.run(configmanager + repo):
              return False
          else:
            if not self.run(self.yumOrDnf + " -y install " + repo):
              return False
        if 'keys' in config['lbs'][self.dist][str(self.release)]:
          keys = config['lbs'][self.dist][str(self.release)]['keys']
          for key in keys:
            if not self.run("rpm --import '" + key + "'"):
              return False

    # install own repo as well if it exists
    repofile=self.config['lbs']['ReposPath'] + "/" + self.username + "/" + self.projectname + "/" + self.dist + "/" + self.release + "/lbs-" + self.username + "-" + self.projectname + ".repo"
    if os.path.isfile(repofile):
      self.container.rsyncContainerPut(repofile,"/etc/yum.repos.d/")

    self.run(self.yumOrDnf + " clean metadata")
    return True

  def InstallRequiredPackages(self):
    # now install required packages
    specfile=self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename()
    if os.path.isfile(specfile):
      remoteSpecName="lbs-" + self.projectname + "/" + self.packagename + "/" + self.packagename + ".spec"
      self.run("sed -e 's/Release:.*%{release}/Release: 0/g' " + remoteSpecName + " > /tmp/" + self.packagename + ".spec")
      if self.dist == "centos" and self.release == "5":
        # we cannot use yum-builddep because it requires a SRPM. need to use a setup.sh script instead
        return True
      builddep = "yum-builddep"
      if self.yumOrDnf == "dnf":
        builddep = "dnf builddep"
      if not self.run(builddep + " -y /tmp/" + self.packagename + ".spec"):
        return False
    return True

  def BuildPackage(self, config):
    DownloadUrl = config['lbs']['DownloadUrl']
    DeletePackagesAfterDays = config['lbs']['DeletePackagesAfterDays']
    KeepMinimumPackages = config['lbs']['KeepMinimumPackages']
    myPath = self.username + "/" + self.projectname
    if 'Secret' in config['lbs']['Users'][self.username]:
      myPath = self.username + "/" + config['lbs']['Users'][self.username]['Secret'] + "/" + self.projectname
    repopath=self.config['lbs']['ReposPath'] + "/" + myPath + "/" + self.dist + "/" + self.release
    specfile=self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename()
    if os.path.isfile(specfile):
      remoteSpecName="lbs-" + self.projectname + "/" + self.packagename + "/" + self.packagename + ".spec"
      self.run('sed -i "s/0%{?suse_version}/' + str(self.suse_version) + '/g" ' + remoteSpecName)
      self.run('sed -i "s/0%{?rhel}/' + str(self.rhel) + '/g" ' + remoteSpecName)
      self.run('sed -i "s/0%{?fedora}/' + str(self.fedora) + '/g" ' + remoteSpecName)
      self.run("cp " + remoteSpecName + " rpmbuild/SPECS")

      # copy patches, and other files (eg. env.sh for mono-opt)
      self.run("cp lbs-" + self.projectname + "/" + self.packagename + "/* rpmbuild/SOURCES")

      # move the sources that have been downloaded according to instructions in config.yml. see BuildHelper::DownloadSources
      self.run("mv sources/* rpmbuild/SOURCES")

      arch=self.arch
      if arch == "amd64":
        arch="x86_64"
      elif arch == "i686":
        arch="i386"

      # read version from spec file, that is on the build server
      # (setup.sh might overwrite the version number...)
      temppath = tempfile.mkdtemp()
      self.container.rsyncContainerGet("/root/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename(), temppath)
      buildversion = "1.0.0"
      for line in open(temppath + "/" + self.GetSpecFilename()):
        if line.startswith("%define version "):
          buildversion=line[len("%define version "):].strip()
        if line.startswith("Version: ") and not "%{version}" in line:
          buildversion=line[len("Version: "):].strip()
        if line.startswith("BuildArch: "):
          # deal with noarch
          arch=line[len("BuildArch: "):].strip()
      shutil.rmtree(temppath)

      # build counter for automatically increasing the release number
      buildnumber=0

      rpmfiles=[]
      if os.path.isdir(repopath + "/" + arch):
        for file in os.listdir(repopath + "/" + arch):
          # TODO use GetSpecFilename, without spec, instead of packagename
          if file.startswith(self.packagename + "-" + buildversion + "-") and file.endswith("." + arch + ".rpm"):
            oldnumber=file[len(self.packagename + "-" + buildversion + "-"):-1*len("." + arch + ".rpm")]
            if '.' in oldnumber:
              oldnumber=oldnumber[:oldnumber.find('.')]
            oldnumber=int(oldnumber)
            rpmfiles.append(str(oldnumber).zfill(6) + ":" + file)
            if oldnumber >= buildnumber:
              buildnumber = oldnumber + 1
      self.run("sed -i -e 's/Release:.*%{release}/Release: " + str(buildnumber) + "/g' rpmbuild/SPECS/" + self.packagename + ".spec")

      if not self.run("rpmbuild -ba rpmbuild/SPECS/" + self.packagename + ".spec"):
        return False

      # import the private key for signing the package if the file privateLBSkey exists
      sshContainerPath = config['lbs']['SSHContainerPath']
      if os.path.isfile(sshContainerPath + '/' + self.username + '/' + self.projectname + '/privateLBSkey'):
        # do not sign packages on CentOS5, see https://github.com/tpokorra/lbs-mono/issues/9
        if not (self.dist == "centos" and self.release == "5"):
          self.run("gpg --import < ~/.ssh/privateLBSkey; cp -f ~/.ssh/rpmmacros ~/.rpmmacros")
          if not self.run("if ls rpmbuild/RPMS/" + arch + "/*.rpm 1> /dev/null 2>&1; then rpm --addsign rpmbuild/RPMS/" + arch + "/*.rpm; fi"):
            return False
          if not self.run("if ls rpmbuild/RPMS/noarch/*.rpm 1> /dev/null 2>&1; then rpm --addsign rpmbuild/RPMS/noarch/*.rpm; fi"):
            return False

      # add result to repo
      self.run("mkdir -p ~/repo/src")
      self.run("cp ~/rpmbuild/SRPMS/*.src.rpm ~/repo/src")
      self.run("cp -R ~/rpmbuild/RPMS/* ~/repo")

      # clean up old packages
      MaximumAgeInSeconds=time.time() - (DeletePackagesAfterDays*24*60*60)
      rpmfiles=sorted(rpmfiles)
      if (len(rpmfiles) > KeepMinimumPackages):
        for i in range(1, len(rpmfiles) - KeepMinimumPackages + 1):
          file=rpmfiles[i - 1][7:]
          # delete older rpm files, depending on DeletePackagesAfterDays
          if os.path.getmtime(repopath + "/" + arch + "/" + file) < MaximumAgeInSeconds:
            self.run("rm -f " + "/root/repo/" + arch + "/" + file)
            self.run("rm -f " + "/root/repo/" + arch + "/" + str.replace(file, self.packagename + "-", self.packagename + "-debuginfo-"))
            # TODO: what about other packages provided by that source package
            self.run("rm -f " + "/root/repo/src/" + str.replace(file, arch+".rpm", "src.rpm"))

      if not self.run("cd repo && createrepo ."):
        return False
    return True

  def CreateRepoFile(self, config):
    DownloadUrl = config['lbs']['DownloadUrl']
    myPath = self.username + "/" + self.projectname
    if 'Secret' in config['lbs']['Users'][self.username]:
      myPath = self.username + "/" + config['lbs']['Users'][self.username]['Secret'] + "/" + self.projectname
    repopath=self.config['lbs']['ReposPath'] + "/" + myPath + "/" + self.dist + "/" + self.release
    if os.path.isdir(repopath + "/repodata"):
      repoFileContent="[lbs-"+self.username + "-"+self.projectname +"]\n"
      repoFileContent+="name=LBS-"+self.username + "-"+self.projectname +"\n"
      repoFileContent+="baseurl=" + DownloadUrl + "/repos/" + myPath + "/" + self.dist + "/" + self.release + "\n"
      repoFileContent+="enabled=1\n"
      repoFileContent+="gpgcheck=0\n"
      repofile="lbs-"+self.username + "-"+self.projectname +".repo"
      with open(repopath + "/" + repofile, 'w') as f:
        f.write(repoFileContent)
    return True

  def getRepoUrl(self, config, DownloadUrl, buildtarget):
    buildtarget = buildtarget.split("/")
    repourl = DownloadUrl + "/repos/" + self.username + "/"
    if 'Secret' in config['lbs']['Users'][self.username]:
        repourl += config['lbs']['Users'][self.username]['Secret'] + "/"
    repourl += self.projectname + "/" + buildtarget[0] + "/" + buildtarget[1]
    return repourl
    
  # find the latest src package
  def GetSrcInstructions(self, config, DownloadUrl, buildtarget):
    srcurl = self.getRepoUrl(config, DownloadUrl, buildtarget)
    buildtarget = buildtarget.split("/")
    result = None

    srcPath=self.config['lbs']['ReposPath'] + "/" + self.username + "/"
    if 'Secret' in config['lbs']['Users'][self.username]:
      srcPath += config['lbs']['Users'][self.username]['Secret'] + "/"

    srcPath += self.projectname + "/" + buildtarget[0] + "/" + buildtarget[1] + "/src"
    if os.path.isdir(srcPath):
      latestFile=None
      latestTime=0
      for fn in os.listdir(srcPath):
        if fn.startswith(self.GetSpecFilename()[:-5] + "-") and fn[len(self.GetSpecFilename()[:-5]) + 1].isdigit() and fn.endswith(".src.rpm"):
          fileTime=os.path.getmtime(srcPath + "/" + fn)
          if fileTime > latestTime:
            latestTime=fileTime
            latestFile=fn
      if latestFile is not None:
        result = (srcurl + "/src/" + latestFile, latestFile)
    return result

  def GetWinInstructions(self, config, DownloadUrl, buildtarget):
    repourl = self.getRepoUrl(config, DownloadUrl, buildtarget)
    buildtarget = buildtarget.split("/")
    # check if there is such a package at all
    checkfile = self.config['lbs']['ReposPath'] + "/" + self.username + "/"
    if 'Secret' in config['lbs']['Users'][self.username]:
      checkfile += config['lbs']['Users'][self.username]['Secret'] + "/"
    checkfile += self.projectname + "/" + self.dist
    # perhaps we have built a Windows installer with NSIS
    windowsfile = checkfile + "/" + buildtarget[1] + "/windows/" + self.packagename + "/*.exe"
    if glob.glob(windowsfile):
      newest = max(glob.iglob(windowsfile), key=os.path.getctime)
      winurl = repourl + "/windows/" + self.packagename + "/"
      winurl += os.path.basename(newest) 
      return (winurl, os.path.basename(newest))
    return None

  def GetRepoInstructions(self, config, DownloadUrl, buildtarget):
    if self.GetWinInstructions(config, DownloadUrl, buildtarget):
      return None
    repourl = self.getRepoUrl(config, DownloadUrl, buildtarget)
    repourl += "/lbs-"+self.username + "-"+self.projectname +".repo"
    buildtarget = buildtarget.split("/")
    result = ""
    if not (buildtarget[0] == "centos" and buildtarget[1] == "5"):
      if 'PublicKey' in config['lbs']['Users'][self.username]['Projects'][self.projectname]:
        result += 'rpm --import "' + config['lbs']['Users'][self.username]['Projects'][self.projectname]['PublicKey'] + '"' + "\n"
    # packagename: name of spec file, without .spec at the end
    packagename=self.GetSpecFilename()[:-5]
    if buildtarget[0] == "centos" and buildtarget[1] == "5":
      result += "wget " + repourl + " -O /etc/yum.repos.d/lbs-"+self.username + "-"+self.projectname +".repo" + "\n"
      result += "yum install " + packagename
    elif buildtarget[0] == "fedora" and (buildtarget[1] == "rawhide" or int(buildtarget[1]) >= 22):
      result += "dnf install 'dnf-command(config-manager)'\n"
      result += "dnf config-manager --add-repo " + repourl + "\n"
      result += "dnf install " + packagename
    else:
      result += "yum install yum-utils\n"
      result += "yum-config-manager --add-repo " + repourl + "\n"
      result += "yum install " + packagename

    # check if there is such a package at all
    checkfile = self.config['lbs']['ReposPath'] + "/" + self.username + "/"
    if 'Secret' in config['lbs']['Users'][self.username]:
      checkfile += config['lbs']['Users'][self.username]['Secret'] + "/"
    checkfile += self.projectname + "/" + self.dist + "/*/*/" + self.GetSpecFilename()[:-5] + "*"
    if glob.glob(checkfile):
      return result
 
    return None

  def GetDependanciesAndProvides(self):
    specfile=self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename()
    builddepends=[]
    provides={}
    if os.path.isfile(specfile):
      for line in open(specfile):
        if line.lower().startswith("buildrequires: "):
          if line.count(",") > 0:
            packagesWithVersions=line[len("BuildRequires: "):].split(",")
          else:
            packagesWithVersions=line[len("BuildRequires: "):].split()
          ignoreNext=False
          for word in packagesWithVersions:
            if not ignoreNext:
              # filter >= 3.0, only use package names
              if word[0] == '>' or word[0] == '<' or word[0] == '=':
                ignoreNext=True
              else:
                builddepends.append(word.strip())
            else:
              ignoreNext=False

      name = self.packagename
      recentpackagename=name
      for line in open(specfile):
        if line.lower().startswith("name:"):
          name = line[len("name:"):].strip()
          recentpackagename=name
          provides[name] = []
        elif line.lower().startswith("%package -n"):
          recentpackagename=line[len("%package -n"):].strip()
          provides[recentpackagename] = []
        elif line.lower().startswith("%package"):
          recentpackagename=self.packagename + "-" + line[len("%package"):].strip()
          provides[recentpackagename] = []
        elif line.lower().startswith("requires:"):
          r = line[len("requires:"):].strip().replace("(", "-").replace(")", "")
          provides[recentpackagename].append(r.split()[0])

    return (builddepends, provides)
