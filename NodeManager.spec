#
# $Id$
#
%define url $URL$

%define slicefamily %{pldistro}-%{distroname}-%{_arch}

%define name NodeManager
%define version 1.8
%define taglevel 37

%define release %{taglevel}%{?pldistro:.%{pldistro}}%{?date:.%{date}}

Summary: PlanetLab Node Manager
Name: %{name}
Version: %{version}
Release: %{release}
License: PlanetLab
Group: System Environment/Daemons
Source0: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root

Vendor: PlanetLab
Packager: PlanetLab Central <support@planet-lab.org>
Distribution: PlanetLab %{plrelease}
URL: %(echo %{url} | cut -d ' ' -f 2)

# not possible because of forward_api_calls
#BuildArch: noarch

# Old Node Manager
Obsoletes: sidewinder, sidewinder-common

# vuseradd, vuserdel
Requires: vserver-%{slicefamily}
Requires: util-vserver >= 0.30.208-17

# vserver.py
Requires: util-vserver-python > 0.3-16

# Signed tickets
Requires: gnupg

# Contact API server
Requires: curl

# Uses function decorators
Requires: python >= 2.4

# sioc/plnet
Requires: pyplnet >= 4.3

%description
The PlanetLab Node Manager manages all aspects of PlanetLab node and
slice management once the node has been initialized and configured by
the Boot Manager. It periodically contacts its management authority
for configuration updates. It provides an XML-RPC API for performing
local operations on slices.

%prep
%setup -q

%build
%{__make} %{?_smp_mflags}

%install
rm -rf $RPM_BUILD_ROOT
%{__make} %{?_smp_mflags} install DESTDIR="$RPM_BUILD_ROOT"

# install the sliver initscript (that triggers the slice initscript if any)
mkdir -p $RPM_BUILD_ROOT/usr/share/NodeManager/sliver-initscripts/
rsync -av sliver-initscripts/ $RPM_BUILD_ROOT/usr/share/NodeManager/sliver-initscripts/
chmod 755 $RPM_BUILD_ROOT/usr/share/NodeManager/sliver-initscripts/

install -D -m 755 conf_files.init $RPM_BUILD_ROOT/%{_initrddir}/conf_files
install -D -m 755 fuse-pl.init $RPM_BUILD_ROOT/%{_initrddir}/fuse-pl
install -D -m 755 nm.init $RPM_BUILD_ROOT/%{_initrddir}/nm
install -D -m 644 nm.logrotate $RPM_BUILD_ROOT/%{_sysconfdir}/logrotate.d/nm

%post
chkconfig --add conf_files
chkconfig conf_files on
chkconfig --add nm
chkconfig nm on
chkconfig --add fuse-pl
chkconfig fuse-pl on
if [ "$PL_BOOTCD" != "1" ] ; then
	service nm restart
	service fuse-pl restart
fi


%preun
# 0 = erase, 1 = upgrade
if [ $1 -eq 0 ] ; then
    chkconfig fuse-pl off
    chkconfig --del fuse-pl
    chkconfig nm off
    chkconfig --del nm
    chkconfig conf_files off
    chkconfig --del conf_files
fi

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
%{_datadir}/NodeManager/
%{_bindir}/forward_api_calls
%{_initrddir}/nm
%{_initrddir}/conf_files
%{_initrddir}/fuse-pl
%{_sysconfdir}/logrotate.d/nm

%changelog
* Mon Mar 21 2011 S.Çağlar Onur <caglar@verivue.com> - nodemanager-1.8-37
- Fix syntax error

* Fri Mar 18 2011 S.Çağlar Onur <caglar@verivue.com> - nodemanager-1.8-36
- use system-wide umask value otherwise all directories under /dev/cgroup and /vservers become world writable

* Fri Mar 18 2011 S.Çağlar Onur <caglar@verivue.com> - nodemanager-1.8-35
- cherry-pick initscripts changes from master

* Thu Jan 20 2011 S.Çağlar Onur <caglar@cs.princeton.edu> - nodemanager-1.8-34

* Thu Jan 20 2011 S.Çağlar Onur <caglar@cs.princeton.edu> - nodemanager-1.8-33
- start to use /etc/vservers/<guest>/sysctl/<id>/{setting,value} files as new kernels don't support old syntax

* Thu Jan 20 2011 S.Çağlar Onur <caglar@cs.princeton.edu> - nodemanager-1.8-32
- Add required helper function

* Thu Jan 20 2011 S.Çağlar Onur <caglar@cs.princeton.edu> - nodemanager-1.8-31
- Add missing vinit script

* Thu Jan 20 2011 S.Çağlar Onur <caglar@cs.princeton.edu> - nodemanager-1.8-30
- backport required vinit support from master

* Tue Jul 27 2010 Baris Metin <Talip-Baris.Metin@sophia.inria.fr> - nodemanager-1.8-29
- tagging to test module-tag on branch (no changes in nodemanager)

* Mon Jul 26 2010 Daniel Hokka Zakrisson <dhokka@cs.princeton.edu> - nodemanager-1.8-28
- Fix cciss LVM and partition detection.

