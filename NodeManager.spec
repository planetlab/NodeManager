#
# $Id$
#
%define url $URL$

%define slicefamily %{pldistro}-%{distroname}-%{_arch}

%define name NodeManager
%define version 1.7
%define taglevel 15

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

# Old Node Manager
Obsoletes: sidewinder, sidewinder-common

# vuseradd, vuserdel
Requires: vserver-%{slicefamily}
Requires: util-vserver >= 0.30.208-17

# vserver.py
Requires: util-vserver-python

# Signed tickets
Requires: gnupg

# Contact API server
Requires: curl

# Uses function decorators
Requires: python >= 2.4

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

install -D -m 755 conf_files.init $RPM_BUILD_ROOT/%{_initrddir}/conf_files
install -D -m 755 nm.init $RPM_BUILD_ROOT/%{_initrddir}/nm
install -D -m 644 nm.logrotate $RPM_BUILD_ROOT/%{_sysconfdir}/logrotate.d/nm

%post
chkconfig --add conf_files
chkconfig conf_files on
chkconfig --add nm
chkconfig nm on
if [ "$PL_BOOTCD" != "1" ] ; then
	service nm restart
fi


%preun
# 0 = erase, 1 = upgrade
if [ $1 -eq 0 ] ; then
    chkconfig nm off
    chkconfig --del nm
    chkconfig conf_files off
    chkconfig --del conf_files
fi

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
%doc
%dir %{_datadir}/NodeManager
%{_datadir}/NodeManager/*
%{_bindir}/forward_api_calls
%{_initrddir}/nm
%{_initrddir}/conf_files
%{_sysconfdir}/logrotate.d/nm

%changelog
* Wed Jun 18 2008 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.7-15
- 
- enable restart if vsys.conf changes also.
- 

* Wed Jun 18 2008 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.7-14
- 
- the _restart flag for vsys was getting lost when looking across multiple
- vservers.  adding the 'or' should preserve any 'True' returns from
- createVsysDir()
- 

* Tue Jun 17 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-13
- 
- Time out curl when no response for 90 seconds.
- 

* Fri Jun 13 2008 Stephen Soltesz <soltesz@cs.princeton.edu> - NodeManager-1.7-12
- Patch designed to work around the vsys-fail-to-restart problem with
- non-existent directories, and the vuseradd-fail-to-work on directories that
- do exist.  
- 
- This patch will work in conjunction with the new vsys patch.
- 

* Wed May 14 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.7-10
- fixed doc build by locating locally installed DTDs at build-time

* Fri May 09 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-9
- * Reverted vserver start to forking before VServer.start to avoid defunct procs.* House keeping in various places.

* Fri May 09 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - NodeManager-1.7-8
- merge changes for myplc-docs from trunk

* Wed Apr 16 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-7
- 
- Set vcVHI_CONTEXT as slice_id for fprobe-ulog to mark packets with.
- 

* Wed Apr 09 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-5 NodeManager-1.7-6
- 
- * Codemux will use PLC_API_HOST when PLC_PLANETFLOW_HOST isn't defined.
- 

* Fri Apr 04 2008 Faiyaz Ahmed <faiyaza@cs.princeton.edu> - NodeManager-1.7-4 NodeManager-1.7-5
- * vdu limitting when NM restarts and slices are re-init'ed
- * CoDemux config parser update.  Now tolerates spaces.

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
