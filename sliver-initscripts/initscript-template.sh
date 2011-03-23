#!/bin/bash
command=$1; shift
slicename=$1; shift

# that can make sense if needed
# source /etc/init.d/functions

# a reasonably tested function for installing with yum
function yum_install () {
    pkg="$1"; shift
    while true; do
	rpm -q $pkg && break
	sudo rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY 
	sudo yum -y install $pkg
	sleep 10
    done
    echo $pkg installed
}

####################
function start () {
    
}
function stop () {

}

####################
function restart () {
  stop
  start
}
case $command in 
start) start ;;
stop) stop ;;
restart) restart ;;
*) echo "Unknown command in initscript $command for slice $slicename" ;;
esac