* Fri Jul 23 2010 Daniel Hokka Zakrisson <dhokka@cs.princeton.edu> - nodemanager-1.8-27
- Write slice_id to the vserver configuration directory.
- Fix rawdisk for cciss.

* Tue Mar 09 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - NodeManager-1.8-26
- Support codemux's IP field
- Introduce DRL plugin

* Tue Feb 23 2010 Marc Fiuczynski <mef@cs.princeton.edu> - NodeManager-1.8-25
- Only call /etc/init.d/codemux if it is installed.

* Fri Feb 19 2010 Daniel Hokka Zakrisson <daniel@hozac.com> - NodeManager-1.8-24
- Enable/disable the codemux service too.

* Tue Jan 12 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.8-23
- emergency tag - make the setting of hmac by the sliverauth plugin more robust

* Mon Jan 11 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.8-22
- support for f10 and f12 in the vref slice tag

* Sat Jan 09 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.8-21
- build on fedora12
- uses slicename 'sfacm' instead of 'genicw'

* Fri Oct 30 2009 Sapan Bhatia <sapanb@cs.princeton.edu> - NodeManager-1.8-20
- This tag is identical to 1.8-19. The main addition is PLC-controllable vsys scripts. The reason I am
- retagging is to eliminate any confusion associated with the -19 tag which was (temporarily) modified a few
- days ago.

* Tue Oct 27 2009 Sapan Bhatia <sapanb@cs.princeton.edu> - NodeManager-1.8-19
- This patch makes vsys scripts PLC-configurable. Previously, vsys scripts needed to be
- self-contained. With this change, they will be able to refer to the attributes associated with a
- slice.

* Thu Oct 22 2009 Baris Metin <Talip-Baris.Metin@sophia.inria.fr> - NodeManager-1.8-18
- fix for syntax error

* Wed Oct 21 2009 anil vengalil <avengali@sophia.inria.fr> - NodeManager-1.8-17
- -fixed problem with sioc import at the build side
- -bwlimit.set() now accepts the device and does not asume that it is eth0

* Tue Oct 20 2009 Baris Metin <Talip-Baris.Metin@sophia.inria.fr> - NodeManager-1.8-16
- - don't hardcode the device name (depends on util-vserver-pl change rev. 15385)

* Fri Oct 09 2009 Marc Fiuczynski <mef@cs.princeton.edu> - NodeManager-1.8-15
- The seed for random previously was the meaning of life (i.e., 42) but
- that resulted in a not so random choice for the hmac.  This
- implementation now uses a random.seed that is based on the current
- time.

* Tue Oct 06 2009 Marc Fiuczynski <mef@cs.princeton.edu> - NodeManager-1.8-14
- Minor fix such that sliverauth.py makes a more specific call to
- GetSliceTags that include that specific tagname it is looking for.

* Sat Sep 19 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.8-13
- Fix bug that prevented 'OVERRIDES' for working correctly.

* Tue Sep 08 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-12
- Increase disk limits to 10G per sliver
- Sanity check slice for home directory before starting (hack)
- Check codemux arguments

* Thu Aug 06 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-11
- * Fix Delegation
- * Move plcapi in plugin-api GetSlivers() calls.
- * Persistent Authcheck and resync session when auth failure

* Tue Aug 04 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-10
- Disabling sliverauth module.  Not ready for deployment.

* Mon Aug 03 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-9
- Fixing overrides semantics.

* Mon Aug 03 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-8
- Generalized plugins
- Fixed initscript start up bug.

* Tue Jun 30 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-7
- * Fix delegation authentication problem
- * Can now disable codemux using _default slice, and setting tag {codemux: -1}

* Tue May 26 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.8-4
- * Rerun initscripts when slice goes from disabled to enabled.

* Tue May 26 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.8-4
- * Update session key when out of synch with PLC
- * PLCDefaults uses tagname

* Fri Apr 17 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.8-3
- log invokations of vsys

* Fri Mar 27 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-2

* Tue Mar 24 2009 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.8-1

* Wed Apr 02 2008 Faiyaz Ahmed <faiyaza@cs.prineton.edu - NodeManager-1.7.4
- Codemux supports multiple hosts mapping to single slice
- Fixed bug in delegation support where tickets delivered weren't
  being passed to sm.deliver_ticket().
* Fri Mar 28 2008 Faiyaz Ahmed <faiyaza@cs.prineton.edu - NodeManager-1.7.3
- Codemux now configured via slice attribute (host,port)
- Support for multiple vserver reference images (including different archs)
- Mom BW emails are sent to list defined by MyPLC's config
- Sirius BW loans honored correctly.  Fixed.
- BW totals preserved for dynamic slices so as not to game the system.
* Thu Feb 14 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-1 NodeManager-1.7-2
- Configures vsys via vsys slice attribute {name: vsys, value: script}
- CPU reservations are now calculated via percentages instead of shares
- BW totals preserved for dynamic slices
- Closes bug where node cap sets off bw slice alarms for all slices.

* Wed Oct 03 2007 Faiyaz Ahmed <faiyaza@cs.princeton.edu> .
- Switched to SVN.

* Mon Nov 13 2006 Mark Huang <mlhuang@paris.CS.Princeton.EDU> - 
- Initial build.
